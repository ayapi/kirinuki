"""CLIコマンドのテスト"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.models.domain import (
    Channel,
    ChannelSummary,
    SearchResult,
    Segment,
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


class TestSearch:
    @patch("kirinuki.cli.main.create_app_context")
    def test_search_results(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = [
            SearchResult(
                video_title="Test Video",
                channel_name="Test Channel",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="テスト話題",
                youtube_url="https://www.youtube.com/watch?v=abc123&t=60",
                score=0.95,
            ),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "テスト"])
        assert result.exit_code == 0
        assert "Test Video" in result.output
        assert "youtube.com" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_search_no_results(self, mock_ctx, runner):
        mock_context = MagicMock()
        mock_context.search_service.search.return_value = []
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = runner.invoke(cli, ["search", "nothing"])
        assert result.exit_code == 0
        assert "該当" in result.output or "0" in result.output


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
