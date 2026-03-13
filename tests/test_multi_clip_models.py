"""MultiClip関連モデルのテスト"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipRequest,
    MultiClipResult,
    TimeRange,
)


class TestTimeRange:
    def test_normal(self) -> None:
        tr = TimeRange(start_seconds=60.0, end_seconds=120.0)
        assert tr.start_seconds == 60.0
        assert tr.end_seconds == 120.0

    def test_zero_start(self) -> None:
        tr = TimeRange(start_seconds=0.0, end_seconds=10.0)
        assert tr.start_seconds == 0.0

    def test_start_equals_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="start_seconds.*end_seconds"):
            TimeRange(start_seconds=60.0, end_seconds=60.0)

    def test_start_greater_than_end_rejected(self) -> None:
        with pytest.raises(ValidationError, match="start_seconds.*end_seconds"):
            TimeRange(start_seconds=120.0, end_seconds=60.0)

    def test_negative_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="0以上"):
            TimeRange(start_seconds=-1.0, end_seconds=10.0)


class TestMultiClipRequest:
    def test_normal(self, tmp_path: Path) -> None:
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )
        assert req.video_id == "dQw4w9WgXcQ"
        assert req.filename == "video.mp4"
        assert len(req.ranges) == 1

    def test_multiple_ranges(self, tmp_path: Path) -> None:
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
            ],
        )
        assert len(req.ranges) == 2

    def test_empty_ranges_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="1つ以上"):
            MultiClipRequest(
                video_id="dQw4w9WgXcQ",
                filename="video.mp4",
                output_dir=tmp_path,
                ranges=[],
            )

    def test_cookie_file_optional(self, tmp_path: Path) -> None:
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=0.0, end_seconds=10.0)],
            cookie_file=tmp_path / "cookies.txt",
        )
        assert req.cookie_file == tmp_path / "cookies.txt"

    def test_broadcast_start_at_default_none(self, tmp_path: Path) -> None:
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=0.0, end_seconds=10.0)],
        )
        assert req.broadcast_start_at is None

    def test_broadcast_start_at_set(self, tmp_path: Path) -> None:
        dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=0.0, end_seconds=10.0)],
            broadcast_start_at=dt,
        )
        assert req.broadcast_start_at == dt


class TestClipOutcome:
    def test_success(self, tmp_path: Path) -> None:
        tr = TimeRange(start_seconds=60.0, end_seconds=120.0)
        outcome = ClipOutcome(
            range=tr,
            output_path=tmp_path / "video1.mp4",
        )
        assert outcome.output_path is not None
        assert outcome.error is None

    def test_failure(self) -> None:
        tr = TimeRange(start_seconds=60.0, end_seconds=120.0)
        outcome = ClipOutcome(
            range=tr,
            output_path=None,
            error="ダウンロードに失敗しました",
        )
        assert outcome.output_path is None
        assert outcome.error is not None


class TestMultiClipResult:
    def test_all_success(self, tmp_path: Path) -> None:
        result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "video1.mp4",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=tmp_path / "video2.mp4",
                ),
            ],
        )
        assert result.success_count == 2
        assert result.failure_count == 0

    def test_partial_failure(self, tmp_path: Path) -> None:
        result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "video1.mp4",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=None,
                    error="失敗",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=300.0, end_seconds=360.0),
                    output_path=tmp_path / "video3.mp4",
                ),
            ],
        )
        assert result.success_count == 2
        assert result.failure_count == 1

    def test_all_failure(self) -> None:
        result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=None,
                    error="失敗1",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=None,
                    error="失敗2",
                ),
            ],
        )
        assert result.success_count == 0
        assert result.failure_count == 2
