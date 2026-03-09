"""FfmpegClientのテスト（モック使用）"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.core.errors import ClipError, FfmpegNotFoundError
from kirinuki.infra.ffmpeg import FfmpegClientImpl


class TestCheckAvailable:
    @patch("kirinuki.infra.ffmpeg.shutil.which")
    def test_ffmpeg_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = "/usr/bin/ffmpeg"
        client = FfmpegClientImpl()
        client.check_available()  # should not raise

    @patch("kirinuki.infra.ffmpeg.shutil.which")
    def test_ffmpeg_not_found(self, mock_which: MagicMock) -> None:
        mock_which.return_value = None
        client = FfmpegClientImpl()
        with pytest.raises(FfmpegNotFoundError):
            client.check_available()


class TestClip:
    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_clip_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        input_path = tmp_path / "input.mp4"
        input_path.touch()
        output_path = tmp_path / "output.mp4"

        client = FfmpegClientImpl()
        client.clip(input_path, output_path, 10.0, 60.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd
        assert "-ss" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "+faststart" in cmd

    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_clip_failure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg", stderr="error details")
        input_path = tmp_path / "input.mp4"
        input_path.touch()
        output_path = tmp_path / "output.mp4"

        client = FfmpegClientImpl()
        with pytest.raises(ClipError):
            client.clip(input_path, output_path, 10.0, 60.0)

    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_clip_command_structure(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """ffmpegコマンドが正しい構造で呼ばれることを確認"""
        mock_run.return_value = MagicMock(returncode=0)
        input_path = tmp_path / "input.mp4"
        input_path.touch()
        output_path = tmp_path / "output.mp4"

        client = FfmpegClientImpl()
        client.clip(input_path, output_path, 10.0, 60.0)

        cmd = mock_run.call_args[0][0]
        # -ss should come before -i (keyframe seek)
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx
        # -y flag for overwrite
        assert "-y" in cmd
