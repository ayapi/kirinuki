"""切り抜き機能のユーティリティ関数"""

import re
from urllib.parse import parse_qs, urlparse

from kirinuki.core.errors import InvalidURLError

_YOUTUBE_PATTERNS = [
    # https://www.youtube.com/watch?v=VIDEO_ID
    re.compile(r"^https?://(?:www\.)?youtube\.com/watch"),
    # https://youtu.be/VIDEO_ID
    re.compile(r"^https?://youtu\.be/"),
    # https://www.youtube.com/live/VIDEO_ID
    re.compile(r"^https?://(?:www\.)?youtube\.com/live/"),
]


def extract_video_id(url: str) -> str:
    """YouTube URLから動画IDを抽出する。無効なURLの場合はInvalidURLErrorを送出する。"""
    if not url:
        raise InvalidURLError("URLが空です")

    parsed = urlparse(url)

    # youtu.be/VIDEO_ID
    if parsed.hostname in ("youtu.be",):
        video_id = parsed.path.lstrip("/").split("/")[0]
        if video_id:
            return video_id

    # youtube.com/watch?v=VIDEO_ID
    if parsed.hostname in ("www.youtube.com", "youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            v = qs.get("v")
            if v:
                return v[0]

        # youtube.com/live/VIDEO_ID
        live_match = re.match(r"^/live/([^/?]+)", parsed.path)
        if live_match:
            return live_match.group(1)

    raise InvalidURLError(f"無効なYouTube URLです: {url}")


def seconds_to_ffmpeg_time(seconds: float) -> str:
    """秒数をHH:MM:SS.mmm形式に変換する（ffmpegコマンド用）。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def parse_time_str(time_str: str) -> float:
    """HH:MM:SS、MM:SS、または秒数の文字列をfloat秒数に変換する。"""
    parts = time_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    else:
        return float(time_str)


def build_youtube_url(video_id: str, start_ms: int) -> str:
    """タイムスタンプ付きYouTube URLを生成する。

    Args:
        video_id: YouTube動画ID
        start_ms: 開始時刻（ミリ秒）

    Returns:
        https://www.youtube.com/watch?v={video_id}&t={start_seconds} 形式の文字列
    """
    start_seconds = start_ms // 1000
    return f"https://www.youtube.com/watch?v={video_id}&t={start_seconds}"


def format_default_filename(
    video_id: str, start_seconds: float, end_seconds: float, output_format: str
) -> str:
    """デフォルトの出力ファイル名を生成する。"""
    return f"{video_id}_{start_seconds}-{end_seconds}.{output_format}"
