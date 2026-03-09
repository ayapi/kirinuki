"""ffmpegによる動画区間切り出し"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from kirinuki.core.clip_utils import seconds_to_ffmpeg_time
from kirinuki.core.errors import ClipError, FfmpegNotFoundError

logger = logging.getLogger(__name__)


class FfmpegClient(Protocol):
    def check_available(self) -> None: ...

    def clip(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None: ...


class FfmpegClientImpl:
    """ffmpegのsubprocessラッパー実装"""

    def check_available(self) -> None:
        """ffmpegがシステムにインストールされているか確認する。"""
        if shutil.which("ffmpeg") is None:
            raise FfmpegNotFoundError(
                "ffmpegがインストールされていません。"
                " ffmpegをインストールしてください: https://ffmpeg.org/download.html"
            )

    def clip(
        self,
        input_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> None:
        """入力動画の指定区間を切り出して出力ファイルに保存する。"""
        start_time = seconds_to_ffmpeg_time(start_seconds)
        duration = end_seconds - start_seconds
        duration_time = seconds_to_ffmpeg_time(duration)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            start_time,
            "-i",
            str(input_path),
            "-t",
            duration_time,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-avoid_negative_ts",
            "make_zero",
            str(output_path),
        ]

        logger.debug("ffmpeg command: %s", " ".join(cmd))

        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", errors="replace")
        except subprocess.CalledProcessError as e:
            raise ClipError(f"ffmpegによる切り出しに失敗しました: {e.stderr}") from e
