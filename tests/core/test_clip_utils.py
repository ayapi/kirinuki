"""切り抜きユーティリティ関数のテスト"""

import pytest

from kirinuki.core.clip_utils import (
    build_youtube_url,
    extract_video_id,
    format_default_filename,
    parse_time_str,
    seconds_to_ffmpeg_time,
)
from kirinuki.core.errors import InvalidURLError


class TestExtractVideoId:
    def test_standard_watch_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self) -> None:
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self) -> None:
        assert extract_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_watch_url_with_extra_params(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120&list=PLxyz"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_short_url_with_params(self) -> None:
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=120") == "dQw4w9WgXcQ"

    def test_live_url_with_query(self) -> None:
        url = "https://www.youtube.com/live/dQw4w9WgXcQ?si=abc"
        assert extract_video_id(url) == "dQw4w9WgXcQ"

    def test_http_url(self) -> None:
        assert extract_video_id("http://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_no_www(self) -> None:
        assert extract_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(InvalidURLError):
            extract_video_id("https://example.com/video")

    def test_empty_string_raises(self) -> None:
        with pytest.raises(InvalidURLError):
            extract_video_id("")

    def test_not_a_url_raises(self) -> None:
        with pytest.raises(InvalidURLError):
            extract_video_id("not a url")


class TestSecondsToFfmpegTime:
    def test_zero(self) -> None:
        assert seconds_to_ffmpeg_time(0.0) == "00:00:00.000"

    def test_simple_seconds(self) -> None:
        assert seconds_to_ffmpeg_time(65.5) == "00:01:05.500"

    def test_hours(self) -> None:
        assert seconds_to_ffmpeg_time(3661.123) == "01:01:01.123"

    def test_exact_hour(self) -> None:
        assert seconds_to_ffmpeg_time(3600.0) == "01:00:00.000"

    def test_large_value(self) -> None:
        assert seconds_to_ffmpeg_time(36000.0) == "10:00:00.000"


class TestParseTimeStr:
    def test_hhmmss(self) -> None:
        assert parse_time_str("01:30:00") == 5400.0

    def test_mmss(self) -> None:
        assert parse_time_str("05:30") == 330.0

    def test_seconds_only(self) -> None:
        assert parse_time_str("120") == 120.0

    def test_seconds_float(self) -> None:
        assert parse_time_str("65.5") == 65.5

    def test_hhmmss_with_millis(self) -> None:
        assert parse_time_str("01:01:01.5") == 3661.5


class TestBuildYoutubeUrl:
    def test_normal_ms(self) -> None:
        url = build_youtube_url("abc123", 90000)
        assert url == "https://www.youtube.com/watch?v=abc123&t=90"

    def test_zero_ms(self) -> None:
        url = build_youtube_url("abc123", 0)
        assert url == "https://www.youtube.com/watch?v=abc123&t=0"

    def test_large_value(self) -> None:
        url = build_youtube_url("abc123", 7200000)
        assert url == "https://www.youtube.com/watch?v=abc123&t=7200"

    def test_truncates_ms_to_seconds(self) -> None:
        """1999ms → 1s（切り捨て確認）"""
        url = build_youtube_url("abc123", 1999)
        assert url == "https://www.youtube.com/watch?v=abc123&t=1"

    def test_exact_second_boundary(self) -> None:
        url = build_youtube_url("abc123", 2000)
        assert url == "https://www.youtube.com/watch?v=abc123&t=2"


class TestFormatDefaultFilename:
    def test_both_times(self) -> None:
        name = format_default_filename("abc123", 10.0, 60.0, "mp4")
        assert name == "abc123_10.0-60.0.mp4"

    def test_mkv_format(self) -> None:
        name = format_default_filename("xyz", 0.0, 120.5, "mkv")
        assert name == "xyz_0.0-120.5.mkv"
