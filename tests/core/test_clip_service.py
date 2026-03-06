"""ClipService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from kirinuki.core.clip_service import ClipService
from kirinuki.core.errors import ClipError, VideoDownloadError
from kirinuki.models.clip import (
    MultiClipRequest,
    MultiClipResult,
    TimeRange,
)


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
    def test_single_range_success(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """単一範囲の正常系: DL1回 + ffmpegカット1回"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        result = service.execute(request)

        assert isinstance(result, MultiClipResult)
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.success_count == 1
        assert result.failure_count == 0
        mock_ytdlp.download_video.assert_called_once()
        mock_ffmpeg.clip.assert_called_once_with(
            downloaded, tmp_path / "video.mp4", 60.0, 120.0
        )

    def test_multiple_ranges_single_download(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """複数範囲でもDLは1回だけ"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
                TimeRange(start_seconds=300.0, end_seconds=360.0),
            ],
        )

        result = service.execute(request)

        assert result.success_count == 3
        assert result.failure_count == 0
        mock_ytdlp.download_video.assert_called_once()
        assert mock_ffmpeg.clip.call_count == 3

    def test_partial_failure(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """3範囲中1つのffmpegカットが失敗、残り2つは成功"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        mock_ffmpeg.clip.side_effect = [
            None,
            ClipError("ffmpegエラー"),
            None,
        ]

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
                TimeRange(start_seconds=300.0, end_seconds=360.0),
            ],
        )

        result = service.execute(request)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.outcomes[0].output_path is not None
        assert result.outcomes[1].output_path is None
        assert result.outcomes[1].error is not None
        assert result.outcomes[2].output_path is not None

    def test_output_dir_auto_created(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """出力先ディレクトリが存在しない場合に自動作成される"""
        output_dir = tmp_path / "new_subdir" / "output"
        assert not output_dir.exists()

        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=output_dir,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        service.execute(request)
        assert output_dir.exists()

    def test_progress_callback(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """進捗コールバックがDL通知+処理番号で呼ばれる"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
                TimeRange(start_seconds=300.0, end_seconds=360.0),
            ],
        )

        progress_calls: list[str] = []
        service.execute(request, on_progress=lambda msg: progress_calls.append(msg))

        assert len(progress_calls) == 4  # DL通知 + 3区間
        assert "ダウンロード" in progress_calls[0]
        assert "[1/3]" in progress_calls[1]
        assert "[2/3]" in progress_calls[2]
        assert "[3/3]" in progress_calls[3]

    def test_cookie_file_passed(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """cookie_fileがdownload_videoに渡される"""
        cookie_file = tmp_path / "cookies.txt"
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            cookie_file=cookie_file,
        )

        service.execute(request)

        _, kwargs = mock_ytdlp.download_video.call_args
        assert kwargs.get("cookie_file") == cookie_file

    def test_output_path_numbering_single(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """単一範囲のファイル名に連番なし"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        service.execute(request)

        clip_call = mock_ffmpeg.clip.call_args
        output_path_arg = clip_call[0][1]
        assert output_path_arg == tmp_path / "video.mp4"

    def test_output_path_numbering_multiple(
        self, service: ClipService, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """複数範囲のファイル名に連番あり"""
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        mock_ytdlp.download_video.return_value = downloaded

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
            ],
        )

        service.execute(request)

        calls = mock_ffmpeg.clip.call_args_list
        first_output = calls[0][0][1]
        assert first_output == tmp_path / "video1.mp4"
        second_output = calls[1][0][1]
        assert second_output == tmp_path / "video2.mp4"
