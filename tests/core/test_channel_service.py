"""チャンネル管理サービスのテスト"""

from unittest.mock import MagicMock

import pytest

from kirinuki.core.channel_service import ChannelService
from kirinuki.infra.database import Database


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    return database


@pytest.fixture
def mock_ytdlp():
    return MagicMock()


@pytest.fixture
def service(db, mock_ytdlp):
    return ChannelService(db=db, ytdlp_client=mock_ytdlp)


class TestRegister:
    def test_register_channel(self, service, mock_ytdlp):
        mock_ytdlp.resolve_channel_name.return_value = ("UC123", "Test Channel")
        ch = service.register("https://youtube.com/c/test")
        assert ch.channel_id == "UC123"
        assert ch.name == "Test Channel"

    def test_duplicate_register(self, service, mock_ytdlp, db):
        mock_ytdlp.resolve_channel_name.return_value = ("UC123", "Test Channel")
        service.register("https://youtube.com/c/test")
        # 2回目は既存チャンネルを返す
        ch = service.register("https://youtube.com/c/test")
        assert ch.channel_id == "UC123"


class TestListChannels:
    def test_empty(self, service):
        assert service.list_channels() == []

    def test_with_channels(self, service, mock_ytdlp):
        mock_ytdlp.resolve_channel_name.side_effect = [
            ("UC1", "Ch1"),
            ("UC2", "Ch2"),
        ]
        service.register("https://youtube.com/c/ch1")
        service.register("https://youtube.com/c/ch2")
        channels = service.list_channels()
        assert len(channels) == 2


class TestListVideos:
    def test_empty(self, service):
        videos = service.list_videos("UC_NONEXIST")
        assert videos == []

    def test_with_videos(self, service, mock_ytdlp, db):
        mock_ytdlp.resolve_channel_name.return_value = ("UC1", "Ch1")
        service.register("https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        videos = service.list_videos("UC1")
        assert len(videos) == 1
