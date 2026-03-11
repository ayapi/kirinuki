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

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
        )

        result = service.extract(request)

        assert result.video_id == "dQw4w9WgXcQ"
        assert result.start_seconds == 10.0
        assert result.end_seconds == 70.0
        assert result.duration_seconds == 60.0
        assert result.output_path == output
        ffmpeg.check_available.assert_called_once()
        ytdlp.fetch_video_metadata.assert_called_once_with("dQw4w9WgXcQ")
        ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            10.0,
            70.0,
            output,
            cookie_file=None,
        )

    def test_start_only_uses_duration_as_end(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=120)

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=30.0,
            output_path=output,
        )

        result = service.extract(request)
        assert result.start_seconds == 30.0
        assert result.end_seconds == 120.0

    def test_end_only_uses_zero_as_start(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta(duration=120)

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            end_seconds=60.0,
            output_path=output,
        )

        result = service.extract(request)
        assert result.start_seconds == 0.0
        assert result.end_seconds == 60.0

    def test_auto_generated_output_path(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
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


class TestCookiePassthrough:
    def test_cookie_file_passed_to_download_section(self, tmp_path: Path) -> None:
        ytdlp = MagicMock()
        ffmpeg = MagicMock()
        ytdlp.fetch_video_metadata.return_value = _video_meta()

        service = _make_service(ytdlp=ytdlp, ffmpeg=ffmpeg)
        cookie = tmp_path / "cookies.txt"
        output = tmp_path / "output.mp4"
        request = ClipRequest(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            start_seconds=10.0,
            end_seconds=70.0,
            output_path=output,
            cookie_file=cookie,
        )

        service.extract(request)
        ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            10.0,
            70.0,
            output,
            cookie_file=cookie,
        )
