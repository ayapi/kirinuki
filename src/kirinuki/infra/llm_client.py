"""Claude APIによる話題セグメンテーションクライアント"""

import json
import logging

import anthropic

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import TopicSegment

logger = logging.getLogger(__name__)

SEGMENTS_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "summary": {"type": "string"},
                },
                "required": ["start", "end", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["segments"],
    "additionalProperties": False,
}


def _salvage_truncated_json(raw_text: str) -> list | None:
    """途中で切れたJSONから、最後の完全なオブジェクトまでを復元する。"""
    pos = len(raw_text)
    for attempt in range(10):
        pos = raw_text.rfind("}", 0, pos)
        if pos == -1:
            logger.debug("salvage: no more } found after %d attempts", attempt)
            return None
        truncated = raw_text[: pos + 1].rstrip().rstrip(",") + "\n]}"
        try:
            data = json.loads(truncated)
            if isinstance(data, dict) and len(data.get("segments", [])) > 0:
                return data["segments"]
        except json.JSONDecodeError as e:
            logger.debug("salvage attempt %d (pos=%d): %s", attempt, pos, e)
            continue
    return None


def _parse_segments_response(response) -> list[TopicSegment]:
    """LLMレスポンスからTopicSegmentリストをパースする。切り詰め時は部分復元を試みる。"""
    raw_text = response.content[0].text
    logger.info(
        "LLM response: %d chars, stop_reason=%s, usage(in=%d, out=%d)",
        len(raw_text),
        response.stop_reason,
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    if response.stop_reason == "max_tokens":
        logger.warning("LLM response was truncated due to max_tokens limit")
    try:
        data = json.loads(raw_text)
        items = data["segments"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        salvaged = _salvage_truncated_json(raw_text)
        if salvaged is not None:
            logger.warning(
                "LLM response was truncated, salvaged %d segments from partial JSON",
                len(salvaged),
            )
            items = salvaged
        else:
            logger.warning(
                "Failed to parse LLM response as JSON (%s):\n  head: %s\n  tail: %s",
                e,
                raw_text[:200],
                raw_text[-200:],
            )
            return []

    segments: list[TopicSegment] = []
    for item in items:
        try:
            start_ms = _parse_timestamp(item["start"])
            end_ms = _parse_timestamp(item["end"])
        except (ValueError, KeyError) as e:
            logger.warning("Skipping segment with invalid timestamp: %s", e)
            continue
        segments.append(TopicSegment(start_ms=start_ms, end_ms=end_ms, summary=item["summary"]))
    return segments


def _parse_timestamp(timestamp: str) -> int:
    """タイムスタンプ文字列をミリ秒に変換。

    対応形式:
    - MM:SS (例: "01:30", "[120:00]") — _build_subtitle_text() が生成する形式
    - HH:MM:SS (例: "02:00:00") — LLMが勝手に正規化した場合のフォールバック
    """
    cleaned = timestamp.strip().strip("[]")
    parts = cleaned.split(":")
    if len(parts) == 2:
        return (int(parts[0]) * 60 + int(parts[1])) * 1000
    elif len(parts) == 3:
        return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
    raise ValueError(f"Invalid timestamp: {timestamp!r}")


SEGMENT_PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """あなたはYouTube Live配信の字幕テキストを分析する専門家です。
与えられた字幕テキストをできるだけ細かくサブトピック単位で分割し、各セグメントに階層的な要約をつけてください。

summaryは「【大分類】サブトピック（日本語、40文字以内）」の形式にしてください。

start, endには字幕テキストに含まれるタイムスタンプ（[MM:SS]の部分）をそのままコピーしてください。
時刻の変換や計算は一切不要です。[60:00]のような表記もそのままコピーし、01:00:00のような変換はしないでください。

分割基準（以下のいずれかで分割してください）:
- サブトピックの変化（話の対象・論点が変わった箇所）
- Q&A・コメント反応（視聴者コメントへの応答が始まった/終わった箇所）
- 場面転換（ゲームシーン変更、画面共有切り替えなど）
- 作業フェーズの切り替わり（準備→本編→まとめなど）

品質基準:
- 識別可能な話題がある区間のみセグメント化してください
- フィラー（「えーと」「あー」など）や相槌のみの区間は独立セグメントにせず、隣接するセグメントに含めてください
- 最小長の制約はありません。短いセグメントでも話題として成立していればそのまま出力してください

注意:
- 字幕テキストにはタイムスタンプが含まれています。[MM:SS] の形式です
- セグメントは時系列順に並べてください
- 各セグメントの区間は重複しないようにしてください"""

RESPLIT_SYSTEM_PROMPT = """あなたはYouTube Live配信の字幕テキストを分析する専門家です。
以下の字幕テキストを細かいサブトピックに分割してください。最低2つ以上のセグメントに分割してください。

参考情報: この区間は元々「{parent_summary}」として分類されていましたが、実際の内容と異なる場合があります。
必ず字幕テキストの実際の内容に基づいて分割・要約してください。

summaryは「【大分類】サブトピック（日本語、40文字以内）」の形式にしてください。

start, endには字幕テキストに含まれるタイムスタンプ（[MM:SS]の部分）をそのままコピーしてください。
時刻の変換や計算は一切不要です。[60:00]のような表記もそのままコピーし、01:00:00のような変換はしないでください。

注意:
- 字幕テキストにはタイムスタンプが含まれています。[MM:SS] の形式です
- セグメントは時系列順に並べてください
- 各セグメントの区間は重複しないようにしてください
- 識別可能な話題がある区間のみセグメント化してください
- フィラーや相槌のみの区間は隣接するセグメントに含めてください
- 【大分類】は字幕の実際の内容から判断してください"""


class LlmClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._client = anthropic.Anthropic(
            api_key=config.anthropic_api_key,
            max_retries=10,
        )

    def analyze_topics(self, subtitle_text: str) -> list[TopicSegment]:
        if not subtitle_text.strip():
            return []

        response = self._client.messages.create(
            model=self._config.llm_model,
            max_tokens=16384,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": subtitle_text}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": SEGMENTS_JSON_SCHEMA,
                }
            },
        )

        return _parse_segments_response(response)

    def analyze_topics_resplit(
        self, subtitle_text: str, parent_summary: str
    ) -> list[TopicSegment]:
        if not subtitle_text.strip():
            return []

        system_prompt = RESPLIT_SYSTEM_PROMPT.format(parent_summary=parent_summary)
        response = self._client.messages.create(
            model=self._config.llm_model,
            max_tokens=16384,
            system=system_prompt,
            messages=[{"role": "user", "content": subtitle_text}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": SEGMENTS_JSON_SCHEMA,
                }
            },
        )

        return _parse_segments_response(response)
