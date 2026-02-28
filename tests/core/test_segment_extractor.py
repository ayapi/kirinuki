"""SegmentExtractorServiceのテスト（全依存モック化）"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kirinuki.core.errors import (
    InvalidURLError,
    TimeRangeError,
)
from kirinuki.core.segment_extractor import SegmentExtractorServiceImpl
from kirinuki.infra.ytdlp_client import VideoMeta
from kirinuki.models.clip import ClipRequest


def _make_service(
    ytdlp: MagicMock | None = None,
    ffmpeg: MagicMock | None = None,
) -> SegmentExtractorServiceImpl:
    return SegmentExtractorServiceImpl(
        ytdlp_client=ytdlp or MagicMock(),
        ffmpeg_client=ffmpeg or MagicMock(),
    )


def _video_meta(duration: int = 3600) -> VideoMeta:
    return VideoMeta(
        video_id="dQw4w9WgXcQ",
        title="Test Video",
        published_at=None,
        duration_seconds=duration,
    )


class TestExtractSuccess:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.touch()
        ytdlp.download_video.return_value = downloaded

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
            temp_dir=tmp_path / "temp",
        )

        result = service.extract(request)

        assert result.video_id == "dQw4w9WgXcQ"
        assert result.start_seconds == 10.0
        assert result.end_seconds == 70.0
        assert result.duration_seconds == 60.0
        assert result.output_path == output
        ffmpeg.check_available.assert_called_once()
        ytdlp.fetch_video_metadata.assert_called_once_with("dQw4w9WgXcQ")
        ytdlp.download_video.assert_called_once()
        ffmpeg.clip.assert_called_once()

    def test_start_only_uses_duration_as_end(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=120)
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.touch()
        ytdlp.download_video.return_value = downloaded

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=30.0,
            output_path=output,
            temp_dir=tmp_path / "temp",
        )

        result = service.extract(request)
        assert result.start_seconds == 30.0
        assert result.end_seconds == 120.0

    def test_end_only_uses_zero_as_start(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=120)
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.touch()
        ytdlp.download_video.return_value = downloaded

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            end_seconds=60.0,
            output_path=output,
            temp_dir=tmp_path / "temp",
        )

        result = service.extract(request)
        assert result.start_seconds == 0.0
        assert result.end_seconds == 60.0

    def test_auto_generated_output_path(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.touch()
        ytdlp.download_video.return_value = downloaded

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            temp_dir=tmp_path / "temp",
        )

        result = service.extract(request)
        assert "dQw4w9WgXcQ" in str(result.output_path)
        assert str(result.output_path).endswith(".mp4")


class TestExtractValidation:
    def test_invalid_url(self) -> None:
        service = _make_service()
        request = ClipRequest(
            url="https://example.com/not-youtube",
            start_seconds=0.0,
            end_seconds=10.0,
        )
        with pytest.raises(InvalidURLError):
            service.extract(request)

    def test_end_exceeds_duration(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=60)
        ffmpeg = MagicMock()

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=0.0,
            end_seconds=120.0,
        )
        with pytest.raises(TimeRangeError):
            service.extract(request)

    def test_start_exceeds_duration(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=60)
        ffmpeg = MagicMock()

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=70.0,
        )
        with pytest.raises(TimeRangeError):
            service.extract(request)


class TestCleanup:
    def test_temp_dir_cleaned_on_success(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()
        created_files: list[Path] = []

        def fake_download(video_id, output_dir, cookie_file=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            f = output_dir / "dQw4w9WgXcQ.mp4"
            f.touch()
            created_files.append(f)
            return f

        ytdlp.download_video.side_effect = fake_download

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
        )

        service.extract(request)
        # ダウンロードされたファイルはクリーンアップされていること
        assert len(created_files) == 1
        assert not created_files[0].exists()

    def test_temp_dir_cleaned_on_error(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()

        def fake_download(video_id, output_dir, cookie_file=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            f = output_dir / "dQw4w9WgXcQ.mp4"
            f.touch()
            return f

        ytdlp.download_video.side_effect = fake_download
        ffmpeg.clip.side_effect = RuntimeError("clip failed")

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
        )

        with pytest.raises(RuntimeError):
            service.extract(request)


class TestCookiePassthrough:
    def test_cookie_file_passed_to_download(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()
        downloaded = tmp_path / "temp" / "dQw4w9WgXcQ.mp4"
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.touch()
        ytdlp.download_video.return_value = downloaded

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        cookie = tmp_path / "cookies.txt"
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
            cookie_file=cookie,
            temp_dir=tmp_path / "temp",
        )

        service.extract(request)
        ytdlp.download_video.assert_called_once_with(
            "dQw4w9WgXcQ",
            tmp_path / "temp",
            cookie_file=cookie,
        )
