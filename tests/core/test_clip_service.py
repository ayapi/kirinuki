"""ClipService のユニットテスト"""

import threading
import time
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
    return ClipService(ytdlp_client=mock_ytdlp, max_workers=4)


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
        # Parallel execution means order is nondeterministic;
        # verify all progress markers are present regardless of order
        joined = "\n".join(progress_calls)
        assert "[1/3]" in joined
        assert "[2/3]" in joined
        assert "[3/3]" in joined

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


class TestClipServiceParallel:
    def test_parallel_execution(self, mock_ytdlp: MagicMock, tmp_path: Path) -> None:
        """複数クリップがThreadPoolExecutorで並列実行される"""
        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def slow_download(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            time.sleep(0.05)
            with lock:
                current_concurrent -= 1

        mock_ytdlp.download_section.side_effect = slow_download
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=4)

        request = MultiClipRequest(
            video_id="test",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=float(i * 10), end_seconds=float(i * 10 + 10))
                for i in range(4)
            ],
        )

        result = service.execute(request)

        assert result.success_count == 4
        assert max_concurrent >= 2  # At least 2 ran concurrently

    def test_max_workers_limits_concurrency(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """max_workersが並列数を制限する"""
        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def slow_download(*args, **kwargs):
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            time.sleep(0.05)
            with lock:
                current_concurrent -= 1

        mock_ytdlp.download_section.side_effect = slow_download
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=2)

        request = MultiClipRequest(
            video_id="test",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=float(i * 10), end_seconds=float(i * 10 + 10))
                for i in range(4)
            ],
        )

        result = service.execute(request)

        assert result.success_count == 4
        assert max_concurrent <= 2

    def test_outcome_order_preserved(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """並列実行でもoutcomesの順序が入力と一致する"""
        delays = [0.1, 0.0, 0.05]  # Different completion order

        def download_with_delay(*args, **kwargs):
            start = args[1]
            idx = int(start / 10)
            time.sleep(delays[idx])

        mock_ytdlp.download_section.side_effect = download_with_delay
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=4)

        ranges = [
            TimeRange(start_seconds=float(i * 10), end_seconds=float(i * 10 + 10))
            for i in range(3)
        ]
        request = MultiClipRequest(
            video_id="test",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=ranges,
        )

        result = service.execute(request)

        assert result.success_count == 3
        for i, outcome in enumerate(result.outcomes):
            assert outcome.range == ranges[i]

    def test_auth_error_in_parallel(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """並列実行でもAuthenticationRequiredErrorは即座に伝播する"""

        def download_with_auth_error(*args, **kwargs):
            start = args[1]
            if start == 10.0:
                raise AuthenticationRequiredError("認証が必要です")
            time.sleep(0.1)

        mock_ytdlp.download_section.side_effect = download_with_auth_error
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=4)

        request = MultiClipRequest(
            video_id="test",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=float(i * 10), end_seconds=float(i * 10 + 10))
                for i in range(3)
            ],
        )

        with pytest.raises(AuthenticationRequiredError):
            service.execute(request)

    def test_sequential_fallback_with_max_workers_1(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """max_workers=1でも正常に動作する（逐次実行）"""
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=1)

        request = MultiClipRequest(
            video_id="test",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=0.0, end_seconds=10.0),
                TimeRange(start_seconds=10.0, end_seconds=20.0),
                TimeRange(start_seconds=20.0, end_seconds=30.0),
            ],
        )

        result = service.execute(request)

        assert result.success_count == 3
        assert result.failure_count == 0
        assert mock_ytdlp.download_section.call_count == 3
