"""切り抜き機能の例外クラスのテスト"""

from kirinuki.core.errors import (
    AuthenticationRequiredError,
    ClipError,
    FfmpegNotFoundError,
    InvalidURLError,
    SegmentExtractorError,
    TimeRangeError,
    VideoDownloadError,
)


class TestSegmentExtractorErrorHierarchy:
    def test_base_error(self) -> None:
        err = SegmentExtractorError("base error")
        assert str(err) == "base error"
        assert isinstance(err, Exception)

    def test_invalid_url_error(self) -> None:
        err = InvalidURLError("invalid url")
        assert isinstance(err, SegmentExtractorError)
        assert str(err) == "invalid url"

    def test_time_range_error(self) -> None:
        err = TimeRangeError("bad range")
        assert isinstance(err, SegmentExtractorError)

    def test_authentication_required_error(self) -> None:
        err = AuthenticationRequiredError("need auth")
        assert isinstance(err, SegmentExtractorError)

    def test_video_download_error(self) -> None:
        err = VideoDownloadError("download failed")
        assert isinstance(err, SegmentExtractorError)

    def test_ffmpeg_not_found_error(self) -> None:
        err = FfmpegNotFoundError("ffmpeg missing")
        assert isinstance(err, SegmentExtractorError)

    def test_clip_error(self) -> None:
        err = ClipError("clip failed")
        assert isinstance(err, SegmentExtractorError)

    def test_errors_carry_cause(self) -> None:
        cause = RuntimeError("original")
        err = VideoDownloadError("download failed")
        err.__cause__ = cause
        assert err.__cause__ is cause
