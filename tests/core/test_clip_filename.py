"""generate_clip_filename / sanitize_filename のユニットテスト"""

import pytest

from kirinuki.core.clip_utils import generate_clip_filename, sanitize_filename


class TestSanitizeFilename:
    def test_removes_forbidden_chars(self) -> None:
        assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"

    def test_replaces_spaces_with_underscore(self) -> None:
        assert sanitize_filename("hello world") == "hello_world"

    def test_strips_trailing_dots_and_spaces(self) -> None:
        assert sanitize_filename("test...") == "test"
        assert sanitize_filename("test   ") == "test"

    def test_truncates_long_text(self) -> None:
        long_text = "あ" * 100
        result = sanitize_filename(long_text, max_length=50)
        assert len(result) <= 50

    def test_removes_control_chars(self) -> None:
        assert sanitize_filename("hello\x00world\x1f") == "hello_world"

    def test_empty_after_sanitize_returns_fallback(self) -> None:
        result = sanitize_filename("///")
        assert result == "clip"

    def test_whitespace_only_returns_fallback(self) -> None:
        result = sanitize_filename("   ")
        assert result == "clip"

    def test_japanese_text_preserved(self) -> None:
        assert sanitize_filename("面白い話題について") == "面白い話題について"

    def test_mixed_content(self) -> None:
        result = sanitize_filename("話題: ゲームの話 (part 1)")
        assert "話題" in result
        assert ":" not in result


class TestGenerateClipFilename:
    def test_basic_format(self) -> None:
        result = generate_clip_filename("dQw4w9WgXcQ", 1083000, "面白い話題")
        assert result == "dQw4w9WgXcQ-18m03s-面白い話題.mp4"

    def test_zero_start(self) -> None:
        result = generate_clip_filename("dQw4w9WgXcQ", 0, "冒頭の話題")
        assert result == "dQw4w9WgXcQ-0m00s-冒頭の話題.mp4"

    def test_over_one_hour(self) -> None:
        # 1h 12m 15s = 72m 15s = 4335000 ms
        result = generate_clip_filename("dQw4w9WgXcQ", 4335000, "長い配信")
        assert result == "dQw4w9WgXcQ-72m15s-長い配信.mp4"

    def test_special_chars_in_summary_sanitized(self) -> None:
        result = generate_clip_filename("dQw4w9WgXcQ", 60000, 'ゲーム/実況: "最高"')
        assert "/" not in result
        assert ":" not in result
        assert '"' not in result
        assert result.endswith(".mp4")

    def test_long_summary_truncated(self) -> None:
        long_summary = "あ" * 100
        result = generate_clip_filename("dQw4w9WgXcQ", 60000, long_summary)
        # video_id(11) + "-" + time + "-" + summary(<=50) + ".mp4"
        assert len(result.split("-", 2)[2].removesuffix(".mp4")) <= 50

    def test_exact_seconds(self) -> None:
        # 5m 0s = 300000 ms
        result = generate_clip_filename("dQw4w9WgXcQ", 300000, "話題")
        assert result == "dQw4w9WgXcQ-5m00s-話題.mp4"
