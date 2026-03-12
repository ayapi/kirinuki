"""差分同期サービス"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from kirinuki.core.errors import AuthenticationRequiredError, VideoUnavailableError
from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.domain import SkipReason, SyncError, SyncResult

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(
        self,
        db: Database,
        ytdlp_client: YtdlpClient,
        segmentation_service: SegmentationService,
        cookie_file_path: Path | None = None,
    ) -> None:
        self._db = db
        self._ytdlp = ytdlp_client
        self._segmentation = segmentation_service
        self._cookie_file_path = cookie_file_path

    def sync_all(self, max_segment_ms: int = 300_000) -> SyncResult:
        channels = self._db.list_channels()
        total = SyncResult()
        for ch in channels:
            result = self.sync_channel(ch.channel_id, max_segment_ms=max_segment_ms)
            total.already_synced += result.already_synced
            total.newly_synced += result.newly_synced
            total.skipped += result.skipped
            total.auth_errors += result.auth_errors
            total.unavailable_skipped += result.unavailable_skipped
            total.not_live_skipped += result.not_live_skipped
            total.segmentation_retried += result.segmentation_retried
            total.segmentation_retry_failed += result.segmentation_retry_failed
            total.errors.extend(result.errors)
            for reason, count in result.skip_reasons.items():
                total.skip_reasons[reason] = total.skip_reasons.get(reason, 0) + count
        return total

    def sync_channel(self, channel_id: str, max_segment_ms: int = 300_000) -> SyncResult:
        channel = self._db.get_channel(channel_id)
        if not channel:
            return SyncResult(errors=[SyncError(video_id="", reason=f"Channel {channel_id} not found")])

        result = SyncResult()

        # cookie更新時にauth記録を自動リセット
        self._reset_auth_if_cookie_updated(channel_id)

        # flat extractionでチャンネル全動画IDを取得
        all_video_ids = self._ytdlp.list_channel_video_ids(channel.url)

        # DBと比較して新規IDを特定（unavailable記録済みも除外）
        existing_ids = self._db.get_existing_video_ids(channel_id)
        unavailable_ids = self._db.get_unavailable_video_ids(channel_id)
        exclude_ids = existing_ids | unavailable_ids
        new_ids = list(dict.fromkeys(vid for vid in all_video_ids if vid not in exclude_ids))
        result.already_synced = len(existing_ids)
        result.unavailable_skipped = len(
            [vid for vid in all_video_ids if vid in unavailable_ids]
        )

        for video_id in new_ids:
            try:
                self._sync_single_video(video_id, channel_id, result, max_segment_ms=max_segment_ms)
            except AuthenticationRequiredError as e:
                logger.warning("Auth required for video %s: %s", video_id, e)
                self._db.save_unavailable_video(video_id, channel_id, "auth_required", str(e))
                result.auth_errors += 1
            except VideoUnavailableError as e:
                logger.warning("Video unavailable %s: %s", video_id, e)
                self._db.save_unavailable_video(video_id, channel_id, "unavailable", str(e))
                result.errors.append(SyncError(video_id=video_id, reason=str(e)))
            except Exception as e:
                logger.error("Failed to sync video %s: %s", video_id, e)
                result.errors.append(SyncError(video_id=video_id, reason=str(e)))

        # セグメンテーション再試行
        self._retry_segmentation(channel_id, result, max_segment_ms=max_segment_ms)

        # 最終同期日時を更新
        self._db.update_channel_last_synced(channel_id, datetime.now(tz=timezone.utc))

        return result

    def _reset_auth_if_cookie_updated(self, channel_id: str) -> None:
        if self._cookie_file_path is None or not self._cookie_file_path.exists():
            return
        recorded_at = self._db.get_auth_unavailable_recorded_at(channel_id)
        if recorded_at is None:
            return
        cookie_mtime = datetime.fromtimestamp(
            self._cookie_file_path.stat().st_mtime, tz=timezone.utc
        )
        if cookie_mtime > recorded_at:
            cleared = self._db.clear_unavailable_by_type(channel_id, "auth_required")
            if cleared > 0:
                logger.info("Cleared %d auth-required records for %s (cookie updated)", cleared, channel_id)

    def _retry_segmentation(
        self, channel_id: str, result: SyncResult, max_segment_ms: int = 300_000
    ) -> None:
        """セグメンテーション未完了動画の再試行を実行する。"""
        unsegmented_ids = self._db.get_unsegmented_video_ids(channel_id)
        for video_id in unsegmented_ids:
            entries = self._db.get_subtitle_entries(video_id)
            if not entries:
                continue
            video = self._db.get_video(video_id)
            if video is None:
                continue
            try:
                self._segmentation.segment_video_from_entries(
                    video_id, entries, video.duration_seconds,
                    max_segment_ms=max_segment_ms,
                )
                result.segmentation_retried += 1
            except Exception as e:
                logger.warning("Segmentation retry failed for video %s: %s", video_id, e)
                result.segmentation_retry_failed += 1

    def _sync_single_video(
        self, video_id: str, channel_id: str, result: SyncResult, max_segment_ms: int = 300_000
    ) -> None:
        # メタデータ取得
        meta = self._ytdlp.fetch_video_metadata(video_id)

        # ライブ配信アーカイブ判定（live_status=Noneは安全側に倒してsync対象）
        if meta.live_status is not None and meta.live_status != "was_live":
            logger.info(
                "Skipping non-live video %s: %s (live_status=%s)",
                video_id, meta.title, meta.live_status,
            )
            result.not_live_skipped += 1
            result.skip_reasons[SkipReason.NOT_LIVE_ARCHIVE] = (
                result.skip_reasons.get(SkipReason.NOT_LIVE_ARCHIVE, 0) + 1
            )
            return

        # 字幕取得
        subtitle_data, skip_reason = self._ytdlp.fetch_subtitle(video_id)
        if subtitle_data is None:
            reason_str = skip_reason.value if skip_reason else "unknown"
            logger.info("No subtitle for video %s: %s", video_id, reason_str)
            result.skipped += 1
            if skip_reason:
                result.skip_reasons[skip_reason] = result.skip_reasons.get(skip_reason, 0) + 1
            return

        # 動画をDBに保存
        self._db.save_video(
            video_id=video_id,
            channel_id=channel_id,
            title=meta.title,
            published_at=meta.published_at,
            duration_seconds=meta.duration_seconds,
            subtitle_language=subtitle_data.language,
            is_auto_subtitle=subtitle_data.is_auto_generated,
            broadcast_start_at=meta.broadcast_start_at or meta.published_at,
        )

        # 字幕行をDBに保存
        self._db.save_subtitle_lines(video_id, subtitle_data.entries)

        # セグメンテーション
        try:
            self._segmentation.segment_video_from_entries(
                video_id, subtitle_data.entries, meta.duration_seconds,
                max_segment_ms=max_segment_ms,
            )
        except Exception as e:
            logger.warning("Segmentation failed for video %s: %s", video_id, e)
            # セグメンテーション失敗でも字幕データは保存済み

        result.newly_synced += 1
