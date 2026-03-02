"""kirinuki clip コマンドのインテグレーションテスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.core.errors import (
    AuthenticationRequiredError,
    InvalidURLError,
    VideoDownloadError,
)
from kirinuki.models.clip import (
    ClipOutcome,
    MultiClipResult,
    TimeRange,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestClipCommand:
    def test_normal_single_range(self, runner: CliRunner, tmp_path: Path) -> None:
        """正常系: 単一範囲の切り抜き"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "output.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "1:00-2:00"]
            )

        assert result.exit_code == 0
        assert "output.mp4" in result.output
        assert "成功" in result.output or "完了" in result.output

    def test_normal_multiple_ranges(self, runner: CliRunner, tmp_path: Path) -> None:
        """正常系: 複数範囲の切り抜き"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "output1.mp4",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=tmp_path / "output2.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "1:00-2:00,3:00-4:00"]
            )

        assert result.exit_code == 0
        assert "2" in result.output  # 成功数

    def test_url_input(self, runner: CliRunner, tmp_path: Path) -> None:
        """URL入力でも正常動作"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "output.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli,
                [
                    "clip",
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "output.mp4",
                    "1:00-2:00",
                ],
            )

        assert result.exit_code == 0

    def test_invalid_url_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """無効なURL/動画IDでエラー"""
        with (
            patch("kirinuki.cli.clip.resolve_video_id") as mock_resolve,
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            mock_resolve.side_effect = InvalidURLError("無効な動画ID/URLです")

            result = runner.invoke(
                cli, ["clip", "invalid", "output.mp4", "1:00-2:00"]
            )

        assert result.exit_code == 1
        assert "無効" in result.output

    def test_invalid_time_range_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """不正な時間範囲でエラー"""
        with patch("kirinuki.cli.clip.AppConfig") as MockConfig:
            MockConfig.return_value.output_dir = tmp_path

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "abc"]
            )

        assert result.exit_code == 1
        assert "時間範囲" in result.output or "エラー" in result.output

    def test_reversed_time_range_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """開始>終了の時間範囲でエラー"""
        with patch("kirinuki.cli.clip.AppConfig") as MockConfig:
            MockConfig.return_value.output_dir = tmp_path

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "20:00-10:00"]
            )

        assert result.exit_code == 1

    def test_output_dir_option_overrides_config(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """--output-dir がAppConfigより優先される"""
        custom_dir = tmp_path / "custom"
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=custom_dir / "output.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path / "default"
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli,
                [
                    "clip",
                    "dQw4w9WgXcQ",
                    "output.mp4",
                    "1:00-2:00",
                    "--output-dir",
                    str(custom_dir),
                ],
            )

        assert result.exit_code == 0
        # Verify the request was built with the custom dir
        call_args = MockService.return_value.execute.call_args[0][0]
        assert call_args.output_dir == custom_dir

    def test_download_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """ダウンロード失敗 (全範囲失敗のサマリー表示)"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=None,
                    error="動画のダウンロードに失敗しました",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "1:00-2:00"]
            )

        # Should still succeed (exit 0) with a summary showing failures
        assert result.exit_code == 0
        assert "失敗" in result.output

    def test_auth_required_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """認証エラー"""
        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.side_effect = AuthenticationRequiredError(
                "認証が必要です"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "1:00-2:00"]
            )

        assert result.exit_code == 1
        assert "認証" in result.output

    def test_summary_with_partial_failure(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """複数範囲で部分失敗時のサマリー表示"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=60.0, end_seconds=120.0),
                    output_path=tmp_path / "output1.mp4",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=180.0, end_seconds=240.0),
                    output_path=None,
                    error="失敗しました",
                ),
                ClipOutcome(
                    range=TimeRange(start_seconds=300.0, end_seconds=360.0),
                    output_path=tmp_path / "output3.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli,
                [
                    "clip",
                    "dQw4w9WgXcQ",
                    "output.mp4",
                    "1:00-2:00,3:00-4:00,5:00-6:00",
                ],
            )

        assert result.exit_code == 0
        # Summary should mention both successes and failures
        assert "2" in result.output  # success count
        assert "1" in result.output  # failure count

    def test_hhmmss_time_format(self, runner: CliRunner, tmp_path: Path) -> None:
        """HH:MM:SS形式の時刻指定"""
        mock_result = MultiClipResult(
            video_id="dQw4w9WgXcQ",
            outcomes=[
                ClipOutcome(
                    range=TimeRange(start_seconds=3600.0, end_seconds=3660.0),
                    output_path=tmp_path / "output.mp4",
                ),
            ],
        )

        with (
            patch("kirinuki.cli.clip.ClipService") as MockService,
            patch("kirinuki.cli.clip.YtdlpClient"),
            patch("kirinuki.cli.clip.AppConfig") as MockConfig,
        ):
            MockConfig.return_value.output_dir = tmp_path
            MockConfig.return_value.cookie_file_path = tmp_path / "cookies.txt"
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "output.mp4", "1:00:00-1:01:00"]
            )

        assert result.exit_code == 0
