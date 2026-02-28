"""YtdlpClient動画ダウンロード機能のテスト（モック使用）"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.core.errors import AuthenticationRequiredError, VideoDownloadError
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def client(tmp_path: Path) -> YtdlpClient:
    config = AppConfig(db_path=tmp_path / "data.db")
    return YtdlpClient(config)


class TestDownloadVideo:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_success(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        expected_path = str(tmp_path / "vid1.mp4")
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "requested_downloads": [{"filepath": expected_path}],
        }

        result = client.download_video("vid1", tmp_path)
        assert result == Path(expected_path)
        mock_ydl.extract_info.assert_called_once()

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_with_cookie(self, mock_ydl_cls: MagicMock, tmp_path: Path) -> None:
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(db_path=tmp_path / "data.db")
        c = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        expected_path = str(tmp_path / "vid1.mp4")
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "requested_downloads": [{"filepath": expected_path}],
        }

        result = c.download_video("vid1", tmp_path, cookie_file=cookie_file)
        assert result == Path(expected_path)

        # cookiefile option should be set
        call_args = mock_ydl_cls.call_args[0][0]
        assert call_args.get("cookiefile") == str(cookie_file)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_failure(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError("download failed")

        with pytest.raises(VideoDownloadError):
            client.download_video("vid1", tmp_path)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_authentication_error(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError(
            "Sign in to confirm you're not a bot"
        )

        with pytest.raises(AuthenticationRequiredError):
            client.download_video("vid1", tmp_path)
