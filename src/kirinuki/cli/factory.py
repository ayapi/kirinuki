"""CLI共通ファクトリ"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kirinuki.core.clip_service import ClipService
    from kirinuki.models.config import AppConfig


def create_clip_service(config: AppConfig) -> ClipService:
    """AppConfigからClipServiceを生成する共通ヘルパー。"""
    from kirinuki.core.clip_service import ClipService as _ClipService
    from kirinuki.infra.ffmpeg import FfmpegClientImpl
    from kirinuki.infra.ytdlp_client import YtdlpClient

    ytdlp = YtdlpClient(config)
    FfmpegClientImpl().check_available()
    return _ClipService(ytdlp_client=ytdlp)
