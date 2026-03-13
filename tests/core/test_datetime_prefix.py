"""日時プレフィックスユーティリティ関数のテスト"""

from datetime import datetime, timezone, timedelta

import pytest

from kirinuki.core.clip_utils import has_datetime_prefix, prepend_datetime_prefix

JST = timezone(timedelta(hours=9))


class TestHasDatetimePrefix:
    def test_valid_prefix(self) -> None:
        assert has_datetime_prefix("20260310_2100_動画.mp4") is True

    def test_no_prefix(self) -> None:
        assert has_datetime_prefix("動画.mp4") is False

    def test_partial_prefix(self) -> None:
        assert has_datetime_prefix("2026031_2100_動画.mp4") is False

    def test_prefix_without_underscore(self) -> None:
        assert has_datetime_prefix("202603102100動画.mp4") is False

    def test_midnight_prefix(self) -> None:
        assert has_datetime_prefix("20260310_0000_動画.mp4") is True


class TestPrependDatetimePrefix:
    def test_utc_datetime_converted_to_jst(self) -> None:
        # UTC 2026-03-10 12:00 -> JST 2026-03-10 21:00
        dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        result = prepend_datetime_prefix("動画.mp4", dt)
        assert result == "20260310_2100_動画.mp4"

    def test_jst_datetime(self) -> None:
        dt = datetime(2026, 3, 10, 21, 0, tzinfo=JST)
        result = prepend_datetime_prefix("動画.mp4", dt)
        assert result == "20260310_2100_動画.mp4"

    def test_none_returns_original(self) -> None:
        result = prepend_datetime_prefix("動画.mp4", None)
        assert result == "動画.mp4"

    def test_no_duplicate_prefix(self) -> None:
        dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        result = prepend_datetime_prefix("20260310_2100_動画.mp4", dt)
        assert result == "20260310_2100_動画.mp4"

    def test_with_numbered_filename(self) -> None:
        # 連番 + 日時プレフィックスの組み合わせ
        dt = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
        result = prepend_datetime_prefix("動画1.mp4", dt)
        assert result == "20260310_2100_動画1.mp4"

    def test_midnight_utc_to_jst(self) -> None:
        # UTC 2026-03-10 00:00 -> JST 2026-03-10 09:00
        dt = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        result = prepend_datetime_prefix("clip.mp4", dt)
        assert result == "20260310_0900_clip.mp4"

    def test_date_boundary_crossing(self) -> None:
        # UTC 2026-03-10 20:00 -> JST 2026-03-11 05:00
        dt = datetime(2026, 3, 10, 20, 0, tzinfo=timezone.utc)
        result = prepend_datetime_prefix("clip.mp4", dt)
        assert result == "20260311_0500_clip.mp4"
