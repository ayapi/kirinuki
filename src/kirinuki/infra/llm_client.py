"""Claude APIによる話題セグメンテーションクライアント"""

import json
import logging

import anthropic

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import TopicSegment

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """あなたはYouTube Live配信の字幕テキストを分析する専門家です。
与えられた字幕テキストを話題の切れ目で分割し、各セグメントに簡潔な要約をつけてください。

以下のJSON配列形式で出力してください。他のテキストは一切含めないでください:
[
  {"start_ms": 開始時刻(ミリ秒), "end_ms": 終了時刻(ミリ秒), "summary": "話題の要約（日本語、30文字以内）"}
]

注意:
- 字幕テキストにはタイムスタンプが含まれています。[MM:SS] の形式です
- セグメントは時系列順に並べてください
- 各セグメントの区間は重複しないようにしてください
- 短すぎるセグメント（1分未満）は前後と統合してください
- 話題の切り替わりが明確な箇所で分割してください"""


class LlmClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def analyze_topics(self, subtitle_text: str) -> list[TopicSegment]:
        if not subtitle_text.strip():
            return []

        client = anthropic.Anthropic(api_key=self._config.anthropic_api_key)
        response = client.messages.create(
            model=self._config.llm_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": subtitle_text}],
        )

        raw_text = response.content[0].text
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON: %s", raw_text[:200])
            return []

        return [
            TopicSegment(start_ms=item["start_ms"], end_ms=item["end_ms"], summary=item["summary"])
            for item in data
        ]
