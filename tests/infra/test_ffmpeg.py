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
        assert "libmp3lame" in cmd
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
    def test_clip_timeout(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """ffmpegがタイムアウトした場合にClipErrorが発生する"""
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 1800)
        input_path = tmp_path / "input.mp4"
        input_path.touch()
        output_path = tmp_path / "output.mp4"

        client = FfmpegClientImpl()
        with pytest.raises(ClipError, match="タイムアウト"):
            client.clip(input_path, output_path, 10.0, 60.0)

    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_clip_passes_timeout_to_subprocess(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """subprocess.runにtimeout引数が渡されること"""
        mock_run.return_value = MagicMock(returncode=0)
        input_path = tmp_path / "input.mp4"
        input_path.touch()
        output_path = tmp_path / "output.mp4"

        client = FfmpegClientImpl()
        client.clip(input_path, output_path, 10.0, 60.0)

        kwargs = mock_run.call_args[1]
        assert kwargs["timeout"] == 1800

    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_reencode_success(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """映像・音声を再エンコードし、元ファイルを置き換える"""
        mock_run.return_value = MagicMock(returncode=0)
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"dummy")
        # tmp fileが作られるのをシミュレート
        tmp_file = file_path.with_suffix(".tmp.mp4")
        def create_tmp(*args, **kwargs):
            tmp_file.write_bytes(b"reencoded")
        mock_run.side_effect = create_tmp

        client = FfmpegClientImpl()
        client.reencode(file_path)

        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-preset" in cmd
        assert "veryfast" in cmd
        assert "-crf" in cmd
        assert "20" in cmd
        assert "-pix_fmt" in cmd
        assert "yuv420p" in cmd
        assert "-c:a" in cmd
        assert "libmp3lame" in cmd
        assert "-q:a" in cmd
        assert "2" in cmd
        assert "+faststart" in cmd

    @patch("kirinuki.infra.ffmpeg.subprocess.run")
    def test_reencode_failure_cleans_up(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """再エンコード失敗時にtmpファイルが削除される"""
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg", stderr="error")
        file_path = tmp_path / "video.mp4"
        file_path.write_bytes(b"dummy")

        client = FfmpegClientImpl()
        with pytest.raises(ClipError):
            client.reencode(file_path)

        tmp_file = file_path.with_suffix(".tmp.mp4")
        assert not tmp_file.exists()

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
