"""MultiClipRequest margin_secondsバリデーションのテスト"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from kirinuki.models.clip import MultiClipRequest, TimeRange


class TestMultiClipRequestMarginSeconds:
    def test_default_is_zero(self, tmp_path: Path) -> None:
        """margin_seconds未指定時のデフォルトが0.0"""
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )
        assert req.margin_seconds == 0.0

    def test_positive_value_accepted(self, tmp_path: Path) -> None:
        """正の値が受け入れられる"""
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=5.0,
        )
        assert req.margin_seconds == 5.0

    def test_zero_accepted(self, tmp_path: Path) -> None:
        """0.0が受け入れられる"""
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=0.0,
        )
        assert req.margin_seconds == 0.0

    def test_negative_value_rejected(self, tmp_path: Path) -> None:
        """負の値がバリデーションエラーになる"""
        with pytest.raises(ValidationError):
            MultiClipRequest(
                video_id="dQw4w9WgXcQ",
                filename="video.mp4",
                output_dir=tmp_path,
                ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
                margin_seconds=-1.0,
            )

    def test_large_positive_value_accepted(self, tmp_path: Path) -> None:
        """大きい正の値も受け入れられる"""
        req = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=30.0,
        )
        assert req.margin_seconds == 30.0
