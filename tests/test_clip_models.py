"""ClipRequest/ClipResultモデルのテスト"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from kirinuki.models.clip import ClipRequest, ClipResult


class TestClipRequest:
    def test_normal_with_both_times(self) -> None:
        req = ClipRequest(
            url="https://www.youtube.com/watch?v=abc123",
            start_seconds=10.0,
            end_seconds=60.0,
        )
        assert req.start_seconds == 10.0
        assert req.end_seconds == 60.0
        assert req.output_format == "mp4"
        assert req.output_path is None
        assert req.cookie_file is None

    def test_start_only(self) -> None:
        req = ClipRequest(
            url="https://www.youtube.com/watch?v=abc123",
            start_seconds=30.0,
        )
        assert req.start_seconds == 30.0
        assert req.end_seconds is None

    def test_end_only(self) -> None:
        req = ClipRequest(
            url="https://www.youtube.com/watch?v=abc123",
            end_seconds=120.0,
        )
        assert req.start_seconds is None
        assert req.end_seconds == 120.0

    def test_both_none_rejected(self) -> None:
        with pytest.raises(ValidationError, match="少なくとも一方"):
            ClipRequest(url="https://www.youtube.com/watch?v=abc123")

    def test_start_greater_than_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="start_seconds.*end_seconds"):
            ClipRequest(
                url="https://www.youtube.com/watch?v=abc123",
                start_seconds=100.0,
                end_seconds=50.0,
            )

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClipRequest(
                url="https://www.youtube.com/watch?v=abc123",
                start_seconds=-1.0,
                end_seconds=10.0,
            )

    def test_unsupported_format_rejected(self) -> None:
        with pytest.raises(ValidationError, match="サポート"):
            ClipRequest(
                url="https://www.youtube.com/watch?v=abc123",
                start_seconds=0.0,
                end_seconds=10.0,
                output_format="avi",
            )

    def test_supported_formats(self) -> None:
        for fmt in ("mp4", "mkv", "webm"):
            req = ClipRequest(
                url="https://www.youtube.com/watch?v=abc123",
                start_seconds=0.0,
                end_seconds=10.0,
                output_format=fmt,
            )
            assert req.output_format == fmt

    def test_output_path(self, tmp_path: Path) -> None:
        out = tmp_path / "output.mp4"
        req = ClipRequest(
            url="https://www.youtube.com/watch?v=abc123",
            start_seconds=0.0,
            end_seconds=10.0,
            output_path=out,
        )
        assert req.output_path == out

    def test_cookie_file(self, tmp_path: Path) -> None:
        cookie = tmp_path / "cookies.txt"
        req = ClipRequest(
            url="https://www.youtube.com/watch?v=abc123",
            start_seconds=0.0,
            end_seconds=10.0,
            cookie_file=cookie,
        )
        assert req.cookie_file == cookie


class TestClipResult:
    def test_creation(self, tmp_path: Path) -> None:
        result = ClipResult(
            output_path=tmp_path / "output.mp4",
            video_id="abc123",
            start_seconds=10.0,
            end_seconds=70.0,
            duration_seconds=60.0,
        )
        assert result.video_id == "abc123"
        assert result.duration_seconds == 60.0
        assert result.output_path == tmp_path / "output.mp4"
