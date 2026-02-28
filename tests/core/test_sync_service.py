"""差分同期サービスのテスト"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kirinuki.core.errors import AuthenticationRequiredError, VideoUnavailableError
from kirinuki.core.sync_service import SyncService
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import SubtitleData, VideoMeta
from kirinuki.models.domain import Segment, SubtitleEntry


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    database.save_channel("UC1", "TestChannel", "https://youtube.com/c/test")
    return database


@pytest.fixture
def mock_ytdlp():
    return MagicMock()


@pytest.fixture
def mock_segmentation():
    return MagicMock()


@pytest.fixture
def service(db, mock_ytdlp, mock_segmentation, tmp_path):
    cookie_path = tmp_path / "cookies.txt"
    return SyncService(
        db=db,
        ytdlp_client=mock_ytdlp,
        segmentation_service=mock_segmentation,
        cookie_file_path=cookie_path,
    )


class TestSyncChannel:
    def test_new_videos(self, service, mock_ytdlp, mock_segmentation, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(video_id="vid1", title="Video 1", published_at=None, duration_seconds=3600),
            VideoMeta(video_id="vid2", title="Video 2", published_at=None, duration_seconds=7200),
        ]
        mock_ytdlp.fetch_subtitle.side_effect = [
            SubtitleData(
                video_id="vid1",
                language="ja",
                is_auto_generated=False,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
            ),
            SubtitleData(
                video_id="vid2",
                language="ja",
                is_auto_generated=True,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト2")],
            ),
        ]
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 2
        assert result.already_synced == 0
        assert result.skipped == 0

    def test_differential_sync(self, service, mock_ytdlp, mock_segmentation, db):
        # 1本目を先に同期済みにする
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)

        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid2", title="Video 2", published_at=None, duration_seconds=7200
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid2",
            language="ja",
            is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        )
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 1
        assert result.already_synced == 1

    def test_skip_no_subtitle(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Video 1", published_at=None, duration_seconds=3600
        )
        mock_ytdlp.fetch_subtitle.return_value = None

        result = service.sync_channel("UC1")
        assert result.skipped == 1
        assert result.newly_synced == 0

    def test_error_handling(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.side_effect = Exception("Network error")

        result = service.sync_channel("UC1")
        assert len(result.errors) == 1
        assert "Network error" in result.errors[0].reason


class TestSyncChannelUnavailable:
    def test_auth_error_recorded_and_counted(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.side_effect = [
            AuthenticationRequiredError("auth failed"),
            VideoMeta(video_id="vid2", title="V2", published_at=None, duration_seconds=100),
        ]
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid2", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        )
        service._segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.auth_errors == 1
        assert result.newly_synced == 1
        assert db.get_unavailable_video_ids("UC1") == {"vid1"}

    def test_unavailable_error_recorded(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.side_effect = VideoUnavailableError("vid1", "removed")

        result = service.sync_channel("UC1")
        assert len(result.errors) == 1
        assert "vid1" in result.errors[0].video_id
        assert db.get_unavailable_video_ids("UC1") == {"vid1"}

    def test_unavailable_skipped(self, service, mock_ytdlp, db):
        db.save_unavailable_video("vid1", "UC1", "unavailable", "removed")
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid2", title="V2", published_at=None, duration_seconds=100,
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid2", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        )
        service._segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.unavailable_skipped == 1
        assert result.newly_synced == 1
        # fetch_video_metadata should only be called for vid2
        assert mock_ytdlp.fetch_video_metadata.call_count == 1

    def test_cookie_update_resets_auth_records(self, service, mock_ytdlp, db, tmp_path):
        # auth記録を先に作成
        db.save_unavailable_video("vid1", "UC1", "auth_required", "auth fail")
        db.save_unavailable_video("vid2", "UC1", "unavailable", "removed")

        # cookieファイルを作成（mtime > recorded_at にする）
        import time
        time.sleep(0.1)
        cookie_path = tmp_path / "cookies.txt"
        cookie_path.write_text("cookie data")

        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="V1", published_at=None, duration_seconds=100,
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        )
        service._segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        # vid1 should be re-synced (auth record cleared), vid2 still skipped
        assert result.newly_synced == 1
        assert result.unavailable_skipped == 1


class TestSyncAll:
    def test_multiple_channels(self, service, mock_ytdlp, mock_segmentation, db):
        db.save_channel("UC2", "Channel 2", "https://youtube.com/c/ch2")

        mock_ytdlp.list_channel_video_ids.return_value = []

        result = service.sync_all()
        assert result.already_synced == 0
        # list_channel_video_ids should be called for both channels
        assert mock_ytdlp.list_channel_video_ids.call_count == 2
