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
    from kirinuki.infra.database import Database

PROMPT_VERSION = "v3"


class LLMClientProtocol(Protocol):
    def evaluate_segments(
        self,
        video_id: str,
        segments: list[dict[str, str | int]],
        prompt_version: str,
    ) -> list[SegmentRecommendation]: ...


class SuggestService:
    def __init__(self, db: Database, llm: LLMClientProtocol) -> None:
        self._db = db
        self._llm = llm

    def suggest(self, options: SuggestOptions) -> SuggestResult:
        """最新アーカイブの切り抜き候補を推薦する。"""
        videos, warnings = self._resolve_videos(options)

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
                        broadcast_start_at=str(video.get("broadcast_start_at", "")),
                        recommendations=filtered,
                    )
                )

        filtered_count = sum(len(v.recommendations) for v in all_videos)
        return SuggestResult(
            videos=all_videos,
            total_candidates=total_candidates,
            filtered_count=filtered_count,
            warnings=warnings,
        )

    def _resolve_videos(
        self, options: SuggestOptions
    ) -> tuple[list[dict[str, str]], list[str]]:
        """動画リストを取得する。video_ids指定時はIDで取得、未指定時は最新N件。"""
        if options.video_ids:
            videos = self._db.get_videos_by_ids(options.video_ids)
            found_ids = {v["video_id"] for v in videos}
            warnings = [
                f"動画ID '{vid}' はデータベースに存在しません"
                for vid in options.video_ids
                if vid not in found_ids
            ]
            if not videos:
                raise NoArchivesError(options.video_ids[0])
            return videos, warnings

        if not self._db.channel_exists(options.channel_id):
            raise ChannelNotFoundError(options.channel_id)

        videos = self._db.get_latest_videos(
            options.channel_id, options.count, until=options.until
        )
        if not videos:
            raise NoArchivesError(options.channel_id)
        return videos, []

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
