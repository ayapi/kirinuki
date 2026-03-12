"""差分同期サービスのテスト"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kirinuki.core.errors import AuthenticationRequiredError, VideoUnavailableError
from kirinuki.core.sync_service import SyncService
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import SubtitleData, VideoMeta
from kirinuki.models.domain import Segment, SkipReason, SubtitleEntry


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
            (SubtitleData(
                video_id="vid1",
                language="ja",
                is_auto_generated=False,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
            ), None),
            (SubtitleData(
                video_id="vid2",
                language="ja",
                is_auto_generated=True,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト2")],
            ), None),
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
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid2",
            language="ja",
            is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        ), None)
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 1
        assert result.already_synced == 1

    def test_skip_no_subtitle(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Video 1", published_at=None, duration_seconds=3600
        )
        mock_ytdlp.fetch_subtitle.return_value = (None, SkipReason.NO_SUBTITLE_AVAILABLE)

        result = service.sync_channel("UC1")
        assert result.skipped == 1
        assert result.newly_synced == 0
        assert result.skip_reasons[SkipReason.NO_SUBTITLE_AVAILABLE] == 1

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
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid2", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        ), None)
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
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid2", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        ), None)
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
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="t")],
        ), None)
        service._segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        # vid1 should be re-synced (auth record cleared), vid2 still skipped
        assert result.newly_synced == 1
        assert result.unavailable_skipped == 1


class TestSyncLiveArchiveFilter:
    def test_was_live_video_is_synced(self, service, mock_ytdlp, mock_segmentation, db):
        """live_status=was_live の動画はsync対象"""
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Live Stream", published_at=None, duration_seconds=7200,
            live_status="was_live",
        )
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        ), None)
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 1
        assert result.not_live_skipped == 0
        mock_ytdlp.fetch_subtitle.assert_called_once()

    def test_not_live_video_is_skipped(self, service, mock_ytdlp, db):
        """live_status=not_live の動画はスキップ"""
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Regular Video", published_at=None, duration_seconds=600,
            live_status="not_live",
        )

        result = service.sync_channel("UC1")
        assert result.newly_synced == 0
        assert result.not_live_skipped == 1
        assert result.skip_reasons[SkipReason.NOT_LIVE_ARCHIVE] == 1
        mock_ytdlp.fetch_subtitle.assert_not_called()

    def test_none_live_status_is_synced(self, service, mock_ytdlp, mock_segmentation, db):
        """live_status=None の動画は安全側に倒してsync対象"""
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Unknown Video", published_at=None, duration_seconds=3600,
            live_status=None,
        )
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        ), None)
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 1
        assert result.not_live_skipped == 0
        mock_ytdlp.fetch_subtitle.assert_called_once()

    def test_mixed_live_and_not_live(self, service, mock_ytdlp, mock_segmentation, db):
        """was_live と not_live が混在するチャンネル"""
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2", "vid3"]
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(video_id="vid1", title="Live 1", published_at=None, duration_seconds=7200, live_status="was_live"),
            VideoMeta(video_id="vid2", title="Regular", published_at=None, duration_seconds=600, live_status="not_live"),
            VideoMeta(video_id="vid3", title="Live 2", published_at=None, duration_seconds=3600, live_status="was_live"),
        ]
        mock_ytdlp.fetch_subtitle.side_effect = [
            (SubtitleData(video_id="vid1", language="ja", is_auto_generated=False,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト1")]), None),
            (SubtitleData(video_id="vid3", language="ja", is_auto_generated=False,
                entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト3")]), None),
        ]
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_channel("UC1")
        assert result.newly_synced == 2
        assert result.not_live_skipped == 1
        assert mock_ytdlp.fetch_subtitle.call_count == 2

    def test_is_upcoming_skipped(self, service, mock_ytdlp, db):
        """live_status=is_upcoming の動画はスキップ"""
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Upcoming Stream", published_at=None, duration_seconds=0,
            live_status="is_upcoming",
        )

        result = service.sync_channel("UC1")
        assert result.not_live_skipped == 1
        mock_ytdlp.fetch_subtitle.assert_not_called()

    def test_not_live_skipped_merged_in_sync_all(self, service, mock_ytdlp, mock_segmentation, db):
        """sync_allでnot_live_skippedが合算される"""
        db.save_channel("UC2", "Channel 2", "https://youtube.com/c/ch2")
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Regular", published_at=None, duration_seconds=600,
            live_status="not_live",
        )

        result = service.sync_all()
        assert result.not_live_skipped == 2  # 2 channels, 1 skipped each


class TestSyncSkipReasons:
    def test_skip_reason_recorded(self, service, mock_ytdlp, db):
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(video_id="vid1", title="V1", published_at=None, duration_seconds=100),
            VideoMeta(video_id="vid2", title="V2", published_at=None, duration_seconds=100),
        ]
        mock_ytdlp.fetch_subtitle.side_effect = [
            (None, SkipReason.NO_SUBTITLE_AVAILABLE),
            (None, SkipReason.PARSE_FAILED),
        ]

        result = service.sync_channel("UC1")
        assert result.skipped == 2
        assert result.skip_reasons[SkipReason.NO_SUBTITLE_AVAILABLE] == 1
        assert result.skip_reasons[SkipReason.PARSE_FAILED] == 1

    def test_skip_reasons_merged_across_channels(self, service, mock_ytdlp, mock_segmentation, db):
        db.save_channel("UC2", "Channel 2", "https://youtube.com/c/ch2")

        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="V1", published_at=None, duration_seconds=100,
        )
        mock_ytdlp.fetch_subtitle.return_value = (None, SkipReason.NO_SUBTITLE_AVAILABLE)

        result = service.sync_all()
        assert result.skip_reasons[SkipReason.NO_SUBTITLE_AVAILABLE] == 2


class TestRetrySegmentation:
    def test_retry_succeeds(self, service, mock_ytdlp, mock_segmentation, db):
        """セグメンテーション未完了の動画が再試行で成功する"""
        # 動画と字幕をDBに保存済み（セグメントなし）
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.return_value = [
            Segment(id=1, video_id="vid1", start_ms=0, end_ms=60000, summary="topic"),
        ]

        result = service.sync_channel("UC1")
        assert result.segmentation_retried == 1
        assert result.segmentation_retry_failed == 0
        mock_segmentation.segment_video_from_entries.assert_called_once()

    def test_retry_fails(self, service, mock_ytdlp, mock_segmentation, db):
        """セグメンテーション再試行が失敗してもエラーにならない"""
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.side_effect = Exception("API credit exhausted")

        result = service.sync_channel("UC1")
        assert result.segmentation_retried == 0
        assert result.segmentation_retry_failed == 1

    def test_retry_skips_already_segmented(self, service, mock_ytdlp, mock_segmentation, db):
        """セグメンテーション済みの動画は再試行しない"""
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "topic"}])

        mock_ytdlp.list_channel_video_ids.return_value = []

        result = service.sync_channel("UC1")
        assert result.segmentation_retried == 0
        assert result.segmentation_retry_failed == 0
        mock_segmentation.segment_video_from_entries.assert_not_called()

    def test_retry_skips_video_with_no_subtitles(self, service, mock_ytdlp, mock_segmentation, db):
        """字幕データがない動画は再試行をスキップ"""
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        # subtitle_linesを保存しない
        mock_ytdlp.list_channel_video_ids.return_value = []

        result = service.sync_channel("UC1")
        assert result.segmentation_retried == 0
        assert result.segmentation_retry_failed == 0
        mock_segmentation.segment_video_from_entries.assert_not_called()

    def test_retry_does_not_call_youtube_api(self, service, mock_ytdlp, mock_segmentation, db):
        """再試行時にYouTube APIを呼び出さない"""
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.return_value = []

        service.sync_channel("UC1")
        mock_ytdlp.fetch_video_metadata.assert_not_called()
        mock_ytdlp.fetch_subtitle.assert_not_called()

    def test_retry_multiple_videos_independent(self, service, mock_ytdlp, mock_segmentation, db):
        """複数動画の再試行は独立して実行される（一方の失敗が他方に影響しない）"""
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト1"),
        ])
        db.save_subtitle_lines("vid2", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト2"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.side_effect = [
            Exception("API error"),
            [Segment(id=1, video_id="vid2", start_ms=0, end_ms=60000, summary="topic")],
        ]

        result = service.sync_channel("UC1")
        assert result.segmentation_retried == 1
        assert result.segmentation_retry_failed == 1

    def test_retry_passes_correct_duration(self, service, mock_ytdlp, mock_segmentation, db):
        """再試行時にDB内のduration_secondsが正しく渡される"""
        db.save_video("vid1", "UC1", "Video 1", None, 5400, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.return_value = []

        service.sync_channel("UC1")
        call_args = mock_segmentation.segment_video_from_entries.call_args
        assert call_args[0][0] == "vid1"  # video_id
        assert call_args[0][2] == 5400    # duration_seconds

    def test_retry_results_merged_in_sync_all(self, service, mock_ytdlp, mock_segmentation, db):
        """sync_allで再試行結果が合算される"""
        db.save_channel("UC2", "Channel 2", "https://youtube.com/c/ch2")
        # 両チャンネルに未セグメント動画
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト1"),
        ])
        db.save_video("vid2", "UC2", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid2", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト2"),
        ])
        mock_ytdlp.list_channel_video_ids.return_value = []
        mock_segmentation.segment_video_from_entries.return_value = []

        result = service.sync_all()
        assert result.segmentation_retried == 2


class TestSyncBroadcastStartAt:
    def test_broadcast_start_at_saved(self, service, mock_ytdlp, mock_segmentation, db):
        """broadcast_start_atがDBに保存される"""
        bsa = datetime(2024, 6, 15, 16, 0, 0, tzinfo=timezone.utc)
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Live", published_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
            duration_seconds=7200, live_status="was_live", broadcast_start_at=bsa,
        )
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        ), None)
        mock_segmentation.segment_video_from_entries.return_value = []

        service.sync_channel("UC1")
        row = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid1'").fetchone()
        assert row[0] == bsa.isoformat()

    def test_broadcast_start_at_fallback_to_published_at(self, service, mock_ytdlp, mock_segmentation, db):
        """broadcast_start_atがNoneの場合published_atがフォールバックとして使用される"""
        pub = datetime(2024, 6, 15, tzinfo=timezone.utc)
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Video", published_at=pub,
            duration_seconds=3600, broadcast_start_at=None,
        )
        mock_ytdlp.fetch_subtitle.return_value = (SubtitleData(
            video_id="vid1", language="ja", is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")],
        ), None)
        mock_segmentation.segment_video_from_entries.return_value = []

        service.sync_channel("UC1")
        row = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid1'").fetchone()
        assert row[0] == pub.isoformat()


class TestSyncAll:
    def test_multiple_channels(self, service, mock_ytdlp, mock_segmentation, db):
        db.save_channel("UC2", "Channel 2", "https://youtube.com/c/ch2")

        mock_ytdlp.list_channel_video_ids.return_value = []

        result = service.sync_all()
        assert result.already_synced == 0
        # list_channel_video_ids should be called for both channels
        assert mock_ytdlp.list_channel_video_ids.call_count == 2
