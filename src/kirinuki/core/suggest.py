"""切り抜き推薦サービス"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from kirinuki.core.errors import ChannelNotFoundError, NoArchivesError
from kirinuki.models.recommendation import (
    SegmentRecommendation,
    SuggestOptions,
    SuggestResult,
    VideoWithRecommendations,
)

if TYPE_CHECKING:
    from kirinuki.infra.db import DatabaseClient

PROMPT_VERSION = "v3"


class LLMClientProtocol(Protocol):
    def evaluate_segments(
        self,
        video_id: str,
        segments: list[dict[str, str | int]],
        prompt_version: str,
    ) -> list[SegmentRecommendation]: ...


class SuggestService:
    def __init__(self, db: DatabaseClient, llm: LLMClientProtocol) -> None:
        self._db = db
        self._llm = llm

    def suggest(self, options: SuggestOptions) -> SuggestResult:
        """最新アーカイブの切り抜き候補を推薦する。"""
        if not self._db.channel_exists(options.channel_id):
            raise ChannelNotFoundError(options.channel_id)

        videos = self._db.get_latest_videos(options.channel_id, options.count)
        if not videos:
            raise NoArchivesError(options.channel_id)

        all_videos: list[VideoWithRecommendations] = []
        total_candidates = 0

        for video in videos:
            video_id = video["video_id"]
            recommendations = self._get_or_evaluate(video_id)
            total_candidates += len(recommendations)

            filtered = [r for r in recommendations if r.score >= options.threshold]

            if filtered:
                all_videos.append(
                    VideoWithRecommendations(
                        video_id=video_id,
                        title=video["title"],
                        published_at=str(video.get("published_at", "")),
                        recommendations=filtered,
                    )
                )

        filtered_count = sum(len(v.recommendations) for v in all_videos)
        return SuggestResult(
            videos=all_videos,
            total_candidates=total_candidates,
            filtered_count=filtered_count,
        )

    def _get_or_evaluate(self, video_id: str) -> list[SegmentRecommendation]:
        """キャッシュ確認→LLM評価のフロー"""
        cached = self._db.get_cached_recommendations(video_id, PROMPT_VERSION)
        if cached is not None:
            return cached

        segments = self._db.get_segments_for_video(video_id)
        if not segments:
            return []

        recommendations = self._llm.evaluate_segments(
            video_id, segments, PROMPT_VERSION
        )
        self._db.save_recommendations(recommendations)
        return recommendations
