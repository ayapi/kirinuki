"""ClipService のユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from kirinuki.core.clip_service import ClipService
from kirinuki.core.errors import AuthenticationRequiredError, ClipError, VideoDownloadError
from kirinuki.models.clip import (
    MultiClipRequest,
    MultiClipResult,
    TimeRange,
)


@pytest.fixture
def mock_ytdlp() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_ytdlp: MagicMock) -> ClipService:
    return ClipService(ytdlp_client=mock_ytdlp)


class TestClipServiceExecute:
    def test_single_range_success(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """単一範囲の正常系: download_section1回"""
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
        mock_ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            60.0,
            120.0,
            tmp_path / "video.mp4",
            cookie_file=None,
        )

    def test_multiple_ranges_individual_downloads(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """複数範囲では各範囲ごとにdownload_sectionが呼ばれる"""
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
        assert mock_ytdlp.download_section.call_count == 3

    def test_partial_failure(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """3範囲中1つのdownload_sectionが失敗、残り2つは成功"""
        mock_ytdlp.download_section.side_effect = [
            None,
            VideoDownloadError("ダウンロードエラー"),
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

    def test_auth_error_propagates(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """認証エラーは個別失敗にせず即座に再送出される"""
        mock_ytdlp.download_section.side_effect = AuthenticationRequiredError("認証が必要です")

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
            ],
        )

        with pytest.raises(AuthenticationRequiredError):
            service.execute(request)

    def test_output_dir_auto_created(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """出力先ディレクトリが存在しない場合に自動作成される"""
        output_dir = tmp_path / "new_subdir" / "output"
        assert not output_dir.exists()

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=output_dir,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        service.execute(request)
        assert output_dir.exists()

    def test_progress_callback(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """進捗コールバックが各範囲で呼ばれる"""
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

        assert len(progress_calls) == 3
        assert "[1/3]" in progress_calls[0]
        assert "[2/3]" in progress_calls[1]
        assert "[3/3]" in progress_calls[2]

    def test_cookie_file_passed(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """cookie_fileがdownload_sectionに渡される"""
        cookie_file = tmp_path / "cookies.txt"

        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            cookie_file=cookie_file,
        )

        service.execute(request)

        _, kwargs = mock_ytdlp.download_section.call_args
        assert kwargs.get("cookie_file") == cookie_file

    def test_output_path_numbering_single(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """単一範囲のファイル名に連番なし"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        service.execute(request)

        call_args = mock_ytdlp.download_section.call_args
        output_path_arg = call_args[0][3]
        assert output_path_arg == tmp_path / "video.mp4"

    def test_output_path_numbering_multiple(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """複数範囲のファイル名に連番あり"""
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

        calls = mock_ytdlp.download_section.call_args_list
        first_output = calls[0][0][3]
        assert first_output == tmp_path / "video1.mp4"
        second_output = calls[1][0][3]
        assert second_output == tmp_path / "video2.mp4"
