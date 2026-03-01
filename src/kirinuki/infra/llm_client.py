"""Claude APIによる話題セグメンテーションクライアント"""

import json
import logging
import re

import anthropic

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import TopicSegment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたはYouTube Live配信の字幕テキストを分析する専門家です。
与えられた字幕テキストをできるだけ細かくサブトピック単位で分割し、各セグメントに階層的な要約をつけてください。

以下のJSON配列形式で出力してください。他のテキストは一切含めないでください:
[
  {"start_ms": 開始時刻(ミリ秒), "end_ms": 終了時刻(ミリ秒), "summary": "【大分類】サブトピック（日本語、40文字以内）"}
]

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
以下の字幕テキストは「{parent_summary}」という大きな話題の一部です。
この区間をさらに細かいサブトピックに分割してください。最低2つ以上のセグメントに分割してください。

以下のJSON配列形式で出力してください。他のテキストは一切含めないでください:
[
  {{"start_ms": 開始時刻(ミリ秒), "end_ms": 終了時刻(ミリ秒), "summary": "【{parent_summary}】サブトピック（日本語、40文字以内）"}}
]

注意:
- 字幕テキストにはタイムスタンプが含まれています。[MM:SS] の形式です
- セグメントは時系列順に並べてください
- 各セグメントの区間は重複しないようにしてください
- 識別可能な話題がある区間のみセグメント化してください
- フィラーや相槌のみの区間は隣接するセグメントに含めてください"""


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
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": subtitle_text}],
        )

        raw_text = response.content[0].text
        # LLMがmarkdownコードフェンスで囲むことがあるので除去
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", raw_text[:200])
            return []

        return [
            TopicSegment(start_ms=item["start_ms"], end_ms=item["end_ms"], summary=item["summary"])
            for item in data
        ]

    def analyze_topics_resplit(
        self, subtitle_text: str, parent_summary: str
    ) -> list[TopicSegment]:
        if not subtitle_text.strip():
            return []

        system_prompt = RESPLIT_SYSTEM_PROMPT.format(parent_summary=parent_summary)
        response = self._client.messages.create(
            model=self._config.llm_model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": subtitle_text}],
        )

        raw_text = response.content[0].text
        raw_text = re.sub(r"^```(?:json)?\s*\n?", "", raw_text.strip())
        raw_text = re.sub(r"\n?```\s*$", "", raw_text)
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM resplit response as JSON: %s", raw_text[:200])
            return []

        return [
            TopicSegment(start_ms=item["start_ms"], end_ms=item["end_ms"], summary=item["summary"])
            for item in data
        ]
