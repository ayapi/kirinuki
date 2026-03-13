"""切り抜き機能のユーティリティ関数"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from kirinuki.core.errors import InvalidURLError

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")

_YOUTUBE_PATTERNS = [
    # https://www.youtube.com/watch?v=VIDEO_ID
    re.compile(r"^https?://(?:www\.)?youtube\.com/watch"),
    # https://youtu.be/VIDEO_ID
    re.compile(r"^https?://youtu\.be/"),
    # https://www.youtube.com/live/VIDEO_ID
    re.compile(r"^https?://(?:www\.)?youtube\.com/live/"),
]


def resolve_video_id(video: str) -> str:
    """URL or 動画IDを受け取り、動画IDを返す。

    - 11文字の動画IDパターンにマッチ → そのまま返す
    - それ以外 → extract_video_id() でURL解析を試みる

    Raises:
        InvalidURLError: URLとしても動画IDとしても無効な場合
    """
    if _YOUTUBE_VIDEO_ID_RE.match(video):
        return video
    return extract_video_id(video)


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


def parse_time_ranges(time_ranges_str: str) -> list:
    """カンマ区切りの時間範囲文字列をパースする。

    Args:
        time_ranges_str: "18:03-19:31,21:31-23:20" 形式の文字列

    Returns:
        TimeRange のリスト

    Raises:
        ValueError: フォーマット不正の場合
    """
    from kirinuki.models.clip import TimeRange

    time_ranges_str = time_ranges_str.strip()
    if not time_ranges_str:
        raise ValueError("時間範囲が空です")

    ranges: list[TimeRange] = []
    for part in time_ranges_str.split(","):
        part = part.strip()
        if "-" not in part:
            raise ValueError(f"時間範囲のフォーマットが不正です（ハイフンがありません）: {part}")

        # 最後のハイフンで分割（時刻にハイフンは含まれない前提）
        # "1:00:00-1:30:00" → start="1:00:00", end="1:30:00"
        idx = part.rfind("-")
        start_str = part[:idx].strip()
        end_str = part[idx + 1 :].strip()

        if not start_str or not end_str:
            raise ValueError(f"時間範囲のフォーマットが不正です: {part}")

        try:
            start_seconds = parse_time_str(start_str)
            end_seconds = parse_time_str(end_str)
        except ValueError as e:
            raise ValueError(f"時刻のパースに失敗しました: {part} ({e})") from e

        try:
            ranges.append(
                TimeRange(start_seconds=start_seconds, end_seconds=end_seconds)
            )
        except Exception as e:
            raise ValueError(
                f"時間範囲が不正です: {part} ({e})"
            ) from e

    return ranges


def sanitize_filename(text: str, max_length: int = 50) -> str:
    """テキストからファイル名に使用できない文字を除去し、長さを制限する。

    除去対象: / \\ : * ? " < > | および制御文字
    空白はアンダースコアに置換。末尾のドットとスペースを除去。
    """
    # 制御文字を空白に置換
    result = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    # ファイル名禁止文字を除去
    result = re.sub(r'[/\\:*?"<>|]', "", result)
    # 空白をアンダースコアに置換
    result = re.sub(r"\s+", "_", result)
    # 末尾のドットとアンダースコアを除去
    result = result.rstrip("._")
    # 長さ制限
    if len(result) > max_length:
        result = result[:max_length].rstrip("._")
    # 空の場合のフォールバック
    if not result:
        result = "clip"
    return result


def generate_clip_filename(video_id: str, start_ms: int, summary: str) -> str:
    """切り抜きファイル名を自動生成する。

    形式: {video_id}-{M}m{SS}s-{sanitized_summary}.mp4
    例: dQw4w9WgXcQ-18m03s-面白い話題について.mp4
    """
    total_seconds = start_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    time_str = f"{minutes}m{seconds:02d}s"
    safe_summary = sanitize_filename(summary)
    return f"{video_id}-{time_str}-{safe_summary}.mp4"


def build_numbered_filename(filename: str, index: int, total: int) -> str:
    """連番付きファイル名を生成する。

    Args:
        filename: ベースファイル名（例: "動画.mp4"）
        index: 1始まりのインデックス
        total: 総数（1の場合は連番なし）

    Returns:
        "動画1.mp4" or "動画.mp4"（total=1の場合）
    """
    if total == 1:
        return filename

    from pathlib import PurePosixPath

    p = PurePosixPath(filename)
    return f"{p.stem}{index}{p.suffix}"


_JST = timezone(timedelta(hours=9))
_DATETIME_PREFIX_RE = re.compile(r"^\d{8}_\d{4}_")


def has_datetime_prefix(filename: str) -> bool:
    """ファイル名が既に YYYYMMDD_HHMM_ 形式の日時プレフィックスを持つかを判定する。"""
    return bool(_DATETIME_PREFIX_RE.match(filename))


def prepend_datetime_prefix(
    filename: str,
    broadcast_start_at: datetime | None,
) -> str:
    """ファイル名の先頭に配信開始日時プレフィックスを付与する。

    - broadcast_start_at をJST変換し YYYYMMDD_HHMM_ 形式でプレフィックス
    - broadcast_start_at が None の場合はファイル名をそのまま返す
    - 既にプレフィックスがある場合は重複付与しない
    """
    if broadcast_start_at is None:
        return filename
    if has_datetime_prefix(filename):
        return filename
    jst_dt = broadcast_start_at.astimezone(_JST)
    prefix = jst_dt.strftime("%Y%m%d_%H%M_")
    return f"{prefix}{filename}"
