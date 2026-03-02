"""YtdlpClient動画ダウンロード機能のテスト（モック使用）"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.core.errors import AuthenticationRequiredError, VideoDownloadError
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def client(tmp_path: Path) -> YtdlpClient:
    config = AppConfig(
        db_path=tmp_path / "data.db",
        cookie_file_path=tmp_path / "nonexistent_cookies.txt",
    )
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


class TestDownloadSection:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_section_success(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"id": "vid1"}

        output_path = tmp_path / "clip.mp4"
        # Simulate file creation by yt-dlp
        output_path.touch()

        result = client.download_section("vid1", 60.0, 120.0, output_path)
        assert result == output_path

        # Verify download_ranges was set in options
        call_args = mock_ydl_cls.call_args[0][0]
        assert "download_ranges" in call_args
        assert call_args.get("format_sort") == ["proto:https"]

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_section_with_cookie(
        self, mock_ydl_cls: MagicMock, tmp_path: Path
    ) -> None:
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(db_path=tmp_path / "data.db")
        c = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"id": "vid1"}

        output_path = tmp_path / "clip.mp4"
        output_path.touch()

        c.download_section("vid1", 60.0, 120.0, output_path, cookie_file=cookie_file)

        call_args = mock_ydl_cls.call_args[0][0]
        assert call_args.get("cookiefile") == str(cookie_file)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_section_failure(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError("section download failed")

        output_path = tmp_path / "clip.mp4"

        with pytest.raises(VideoDownloadError):
            client.download_section("vid1", 60.0, 120.0, output_path)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_section_auth_error_no_cookie(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        """認証エラーでCookieファイルがない場合はエラー"""
        import yt_dlp

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError(
            "Sign in to confirm you're not a bot"
        )

        output_path = tmp_path / "clip.mp4"

        with pytest.raises(AuthenticationRequiredError):
            client.download_section("vid1", 60.0, 120.0, output_path)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_section_auth_retry_with_cookie(
        self, mock_ydl_cls: MagicMock, tmp_path: Path
    ) -> None:
        """認証エラー時にCookieファイルがあれば自動リトライ"""
        import yt_dlp

        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        c = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        # 1回目: 認証エラー、2回目: 成功
        mock_ydl.extract_info.side_effect = [
            yt_dlp.DownloadError("Sign in to confirm you're not a bot"),
            {"id": "vid1"},
        ]

        output_path = tmp_path / "clip.mp4"
        output_path.touch()

        result = c.download_section("vid1", 60.0, 120.0, output_path)
        assert result == output_path
        assert mock_ydl.extract_info.call_count == 2

        # リトライ時にcookiefileが設定されていることを確認
        second_call_opts = mock_ydl_cls.call_args_list[1][0][0]
        assert second_call_opts.get("cookiefile") == str(cookie_file)
