"""LLM APIクライアント"""

from __future__ import annotations

import json
import logging
import re

import anthropic
from pydantic import BaseModel, Field, ValidationError

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


class LLMClient:
    def __init__(self, api_key: str = "", model: str = "claude-haiku-4-5-20251001") -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def evaluate_segments(
        self,
        video_id: str,
        segments: list[dict[str, str | int]],
        prompt_version: str,
    ) -> list[SegmentRecommendation]:
        """動画1本分のセグメントをバッチ分割して評価する"""
        all_evaluations: list[SegmentEvaluation] = []

        for i in range(0, len(segments), BATCH_SIZE):
            batch = segments[i : i + BATCH_SIZE]
            batch_result = self._evaluate_batch(batch)
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
            model=self._model,
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
