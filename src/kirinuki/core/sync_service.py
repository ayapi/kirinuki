"""差分同期サービス"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from kirinuki.core.errors import AuthenticationRequiredError, VideoUnavailableError
from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.domain import SyncError, SyncResult

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

    def sync_all(self) -> SyncResult:
        channels = self._db.list_channels()
        total = SyncResult()
        for ch in channels:
            result = self.sync_channel(ch.channel_id)
            total.already_synced += result.already_synced
            total.newly_synced += result.newly_synced
            total.skipped += result.skipped
            total.auth_errors += result.auth_errors
            total.unavailable_skipped += result.unavailable_skipped
            total.errors.extend(result.errors)
        return total

    def sync_channel(self, channel_id: str) -> SyncResult:
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
                self._sync_single_video(video_id, channel_id, result)
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

    def _sync_single_video(self, video_id: str, channel_id: str, result: SyncResult) -> None:
        # メタデータ取得
        meta = self._ytdlp.fetch_video_metadata(video_id)

        # 字幕取得
        subtitle_data = self._ytdlp.fetch_subtitle(video_id)
        if subtitle_data is None:
            logger.info("No subtitle for video %s, skipping", video_id)
            result.skipped += 1
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
        )

        # 字幕行をDBに保存
        self._db.save_subtitle_lines(video_id, subtitle_data.entries)

        # セグメンテーション
        try:
            self._segmentation.segment_video_from_entries(
                video_id, subtitle_data.entries, meta.duration_seconds
            )
        except Exception as e:
            logger.warning("Segmentation failed for video %s: %s", video_id, e)
            # セグメンテーション失敗でも字幕データは保存済み

        result.newly_synced += 1
