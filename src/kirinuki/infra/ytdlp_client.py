"""yt-dlp Python APIラッパー"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yt_dlp

from kirinuki.core.errors import (
    AuthenticationRequiredError,
    VideoDownloadError,
    VideoUnavailableError,
)
from kirinuki.models.config import AppConfig
from kirinuki.models.domain import SubtitleEntry

logger = logging.getLogger(__name__)

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")


@dataclass
class VideoMeta:
    video_id: str
    title: str
    published_at: datetime | None
    duration_seconds: int


@dataclass
class SubtitleData:
    video_id: str
    language: str
    is_auto_generated: bool
    entries: list[SubtitleEntry]


class YtdlpClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def _base_opts(self) -> dict:
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if self._config.cookie_file_path.exists():
            opts["cookiefile"] = str(self._config.cookie_file_path)
        return opts

    @staticmethod
    def _is_auth_error(msg: str) -> bool:
        lower = msg.lower()
        return (
            "Sign in" in msg
            or "login" in lower
            or "members-only" in lower
            or "Join this channel" in msg
        )

    def list_channel_video_ids(self, channel_url: str) -> list[str]:
        opts = self._base_opts()
        opts["extract_flat"] = True

        # チャンネルのメインURLだとタブ(Videos/Shorts/Live)のエントリが返る。
        # /videos を付加して動画タブから直接動画IDを取得する。
        normalized = channel_url.rstrip("/")
        if not normalized.endswith("/videos"):
            normalized += "/videos"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(normalized, download=False)
        if not info or "entries" not in info:
            return []

        seen: set[str] = set()
        video_ids: list[str] = []
        for entry in info["entries"]:
            if not entry or "id" not in entry:
                continue
            vid = entry["id"]
            # YouTube動画IDは11文字。チャンネルID等を除外する。
            if not _YOUTUBE_VIDEO_ID_RE.match(vid):
                continue
            if vid not in seen:
                seen.add(vid)
                video_ids.append(vid)
        return video_ids

    def fetch_video_metadata(self, video_id: str) -> VideoMeta:
        opts = self._base_opts()
        url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            if self._is_auth_error(msg):
                raise AuthenticationRequiredError(
                    f"認証が必要です ({video_id}): {msg}"
                ) from e
            raise VideoUnavailableError(video_id, msg) from e
        if info is None:
            raise VideoUnavailableError(video_id, "メタデータを取得できませんでした")
        published_at = None
        upload_date = info.get("upload_date")
        if upload_date:
            try:
                published_at = datetime.strptime(upload_date, "%Y%m%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                pass
        return VideoMeta(
            video_id=info["id"],
            title=info.get("title", ""),
            published_at=published_at,
            duration_seconds=int(info.get("duration", 0)),
        )

    def fetch_subtitle(self, video_id: str) -> SubtitleData | None:
        opts = self._base_opts()
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = ["ja"]
        opts["subtitlesformat"] = "json3"
        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            if self._is_auth_error(msg):
                raise AuthenticationRequiredError(
                    f"認証が必要です ({video_id}): {msg}"
                ) from e
            raise VideoUnavailableError(video_id, msg) from e

        if not info:
            return None

        requested = info.get("requested_subtitles")
        if not requested:
            return None

        # 手動字幕優先判定
        subtitles = info.get("subtitles", {})
        auto_captions = info.get("automatic_captions", {})
        is_auto = "ja" not in subtitles and "ja" in auto_captions

        sub_info = requested.get("ja")
        if not sub_info:
            return None

        raw_data = sub_info.get("data")
        if not raw_data:
            return None

        entries = self._parse_json3(raw_data)
        if not entries:
            return None

        return SubtitleData(
            video_id=video_id,
            language="ja",
            is_auto_generated=is_auto,
            entries=entries,
        )

    def _parse_json3(self, raw_data: str) -> list[SubtitleEntry]:
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse json3 subtitle data")
            return []

        entries = []
        for event in data.get("events", []):
            start_ms = event.get("tStartMs", 0)
            duration_ms = event.get("dDurationMs", 0)
            segs = event.get("segs", [])
            text = "".join(seg.get("utf8", "") for seg in segs).strip()
            if text:
                entries.append(
                    SubtitleEntry(start_ms=start_ms, duration_ms=duration_ms, text=text)
                )
        return entries

    def download_video(
        self,
        video_id: str,
        output_dir: Path,
        cookie_file: Path | None = None,
    ) -> Path:
        """動画を指定ディレクトリにダウンロードし、ファイルパスを返す。"""
        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "outtmpl": str(output_dir / f"{video_id}.%(ext)s"),
        }
        if cookie_file:
            opts["cookiefile"] = str(cookie_file)
        elif self._config.cookie_file_path.exists():
            opts["cookiefile"] = str(self._config.cookie_file_path)

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            if self._is_auth_error(msg):
                hint = msg
                if not self._config.cookie_file_path.exists():
                    hint += "\ncookiesが未設定です。`kirinuki cookie set` で設定してください。"
                raise AuthenticationRequiredError(
                    f"認証が必要です。Cookieファイルを設定してください: {hint}"
                ) from e
            raise VideoDownloadError(
                f"動画のダウンロードに失敗しました: {msg}"
            ) from e

        assert info is not None
        filepath = info["requested_downloads"][0]["filepath"]
        return Path(filepath)

    def resolve_channel_name(self, channel_url: str) -> tuple[str, str]:
        """チャンネルURLからチャンネルIDと名前を取得する"""
        opts = self._base_opts()
        opts["extract_flat"] = True
        opts["playlist_items"] = "0"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)
        assert info is not None
        channel_id = info.get("channel_id", info.get("id", ""))
        channel_name = info.get("channel", info.get("title", info.get("uploader", "")))
        return channel_id, channel_name
