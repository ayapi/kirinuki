"""CLIコマンドのテスト"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.models.domain import (
    Channel,
    ChannelSummary,
    MatchType,
    SearchResult,
    Segment,
    SkipReason,
    SyncResult,
    VideoSummary,
)


@pytest.fixture
def runner():
    return CliRunner()


class TestChannelAdd:
    @patch("kirinuki.cli.main.create_app_context")
    def test_add_channel(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.channel_service.register.return_value = Channel(
            channel_id="UC123", name="Test Channel", url="https://youtube.com/c/test"
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["channel", "add", "https://youtube.com/c/test"])
        assert result.exit_code == 0
        assert "UC123" in result.output or "Test Channel" in result.output


class TestChannelList:
    @patch("kirinuki.cli.main.create_app_context")
    def test_list_channels(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.channel_service.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC1", name="Ch1", url="https://youtube.com/c/ch1",
                video_count=5, last_synced_at=None
            ),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["channel", "list"])
        assert result.exit_code == 0
        assert "Ch1" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_list_empty(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.channel_service.list_channels.return_value = []
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["channel", "list"])
        assert result.exit_code == 0


class TestSync:
    @patch("kirinuki.cli.main.create_app_context")
    def test_sync_all(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=10, newly_synced=3, skipped=1
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "3" in result.output  # newly_synced


class TestSyncAuthErrors:
    @patch("kirinuki.cli.main.create_app_context")
    def test_auth_errors_show_cookie_hint(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=0, auth_errors=3,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "3" in result.output
        assert "cookie set" in result.output.lower() or "Cookie" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_unavailable_skipped_shown(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=0, unavailable_skipped=2,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "unavailable" in result.output.lower() or "スキップ" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_no_auth_errors_no_cookie_hint(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=0,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "cookie" not in result.output.lower()


class TestSyncSkipReasonOutput:
    @patch("kirinuki.cli.main.create_app_context")
    def test_skip_reasons_displayed(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=3,
            skip_reasons={
                SkipReason.NO_SUBTITLE_AVAILABLE: 2,
                SkipReason.PARSE_FAILED: 1,
            },
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "字幕なし: 2件" in result.output
        assert "パース失敗: 1件" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_no_skip_reasons_when_zero_skipped(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=3, skipped=0,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "字幕なし" not in result.output
        assert "パース失敗" not in result.output


class TestSyncNotLiveSkipOutput:
    @patch("kirinuki.cli.main.create_app_context")
    def test_not_live_skip_shown_in_summary(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=2, skipped=1,
            not_live_skipped=3,
            skip_reasons={
                SkipReason.NO_SUBTITLE_AVAILABLE: 1,
                SkipReason.NOT_LIVE_ARCHIVE: 3,
            },
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "配信アーカイブ以外" in result.output
        assert "3件" in result.output


class TestSyncRetrySegmentationOutput:
    @patch("kirinuki.cli.main.create_app_context")
    def test_retry_results_shown(self, mock_ctx, runner):
        """再試行結果がサマリーに表示される"""
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=0,
            segmentation_retried=3, segmentation_retry_failed=1,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "セグメンテーション再試行" in result.output
        assert "成功 3件" in result.output
        assert "失敗 1件" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_no_retry_results_when_zero(self, mock_ctx, runner):
        """再試行がない場合は表示しない"""
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=1, skipped=0,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "セグメンテーション再試行" not in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_retry_success_only(self, mock_ctx, runner):
        """再試行成功のみの場合も表示される"""
        mock_context = MagicMock()
        mock_context.sync_service.sync_all.return_value = SyncResult(
            already_synced=5, newly_synced=0, skipped=0,
            segmentation_retried=2, segmentation_retry_failed=0,
        )
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["sync"])
        assert result.exit_code == 0
        assert "セグメンテーション再試行" in result.output
        assert "成功 2件" in result.output


class TestUnavailableReset:
    @patch("kirinuki.cli.main.create_app_context")
    def test_reset_all(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.db.clear_all_unavailable.return_value = 5
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["unavailable", "reset"], input="y\n")
        assert result.exit_code == 0
        assert "5" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_reset_channel(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.db.clear_all_unavailable.return_value = 3
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["unavailable", "reset", "--channel", "UC1"])
        assert result.exit_code == 0
        assert "3" in result.output


class TestSearch:
    @patch("kirinuki.cli.main.create_app_context")
    def test_search_results(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "Test Video" in result.output
        assert "youtube.com" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_search_no_results(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "nothing"])
        assert result.exit_code == 0
        assert "該当" in result.output or "0" in result.output


class TestSearchMatchReason:
    @patch("kirinuki.cli.main.create_app_context")
    def test_keyword_match_shows_snippet(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
                match_type=MatchType.KEYWORD,
                snippet="マッチした字幕テキスト",
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "キーワード" in result.output
        assert "マッチした字幕テキスト" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_semantic_match_shows_similarity(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.85,
                match_type=MatchType.SEMANTIC,
                similarity=0.85,
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "セマンティック" in result.output
        assert "85%" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_hybrid_match_shows_both(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
                match_type=MatchType.HYBRID,
                snippet="マッチした字幕",
                similarity=0.9,
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "キーワード+セマンティック" in result.output
        assert "マッチした字幕" in result.output
        assert "90%" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_no_match_type_backward_compatible(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "Test Video" in result.output
        # match_type=Noneの場合、マッチ理由行は表示されない
        assert "キーワード" not in result.output
        assert "セマンティック" not in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_long_snippet_truncated(self, mock_ctx, runner):
        long_snippet = "あ" * 100
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
                match_type=MatchType.KEYWORD,
                snippet=long_snippet,
            ),
        ], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        # 80文字 + … で切り詰められている
        assert "あ" * 80 + "…" in result.output
        assert "あ" * 100 not in result.output


class TestSearchVideoIdOption:
    @patch("kirinuki.cli.main.create_app_context")
    def test_video_id_passed_to_service(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        runner.invoke(cli, ["search", "テスト", "--video-id", "vid1", "--video-id", "vid2"])
        mock_context.search_service.search.assert_called_once_with(
            "テスト", limit=10, video_ids=["vid1", "vid2"]
        )

    @patch("kirinuki.cli.main.create_app_context")
    def test_no_video_id_passes_none(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([], [])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        runner.invoke(cli, ["search", "テスト"])
        mock_context.search_service.search.assert_called_once_with(
            "テスト", limit=10, video_ids=None
        )

    @patch("kirinuki.cli.main.create_app_context")
    def test_warnings_displayed(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = ([], ["動画ID 'vid_x' はデータベースに存在しません"])
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト", "--video-id", "vid_x"])
        assert result.exit_code == 0


class TestSegments:
    @patch("kirinuki.cli.main.create_app_context")
    def test_list_segments(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.segmentation_service.list_segments.return_value = [
            Segment(id=1, video_id="vid1", start_ms=0, end_ms=60000, summary="自己紹介"),
            Segment(id=2, video_id="vid1", start_ms=60000, end_ms=120000, summary="ゲーム開始"),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["segments", "vid1"])
        assert result.exit_code == 0
        assert "自己紹介" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_segments_include_youtube_url(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.segmentation_service.list_segments.return_value = [
            Segment(id=1, video_id="vid1", start_ms=90000, end_ms=180000, summary="話題A"),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["segments", "vid1"])
        assert result.exit_code == 0
        assert "https://www.youtube.com/watch?v=vid1&t=90" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_segments_empty_no_url(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.segmentation_service.list_segments.return_value = []
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["segments", "vid1"])
        assert result.exit_code == 0
        assert "セグメントはありません" in result.output
        assert "youtube.com" not in result.output


class TestHelp:
    def test_main_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_channel_help(self, runner):
        result = runner.invoke(cli, ["channel", "--help"])
        assert result.exit_code == 0

    def test_sync_help(self, runner):
        result = runner.invoke(cli, ["sync", "--help"])
        assert result.exit_code == 0

    def test_search_help(self, runner):
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
