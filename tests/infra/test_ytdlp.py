"""yt-dlpクライアントのテスト（モック使用）"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def client(tmp_path):
    config = AppConfig(db_path=tmp_path / "data.db")
    return YtdlpClient(config)


class TestListChannelVideoIds:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_flat_extraction(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "vid1", "title": "Video 1"},
                {"id": "vid2", "title": "Video 2"},
                {"id": "vid3", "title": "Video 3"},
            ]
        }
        ids = client.list_channel_video_ids("https://youtube.com/c/test")
        assert ids == ["vid1", "vid2", "vid3"]

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_empty_channel(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"entries": []}
        ids = client.list_channel_video_ids("https://youtube.com/c/empty")
        assert ids == []


class TestFetchVideoMetadata:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_metadata(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Test Video",
            "upload_date": "20240101",
            "duration": 3600,
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.video_id == "vid1"
        assert meta.title == "Test Video"
        assert meta.duration_seconds == 3600


class TestFetchSubtitle:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_manual_subtitle(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Test",
            "duration": 100,
            "subtitles": {
                "ja": [
                    {"ext": "json3", "url": "http://example.com/sub.json3"}
                ]
            },
            "automatic_captions": {},
            "requested_subtitles": {
                "ja": {
                    "ext": "json3",
                    "data": '{"events":[{"tStartMs":0,"dDurationMs":5000,"segs":[{"utf8":"こんにちは"}]},{"tStartMs":5000,"dDurationMs":3000,"segs":[{"utf8":"テスト"}]}]}',
                }
            },
        }
        result = client.fetch_subtitle("vid1")
        assert result is not None
        assert result.language == "ja"
        assert not result.is_auto_generated
        assert len(result.entries) == 2
        assert result.entries[0].text == "こんにちは"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_no_subtitle_returns_none(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Test",
            "duration": 100,
            "subtitles": {},
            "automatic_captions": {},
            "requested_subtitles": None,
        }
        result = client.fetch_subtitle("vid1")
        assert result is None


class TestCookieAuth:
    def test_cookie_option_set(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        c = YtdlpClient(config)
        opts = c._base_opts()
        assert opts.get("cookiefile") == str(cookie_file)

    def test_no_cookie_option(self, client):
        opts = client._base_opts()
        assert "cookiefile" not in opts
