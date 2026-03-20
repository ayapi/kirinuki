"""ClipService マージン適用ロジックのユニットテスト"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from kirinuki.core.clip_service import DEFAULT_CLIP_MARGIN_SECONDS, ClipService
from kirinuki.models.clip import MultiClipRequest, TimeRange


@pytest.fixture
def mock_ytdlp() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_ytdlp: MagicMock) -> ClipService:
    return ClipService(ytdlp_client=mock_ytdlp, max_workers=4)


class TestClipServiceMargin:
    def test_default_margin_constant(self) -> None:
        """デフォルトマージン定数が5.0秒であること"""
        assert DEFAULT_CLIP_MARGIN_SECONDS == 5.0

    def test_margin_expands_start_and_end(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """マージン有り(5.0秒)でstart/endが正しく拡張される"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=5.0,
        )

        service.execute(request)

        mock_ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            55.0,  # 60.0 - 5.0
            125.0,  # 120.0 + 5.0
            tmp_path / "video.mp4",
            cookie_file=None,
            on_progress=None,
        )

    def test_zero_margin_no_change(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """マージン無し(0.0秒)で元のstart/endがそのまま渡される"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=0.0,
        )

        service.execute(request)

        mock_ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            60.0,
            120.0,
            tmp_path / "video.mp4",
            cookie_file=None,
            on_progress=None,
        )

    def test_margin_clamps_start_to_zero(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """開始時刻が5秒未満の区間でマージン適用時に0にクランプされる"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=3.0, end_seconds=30.0)],
            margin_seconds=5.0,
        )

        service.execute(request)

        mock_ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            0.0,  # max(0, 3.0 - 5.0) = 0.0
            35.0,  # 30.0 + 5.0
            tmp_path / "video.mp4",
            cookie_file=None,
            on_progress=None,
        )

    def test_margin_with_start_exactly_zero(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """開始時刻が0の区間でもクランプされて0のまま"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=0.0, end_seconds=30.0)],
            margin_seconds=5.0,
        )

        service.execute(request)

        call_args = mock_ytdlp.download_section.call_args
        assert call_args[0][1] == 0.0  # start clamped to 0
        assert call_args[0][2] == 35.0  # end + 5.0

    def test_outcome_range_preserves_original(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """ClipOutcome.rangeにはマージン適用前の元のTimeRangeが保持される"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
            margin_seconds=5.0,
        )

        result = service.execute(request)

        assert result.outcomes[0].range.start_seconds == 60.0
        assert result.outcomes[0].range.end_seconds == 120.0

    def test_margin_default_omitted_is_zero(
        self, service: ClipService, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """margin_seconds未指定時はデフォルト0.0でマージンなし（CLI互換）"""
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[TimeRange(start_seconds=60.0, end_seconds=120.0)],
        )

        service.execute(request)

        mock_ytdlp.download_section.assert_called_once_with(
            "dQw4w9WgXcQ",
            60.0,
            120.0,
            tmp_path / "video.mp4",
            cookie_file=None,
            on_progress=None,
        )

    def test_margin_applied_to_multiple_ranges(
        self, mock_ytdlp: MagicMock, tmp_path: Path
    ) -> None:
        """複数範囲でもそれぞれにマージンが適用される"""
        service = ClipService(ytdlp_client=mock_ytdlp, max_workers=4)
        request = MultiClipRequest(
            video_id="dQw4w9WgXcQ",
            filename="video.mp4",
            output_dir=tmp_path,
            ranges=[
                TimeRange(start_seconds=60.0, end_seconds=120.0),
                TimeRange(start_seconds=180.0, end_seconds=240.0),
            ],
            margin_seconds=5.0,
        )

        result = service.execute(request)

        assert result.success_count == 2
        calls = mock_ytdlp.download_section.call_args_list
        # 順序は並列実行で不定なのでstart値でソート
        starts = sorted([c[0][1] for c in calls])
        ends = sorted([c[0][2] for c in calls])
        assert starts == [55.0, 175.0]
        assert ends == [125.0, 245.0]
