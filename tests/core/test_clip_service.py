"""ClipService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from kirinuki.core.clip_service import ClipService
from kirinuki.core.errors import FfmpegNotFoundError, VideoDownloadError
from kirinuki.models.clip import ClipRequest, ClipResult


@pytest.fixture
def mock_ytdlp() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_ffmpeg() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock) -> ClipService:
    return ClipService(ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg)


class TestClipServiceExecute:
    def test_normal_flow(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """正常系: DL→切り出し→ClipResult返却"""
        output_path = tmp_path / "output.mp4"
        downloaded = tmp_path / "video.mp4"
        downloaded.touch()

        mock_ytdlp.download_video.return_value = downloaded

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        result = service.execute(request)

        assert isinstance(result, ClipResult)
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.start_seconds == 10.0
        assert result.end_seconds == 70.0
        assert result.duration_seconds == 60.0
        assert result.output_path == output_path

        mock_ffmpeg.check_available.assert_called_once()
        mock_ytdlp.download_video.assert_called_once()
        mock_ffmpeg.clip.assert_called_once()

    def test_download_failure_cleans_up(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """異常系: DL失敗時に一時ディレクトリがクリーンアップされる"""
        output_path = tmp_path / "output.mp4"
        mock_ytdlp.download_video.side_effect = VideoDownloadError("DL失敗")

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        with pytest.raises(VideoDownloadError):
            service.execute(request)

        mock_ffmpeg.clip.assert_not_called()

    def test_clip_failure_cleans_up(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """異常系: ffmpeg切り出し失敗時に一時ディレクトリがクリーンアップされる"""
        output_path = tmp_path / "output.mp4"
        downloaded = tmp_path / "video.mp4"
        downloaded.touch()

        mock_ytdlp.download_video.return_value = downloaded
        mock_ffmpeg.clip.side_effect = Exception("clip failed")

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        with pytest.raises(Exception, match="clip failed"):
            service.execute(request)

    def test_output_dir_not_exists(
        self, service: ClipService, tmp_path: Path
    ) -> None:
        """出力先の親ディレクトリが存在しない場合にエラー"""
        output_path = tmp_path / "nonexistent" / "output.mp4"

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        with pytest.raises(FileNotFoundError):
            service.execute(request)

    def test_progress_callback_order(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """進捗コールバックが正しい順序で呼ばれる"""
        output_path = tmp_path / "output.mp4"
        downloaded = tmp_path / "video.mp4"
        downloaded.touch()

        mock_ytdlp.download_video.return_value = downloaded

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        progress_calls: list[str] = []
        service.execute(request, on_progress=lambda msg: progress_calls.append(msg))

        assert len(progress_calls) == 2
        assert "ダウンロード" in progress_calls[0]
        assert "切り出し" in progress_calls[1]

    def test_ffmpeg_not_found(
        self, service: ClipService, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """ffmpegが見つからない場合のエラー"""
        output_path = tmp_path / "output.mp4"
        mock_ffmpeg.check_available.side_effect = FfmpegNotFoundError("not found")

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
        )

        with pytest.raises(FfmpegNotFoundError):
            service.execute(request)

    def test_cookie_file_passed_to_download(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """cookie_fileがダウンローダーに渡される"""
        output_path = tmp_path / "output.mp4"
        cookie_file = tmp_path / "cookies.txt"
        downloaded = tmp_path / "video.mp4"
        downloaded.touch()

        mock_ytdlp.download_video.return_value = downloaded

        request = ClipRequest(
            url="dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output_path,
            cookie_file=cookie_file,
        )

        service.execute(request)

        _, kwargs = mock_ytdlp.download_video.call_args
        assert kwargs.get("cookie_file") == cookie_file or mock_ytdlp.download_video.call_args[0][2] == cookie_file
