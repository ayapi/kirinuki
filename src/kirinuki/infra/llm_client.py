"""Claude APIクライアント（セグメンテーション・評価統合）"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor

import anthropic
from pydantic import BaseModel, Field, ValidationError

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import TopicSegment
from kirinuki.models.recommendation import SegmentRecommendation

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 8192
BATCH_SIZE = 50

EVALUATION_PROMPT = """\
あなたは YouTube 配信の切り抜き動画の専門家です。
以下の配信アーカイブの話題セグメント一覧を評価し、各セグメントの「切り抜き適性」を判定してください。

## 評価基準（4軸）

1. **話題の独立性**: 前後の文脈がなくても、このセグメントだけで楽しめるか
   - 高: 完結した話題、自己紹介、雑談の一区切り
   - 低: 前の話題の続き、「さっきの話だけど」のような参照が多い

2. **エンタメ性**: 面白さ・意外性・笑い・ギャップがあるか
   - 高: ハプニング、面白エピソード、意外な展開、リアクション芸
   - 低: 淡々とした報告、定型的なお知らせ

3. **情報価値**: 有用な知識・ノウハウ・レビューが含まれるか
   - 高: 専門知識の共有、購入レビュー、ハウツー
   - 低: 一般的な雑談、既知の情報の繰り返し

4. **感情的インパクト**: 共感・感動・驚き・応援したくなるような要素があるか
   - 高: 泣ける話、嬉しい報告、努力の成果発表
   - 低: 感情の起伏が少ない

## スコアリング方針

- スコアは4軸の平均ではありません。**いずれか1つの軸で突出していれば、それだけで高スコア（8〜10）にしてください。**
- 例: 情報価値はゼロでも、とにかく笑える・エンタメとして最高なら 9〜10 をつけてOKです。
- 逆に、すべての軸で「まあまあ」なセグメントは中程度（5〜6）に留めてください。

## セグメント一覧

{segments_text}

## 出力指示

以下のJSON形式で出力してください。他のテキストは一切含めないでください:
{{"evaluations": [
  {{"segment_id": セグメントID, "score": 切り抜き推薦スコア（1〜10の整数。10が最も推薦）, "summary": "話題の要約（1〜2文で簡潔に）", "appeal": "この部分が切り抜きに向いている理由（1〜2文）"}}
]}}
"""


class SegmentEvaluation(BaseModel):
    """LLMの評価結果1件"""
    segment_id: int
    score: int = Field(ge=1, le=10)
    summary: str
    appeal: str


class EvaluationResponse(BaseModel):
    """LLMの評価結果一覧"""
    evaluations: list[SegmentEvaluation]


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
        self._max_workers = config.max_concurrent_api_calls

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

    def evaluate_segments(
        self,
        video_id: str,
        segments: list[dict[str, str | int]],
        prompt_version: str,
    ) -> list[SegmentRecommendation]:
        """動画1本分のセグメントをバッチ分割して並列評価する"""
        batches = [
            segments[i : i + BATCH_SIZE]
            for i in range(0, len(segments), BATCH_SIZE)
        ]

        all_evaluations: list[SegmentEvaluation] = []
        if len(batches) <= 1:
            for batch in batches:
                batch_result = self._evaluate_batch(batch)
                if batch_result is not None:
                    all_evaluations.extend(batch_result)
        else:
            workers = min(self._max_workers, len(batches))
            logger.info(
                "Evaluating %d batches in parallel (max_workers=%d)",
                len(batches), workers,
            )
            with ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(self._evaluate_batch, batches))
            for batch_result in results:
                if batch_result is not None:
                    all_evaluations.extend(batch_result)

        return [
            SegmentRecommendation(
                segment_id=ev.segment_id,
                video_id=video_id,
                start_time=self._find_segment_time(segments, ev.segment_id, "start_ms") / 1000.0,
                end_time=self._find_segment_time(segments, ev.segment_id, "end_ms") / 1000.0,
                score=ev.score,
                summary=ev.summary,
                appeal=ev.appeal,
                prompt_version=prompt_version,
            )
            for ev in all_evaluations
        ]

    def _evaluate_batch(
        self,
        segments: list[dict[str, str | int]],
    ) -> list[SegmentEvaluation] | None:
        """1バッチ分のセグメントをLLMで評価する。失敗時はNoneを返す。"""
        # 連番（1始まり）→ 実セグメントのマッピング
        index_to_seg = {i + 1: seg for i, seg in enumerate(segments)}

        segments_text = "\n".join(
            f"- ID: {i + 1}, 区間: {seg['start_ms']/1000:.0f}s〜{seg['end_ms']/1000:.0f}s, "
            f"内容: {seg['summary']}"
            for i, seg in enumerate(segments)
        )

        prompt = EVALUATION_PROMPT.format(segments_text=segments_text)

        response = self._client.messages.create(
            model=self._config.llm_model,
            max_tokens=DEFAULT_MAX_TOKENS,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.stop_reason == "max_tokens":
            logger.warning(
                "LLM evaluation response was truncated (max_tokens). "
                "Batch size: %d segments",
                len(segments),
            )
            return None

        raw_text = response.content[0].text
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM evaluation response as JSON: %s", raw_text[:200])
            return None

        try:
            parsed = EvaluationResponse.model_validate(data)
        except ValidationError:
            logger.warning("Failed to validate LLM evaluation response: %s", raw_text[:200])
            return None

        # 連番 → 実ID に変換 + バリデーション
        mapped: list[SegmentEvaluation] = []
        for ev in parsed.evaluations:
            real_seg = index_to_seg.get(ev.segment_id)
            if real_seg is None:
                logger.warning("LLM returned unknown segment index %d, skipping", ev.segment_id)
                continue
            mapped.append(SegmentEvaluation(
                segment_id=real_seg["id"],
                score=ev.score,
                summary=ev.summary,
                appeal=ev.appeal,
            ))
        return mapped

    @staticmethod
    def _find_segment_time(
        segments: list[dict[str, str | int]], segment_id: int, key: str
    ) -> float:
        for seg in segments:
            if seg["id"] == segment_id:
                return float(seg[key])
        return 0.0

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
