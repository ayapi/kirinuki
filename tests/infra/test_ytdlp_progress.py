"""YtdlpClient download_section の on_progress コールバックテスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def client(tmp_path: Path) -> YtdlpClient:
    config = AppConfig(
        db_path=tmp_path / "data.db",
        cookie_file_path=tmp_path / "nonexistent_cookies.txt",
    )
    return YtdlpClient(config)


class TestDownloadSectionOnProgress:
    @staticmethod
    def _setup_mock(mock_ydl_cls: MagicMock, output_path: Path) -> MagicMock:
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        def _fake_download(*args, **kwargs):
            output_path.write_bytes(b"\x00" * 8)
            return {"id": "vid1"}

        mock_ydl.extract_info.side_effect = _fake_download
        return mock_ydl

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_progress_hooks_set_when_on_progress_provided(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        """on_progress指定時にprogress_hooksが設定される"""
        output_path = tmp_path / "clip.mp4"
        self._setup_mock(mock_ydl_cls, output_path)
        callback = MagicMock()

        client.download_section(
            "vid1", 60.0, 120.0, output_path, on_progress=callback
        )

        call_args = mock_ydl_cls.call_args[0][0]
        assert "progress_hooks" in call_args
        assert len(call_args["progress_hooks"]) == 1

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_progress_hooks_not_set_when_no_callback(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        """on_progress未指定時にprogress_hooksが設定されない"""
        output_path = tmp_path / "clip.mp4"
        self._setup_mock(mock_ydl_cls, output_path)

        client.download_section("vid1", 60.0, 120.0, output_path)

        call_args = mock_ydl_cls.call_args[0][0]
        assert "progress_hooks" not in call_args

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_progress_hook_forwards_dict_to_callback(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        """progress_hooksに設定されたフック関数がcallbackにdictを転送する"""
        output_path = tmp_path / "clip.mp4"
        self._setup_mock(mock_ydl_cls, output_path)
        callback = MagicMock()

        client.download_section(
            "vid1", 60.0, 120.0, output_path, on_progress=callback
        )

        # Get the hook function that was registered
        call_args = mock_ydl_cls.call_args[0][0]
        hook_fn = call_args["progress_hooks"][0]

        # Simulate yt-dlp calling the hook
        progress_dict = {
            "status": "downloading",
            "downloaded_bytes": 1000,
            "total_bytes": 5000,
        }
        hook_fn(progress_dict)

        callback.assert_called_once_with(progress_dict)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_progress_hooks_with_explicit_cookie_file(
        self, mock_ydl_cls: MagicMock, client: YtdlpClient, tmp_path: Path
    ) -> None:
        """cookie_file引数とon_progressを同時に指定できる"""
        output_path = tmp_path / "clip.mp4"
        self._setup_mock(mock_ydl_cls, output_path)
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        callback = MagicMock()

        client.download_section(
            "vid1", 60.0, 120.0, output_path,
            cookie_file=cookie_file,
            on_progress=callback,
        )

        call_args = mock_ydl_cls.call_args[0][0]
        assert "progress_hooks" in call_args
        assert call_args.get("cookiefile") == str(cookie_file)
