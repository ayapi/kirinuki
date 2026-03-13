"""ClipService の ClipProgress コールバック拡張テスト"""

from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from kirinuki.core.clip_service import ClipService
from kirinuki.core.errors import VideoDownloadError
from kirinuki.models.clip import (
    ClipPhase,
    ClipProgress,
    MultiClipRequest,
    TimeRange,
)


@pytest.fixture
def mock_ytdlp() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_ffmpeg() -> MagicMock:
    return MagicMock()


class TestClipProgressCallback:
    def test_on_progress_receives_clip_progress(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """on_progressがClipProgressオブジェクトで呼ばれる"""
        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        # Should have at least reencoding and done phases
        assert len(progress_calls) >= 2
        assert all(isinstance(p, ClipProgress) for p in progress_calls)

    def test_reencoding_phase_emitted(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """再エンコード開始時にREENCODINGフェーズが通知される"""
        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        reencoding = [p for p in progress_calls if p.phase == ClipPhase.REENCODING]
        assert len(reencoding) == 1
        assert reencoding[0].clip_index == 0

    def test_done_phase_emitted(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """完了時にDONEフェーズが通知される"""
        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        done = [p for p in progress_calls if p.phase == ClipPhase.DONE]
        assert len(done) == 1
        assert done[0].clip_index == 0

    def test_done_without_ffmpeg(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """ffmpegなしの場合はダウンロード後に直接DONEが通知される"""
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=4)
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        phases = [p.phase for p in progress_calls]
        assert ClipPhase.DONE in phases
        assert ClipPhase.REENCODING not in phases

    def test_ytdlp_progress_hooks_dict_converted(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """yt-dlpのprogress_hooks dictがClipProgressに変換される"""

        def fake_download(*args, **kwargs):
            # Simulate yt-dlp calling the on_progress callback
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress({
                    "status": "downloading",
                    "downloaded_bytes": 5_000_000,
                    "total_bytes": 10_000_000,
                    "speed": 2_000_000.0,
                    "eta": 5,
                })

        mock_ytdlp.download_section.side_effect = fake_download

        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        downloading = [p for p in progress_calls if p.phase == ClipPhase.DOWNLOADING]
        assert len(downloading) >= 1
        p = downloading[0]
        assert p.clip_index == 0
        assert p.downloaded_bytes == 5_000_000
        assert p.total_bytes == 10_000_000
        assert p.speed == 2_000_000.0
        assert p.eta == 5
        # percent = downloaded / total * 100 = 50.0
        assert p.percent == 50.0

    def test_ytdlp_total_bytes_estimate_fallback(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """total_bytesがない場合にtotal_bytes_estimateがフォールバック使用される"""

        def fake_download(*args, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress({
                    "status": "downloading",
                    "downloaded_bytes": 3_000_000,
                    "total_bytes_estimate": 10_000_000,
                })

        mock_ytdlp.download_section.side_effect = fake_download

        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        downloading = [p for p in progress_calls if p.phase == ClipPhase.DOWNLOADING]
        assert len(downloading) >= 1
        p = downloading[0]
        assert p.total_bytes == 10_000_000
        assert p.percent == 30.0

    def test_ytdlp_finished_status_ignored(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """yt-dlpのfinishedステータスはDOWNLOADINGの終了を示す中間状態"""

        def fake_download(*args, **kwargs):
            on_progress = kwargs.get("on_progress")
            if on_progress:
                on_progress({"status": "finished"})

        mock_ytdlp.download_section.side_effect = fake_download

        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        # "finished" from yt-dlp should NOT be emitted as DONE
        # (DONE is only emitted after reencode completes)
        phases = [p.phase for p in progress_calls]
        # There should be exactly 1 DONE (from our own done notification after reencode)
        assert phases.count(ClipPhase.DONE) == 1

    def test_multi_clip_progress_indices(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """マルチクリップでclip_indexが正しく設定される"""
        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=0.0, end_seconds=10.0),
                TimeRange(start_seconds=10.0, end_seconds=20.0),
                TimeRange(start_seconds=20.0, end_seconds=30.0),
            ],
        )

        progress_calls: list[ClipProgress] = []
        service.execute(request, on_progress=lambda p: progress_calls.append(p))

        indices = {p.clip_index for p in progress_calls}
        assert indices == {0, 1, 2}

    def test_on_progress_none_compatible(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """on_progress=Noneでも正常動作（既存互換）"""
        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        result = service.execute(request, on_progress=None)
        assert result.success_count == 1

    def test_error_phase_emitted_on_failure(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """個別クリップ失敗時にERRORフェーズが通知される"""
        mock_ytdlp.download_section.side_effect = VideoDownloadError("ダウンロード失敗")

        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        progress_calls: list[ClipProgress] = []
        result = service.execute(request, on_progress=lambda p: progress_calls.append(p))

        assert result.failure_count == 1
        error_phases = [p for p in progress_calls if p.phase == ClipPhase.ERROR]
        assert len(error_phases) == 1
        assert error_phases[0].clip_index == 0

    def test_error_phase_emitted_in_multi_clip(
        self, mock_ytdlp: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        """マルチクリップで部分失敗時にERRORフェーズが正しく通知される"""

        def fail_on_clip_1(*args, **kwargs):
            # args[1] is start_seconds: 10.0 for clip index 1
            if args[1] == 10.0:
                raise VideoDownloadError("失敗")

        mock_ytdlp.download_section.side_effect = fail_on_clip_1

        service = ClipService(
            ytdlp_client=mock_ytdlp, ffmpeg_client=mock_ffmpeg, max_workers=4
        )
        request = MultiClipRequest(
            video_id="vid1",
            filename="clip.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=0.0, end_seconds=10.0),
                TimeRange(start_seconds=10.0, end_seconds=20.0),
                TimeRange(start_seconds=20.0, end_seconds=30.0),
            ],
        )

        progress_calls: list[ClipProgress] = []
        result = service.execute(request, on_progress=lambda p: progress_calls.append(p))

        assert result.success_count == 2
        assert result.failure_count == 1

        error_phases = [p for p in progress_calls if p.phase == ClipPhase.ERROR]
        assert len(error_phases) == 1
        assert error_phases[0].clip_index == 1
