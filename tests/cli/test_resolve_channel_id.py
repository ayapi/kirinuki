"""resolve_channel_id のユニットテスト"""

from unittest.mock import MagicMock

import click
import pytest

from kirinuki.cli.resolve import resolve_channel_id
from kirinuki.models.domain import ChannelSummary


@pytest.fixture
def mock_db():
    return MagicMock()


class TestResolveChannelIdExplicit:
    """チャンネルIDが明示指定された場合"""

    def test_returns_specified_id(self, mock_db):
        result = resolve_channel_id("UC_EXPLICIT", mock_db)
        assert result == "UC_EXPLICIT"

    def test_does_not_query_db(self, mock_db):
        resolve_channel_id("UC_EXPLICIT", mock_db)
        mock_db.list_channels.assert_not_called()


class TestResolveChannelIdSingleChannel:
    """登録チャンネルが1つの場合"""

    def test_returns_single_channel_id(self, mock_db):
        mock_db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_SINGLE",
                name="唯一のチャンネル",
                url="https://youtube.com/c/single",
                video_count=5,
            ),
        ]
        result = resolve_channel_id(None, mock_db)
        assert result == "UC_SINGLE"

    def test_outputs_notification_to_stderr(self, mock_db, capsys):
        mock_db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_SINGLE",
                name="唯一のチャンネル",
                url="https://youtube.com/c/single",
                video_count=5,
            ),
        ]
        resolve_channel_id(None, mock_db)
        captured = capsys.readouterr()
        assert "唯一のチャンネル" in captured.err
        assert "UC_SINGLE" in captured.err


class TestResolveChannelIdNoChannels:
    """登録チャンネルが0件の場合"""

    def test_raises_usage_error(self, mock_db):
        mock_db.list_channels.return_value = []
        with pytest.raises(click.UsageError) as exc_info:
            resolve_channel_id(None, mock_db)
        assert "登録されていません" in str(exc_info.value)

    def test_error_message_suggests_add_command(self, mock_db):
        mock_db.list_channels.return_value = []
        with pytest.raises(click.UsageError) as exc_info:
            resolve_channel_id(None, mock_db)
        assert "channel add" in str(exc_info.value)


class TestResolveChannelIdMultipleChannels:
    """登録チャンネルが複数の場合"""

    def test_raises_usage_error(self, mock_db):
        mock_db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_A",
                name="チャンネルA",
                url="https://youtube.com/c/a",
                video_count=3,
            ),
            ChannelSummary(
                channel_id="UC_B",
                name="チャンネルB",
                url="https://youtube.com/c/b",
                video_count=7,
            ),
        ]
        with pytest.raises(click.UsageError):
            resolve_channel_id(None, mock_db)

    def test_error_message_lists_channels(self, mock_db):
        mock_db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_A",
                name="チャンネルA",
                url="https://youtube.com/c/a",
                video_count=3,
            ),
            ChannelSummary(
                channel_id="UC_B",
                name="チャンネルB",
                url="https://youtube.com/c/b",
                video_count=7,
            ),
        ]
        with pytest.raises(click.UsageError) as exc_info:
            resolve_channel_id(None, mock_db)
        error_msg = str(exc_info.value)
        assert "チャンネルA" in error_msg
        assert "UC_A" in error_msg
        assert "チャンネルB" in error_msg
        assert "UC_B" in error_msg
