"""kirinuki clip コマンドのインテグレーションテスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.core.errors import (
    AuthenticationRequiredError,
    ClipError,
    FfmpegNotFoundError,
    InvalidURLError,
    VideoDownloadError,
)
from kirinuki.models.clip import ClipResult


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestClipCommand:
    def test_normal_execution(self, runner: CliRunner, tmp_path: Path) -> None:
        """正常系: 引数パースと完了メッセージ表示"""
        output_path = tmp_path / "output.mp4"

        mock_result = ClipResult(
            output_path=output_path,
            video_id="dQw4w9WgXcQ",
            start_seconds=60.0,
            end_seconds=120.0,
            duration_seconds=60.0,
        )

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 0
        assert str(output_path) in result.output

    def test_url_input(self, runner: CliRunner, tmp_path: Path) -> None:
        """URL入力でも正常動作する"""
        output_path = tmp_path / "output.mp4"

        mock_result = ClipResult(
            output_path=output_path,
            video_id="dQw4w9WgXcQ",
            start_seconds=60.0,
            end_seconds=120.0,
            duration_seconds=60.0,
        )

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli,
                ["clip", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "1:00", "2:00", str(output_path)],
            )

        assert result.exit_code == 0

    def test_invalid_url_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """無効なURL/動画IDでエラーメッセージ表示"""
        output_path = tmp_path / "output.mp4"

        with patch("kirinuki.cli.clip.resolve_video_id") as mock_resolve, \
             patch("kirinuki.cli.clip.AppConfig"):
            mock_resolve.side_effect = InvalidURLError("無効な動画ID/URLです")

            result = runner.invoke(
                cli, ["clip", "invalid", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "無効" in result.output

    def test_ffmpeg_not_found_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """ffmpeg未インストール時のエラーメッセージ"""
        output_path = tmp_path / "output.mp4"

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.side_effect = FfmpegNotFoundError(
                "ffmpegがインストールされていません"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "ffmpeg" in result.output

    def test_download_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """ダウンロード失敗時のエラーメッセージ"""
        output_path = tmp_path / "output.mp4"

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.side_effect = VideoDownloadError(
                "動画のダウンロードに失敗しました"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "ダウンロード" in result.output

    def test_time_range_hhmmss(self, runner: CliRunner, tmp_path: Path) -> None:
        """HH:MM:SS形式の時刻指定"""
        output_path = tmp_path / "output.mp4"

        mock_result = ClipResult(
            output_path=output_path,
            video_id="dQw4w9WgXcQ",
            start_seconds=3600.0,
            end_seconds=3660.0,
            duration_seconds=60.0,
        )

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.return_value = mock_result

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00:00", "1:01:00", str(output_path)]
            )

        assert result.exit_code == 0

    def test_output_dir_not_exists_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """出力先ディレクトリ不在時のエラーメッセージ"""
        output_path = tmp_path / "nonexistent" / "output.mp4"

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.side_effect = FileNotFoundError(
                f"出力先ディレクトリが存在しません: {output_path.parent}"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "ディレクトリ" in result.output

    def test_auth_required_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """認証要求エラー"""
        output_path = tmp_path / "output.mp4"

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.side_effect = AuthenticationRequiredError(
                "認証が必要です"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "認証" in result.output

    def test_clip_error(self, runner: CliRunner, tmp_path: Path) -> None:
        """切り出し失敗エラー"""
        output_path = tmp_path / "output.mp4"

        with patch("kirinuki.cli.clip.ClipService") as MockService, \
             patch("kirinuki.cli.clip.FfmpegClientImpl"), \
             patch("kirinuki.cli.clip.YtdlpClient"), \
             patch("kirinuki.cli.clip.AppConfig"):
            MockService.return_value.execute.side_effect = ClipError(
                "切り出しに失敗しました"
            )

            result = runner.invoke(
                cli, ["clip", "dQw4w9WgXcQ", "1:00", "2:00", str(output_path)]
            )

        assert result.exit_code == 1
        assert "切り出し" in result.output
