"""yt-dlp Python APIラッパー"""

import json
import logging
import re
import tempfile
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
from kirinuki.models.domain import SkipReason, SubtitleEntry

logger = logging.getLogger(__name__)

_YOUTUBE_VIDEO_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
_CHANNEL_TAB_RE = re.compile(
    r"/(videos|streams|shorts|featured|community|channels|about|podcasts|releases|playlists)$"
)


@dataclass
class VideoMeta:
    video_id: str
    title: str
    published_at: datetime | None
    duration_seconds: int
    live_status: str | None = None


@dataclass
class SubtitleData:
    video_id: str
    language: str
    is_auto_generated: bool
    entries: list[SubtitleEntry]


class YtdlpClient:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @staticmethod
    def _common_opts() -> dict:
        """全リクエスト共通のオプション。"""
        return {
            "quiet": True,
            "no_warnings": True,
            "remote_components": ["ejs:github"],
            "js_runtimes": {"node": {}},
        }

    def _base_opts(self) -> dict:
        """情報抽出用ベースオプション。download_video()はこのメソッドを使用しない。"""
        opts: dict = {
            **self._common_opts(),
            "skip_download": True,
            "ignore_no_formats_error": True,
        }
        if self._config.cookie_file_path.exists():
            opts["cookiefile"] = str(self._config.cookie_file_path)
        return opts

    @staticmethod
    def _is_auth_error(msg: str) -> bool:
        lower = msg.lower()
        return (
            "sign in" in lower
            or "login" in lower
            or "members-only" in lower
            or "join this channel" in lower
        )

    def list_channel_video_ids(self, channel_url: str) -> list[str]:
        """チャンネルの /streams タブからライブ配信アーカイブの動画IDを取得する。"""
        base_url = _CHANNEL_TAB_RE.sub("", channel_url.rstrip("/"))
        return self._fetch_tab_video_ids(f"{base_url}/streams")

    def _fetch_tab_video_ids(self, tab_url: str) -> list[str]:
        """単一タブURLから動画IDを取得する。失敗時は空リストを返す。"""
        opts = self._base_opts()
        opts["extract_flat"] = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(tab_url, download=False)
        except Exception as e:
            logger.warning("Failed to fetch tab %s: %s", tab_url, e)
            return []

        if not info or "entries" not in info:
            return []

        seen: set[str] = set()
        video_ids: list[str] = []
        for entry in info["entries"]:
            if not entry or "id" not in entry:
                continue
            vid = entry["id"]
            if _YOUTUBE_VIDEO_ID_RE.match(vid) and vid not in seen:
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
            live_status=info.get("live_status"),
        )

    def fetch_subtitle(
        self, video_id: str
    ) -> tuple[SubtitleData | None, SkipReason | None]:
        """字幕データを取得する。

        yt-dlpのファイル書出し機能を使い、一時ディレクトリに字幕を書き出してから読み込む。

        Returns:
            tuple[SubtitleData | None, SkipReason | None]:
                - 字幕が取得できた場合: (SubtitleData, None)
                - 字幕が取得できなかった場合: (None, SkipReason)
        """
        url = f"https://www.youtube.com/watch?v={video_id}"

        with tempfile.TemporaryDirectory() as tmpdir:
            opts = self._base_opts()
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitleslangs"] = ["ja"]
            opts["outtmpl"] = str(Path(tmpdir) / f"{video_id}.%(ext)s")

            logger.debug("fetch_subtitle opts: %s", opts)

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
            except yt_dlp.DownloadError as e:
                msg = str(e)
                if self._is_auth_error(msg):
                    raise AuthenticationRequiredError(
                        f"認証が必要です ({video_id}): {msg}"
                    ) from e
                raise VideoUnavailableError(video_id, msg) from e

            if not info:
                return None, SkipReason.FETCH_FAILED

            requested = info.get("requested_subtitles")

            if not requested or "ja" not in requested:
                subtitles = info.get("subtitles", {})
                auto_captions = info.get("automatic_captions", {})
                logger.debug(
                    "No requested_subtitles for %s. subtitles keys: %s, automatic_captions keys: %s",
                    video_id,
                    list(subtitles.keys()),
                    list(auto_captions.keys()),
                )
                return None, SkipReason.NO_SUBTITLE_AVAILABLE

            sub_info = requested["ja"]

            # 手動字幕優先判定
            subtitles = info.get("subtitles", {})
            auto_captions = info.get("automatic_captions", {})
            is_auto = "ja" not in subtitles and "ja" in auto_captions

            # ファイルから字幕データを読み込む
            filepath = sub_info.get("filepath")
            ext = sub_info.get("ext", "")

            if filepath and Path(filepath).exists():
                raw_data = Path(filepath).read_text(encoding="utf-8")
            else:
                # filepathがない場合、一時ディレクトリ内の字幕ファイルを探す
                sub_files = list(Path(tmpdir).glob(f"{video_id}.ja.*"))
                if not sub_files:
                    logger.debug(
                        "Subtitle file not found in tmpdir for %s (ext=%s)",
                        video_id,
                        ext,
                    )
                    return None, SkipReason.NO_SUBTITLE_AVAILABLE
                filepath = str(sub_files[0])
                ext = sub_files[0].suffix.lstrip(".")
                raw_data = sub_files[0].read_text(encoding="utf-8")

            if not raw_data.strip():
                return None, SkipReason.NO_SUBTITLE_AVAILABLE

            # 拡張子に応じてパーサーを呼び分ける
            if ext == "json3":
                entries = self._parse_json3(raw_data)
            elif ext in ("vtt", "srv3"):
                entries = self._parse_vtt(raw_data)
            else:
                # 未知のフォーマットはまずjson3、次にvttとして試す
                entries = self._parse_json3(raw_data)
                if not entries:
                    entries = self._parse_vtt(raw_data)

            if not entries:
                logger.warning(
                    "Failed to parse subtitle for %s (ext=%s)", video_id, ext
                )
                return None, SkipReason.PARSE_FAILED

            return (
                SubtitleData(
                    video_id=video_id,
                    language="ja",
                    is_auto_generated=is_auto,
                    entries=entries,
                ),
                None,
            )

    @staticmethod
    def _parse_vtt(raw_data: str) -> list[SubtitleEntry]:
        """VTT（WebVTT）フォーマットの字幕をパースする。"""
        timestamp_re = re.compile(
            r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
        )
        tag_re = re.compile(r"<[^>]+>")
        entries: list[SubtitleEntry] = []
        lines = raw_data.splitlines()
        i = 0
        in_note = False
        while i < len(lines):
            line = lines[i].strip()

            # NOTEブロックをスキップ
            if line.startswith("NOTE"):
                in_note = True
                i += 1
                continue
            if in_note:
                if line == "":
                    in_note = False
                i += 1
                continue

            # ヘッダー・空行をスキップ
            if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
                i += 1
                continue

            m = timestamp_re.match(line)
            if m:
                start_ms = (
                    int(m.group(1)) * 3600000
                    + int(m.group(2)) * 60000
                    + int(m.group(3)) * 1000
                    + int(m.group(4))
                )
                end_ms = (
                    int(m.group(5)) * 3600000
                    + int(m.group(6)) * 60000
                    + int(m.group(7)) * 1000
                    + int(m.group(8))
                )
                duration_ms = end_ms - start_ms

                # テキスト行を収集
                text_lines: list[str] = []
                i += 1
                while i < len(lines) and lines[i].strip():
                    # 数値のみの行（キュー番号）はスキップ
                    stripped = lines[i].strip()
                    if not stripped.isdigit():
                        # HTMLタグを除去
                        clean = tag_re.sub("", stripped)
                        if clean.strip():
                            text_lines.append(clean.strip())
                    i += 1

                text = " ".join(text_lines).strip()
                if text:
                    entries.append(
                        SubtitleEntry(
                            start_ms=start_ms,
                            duration_ms=duration_ms,
                            text=text,
                        )
                    )
            else:
                i += 1

        return entries

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
        """動画を指定ディレクトリにダウンロードし、ファイルパスを返す。

        認証が必要な動画（メンバー限定等）は自動検出し、Cookieファイルが
        存在すればリトライする。
        """
        opts: dict = {
            **self._common_opts(),
            "format": (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/best[ext=mp4]"
                "/bestvideo*+bestaudio*/best*"
            ),
            "format_sort": ["proto:https"],
            "outtmpl": str(output_dir / f"{video_id}.%(ext)s"),
        }
        used_cookie = False
        if cookie_file:
            opts["cookiefile"] = str(cookie_file)
            used_cookie = True
        elif self._config.cookie_file_path.exists():
            opts["cookiefile"] = str(self._config.cookie_file_path)
            used_cookie = True

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            if self._is_auth_error(msg):
                if not used_cookie and self._config.cookie_file_path.exists():
                    return self._download_video_with_cookie(
                        opts, url, output_dir, video_id,
                    )
                hint = msg
                if not self._config.cookie_file_path.exists():
                    hint += "\ncookiesが未設定です。`kirinuki cookie set` で設定してください。"
                raise AuthenticationRequiredError(
                    f"認証が必要です。Cookieファイルを設定してください: {hint}"
                ) from e
            # Cookie未使用かつコンフィグにCookieがあれば、
            # メンバー限定動画の可能性があるのでリトライ
            if not used_cookie and self._config.cookie_file_path.exists():
                return self._download_video_with_cookie(
                    opts, url, output_dir, video_id,
                )
            raise VideoDownloadError(
                f"動画のダウンロードに失敗しました: {msg}"
            ) from e

        assert info is not None
        filepath = info["requested_downloads"][0]["filepath"]
        return Path(filepath)

    def _download_video_with_cookie(
        self,
        opts: dict,
        url: str,
        output_dir: Path,
        video_id: str,
    ) -> Path:
        """Cookie付きで動画ダウンロードをリトライする。"""
        opts["cookiefile"] = str(self._config.cookie_file_path)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            raise AuthenticationRequiredError(
                "認証が必要です。Cookieを更新してください"
                f" (`kirinuki cookie set`): {msg}"
            ) from e
        assert info is not None
        filepath = info["requested_downloads"][0]["filepath"]
        return Path(filepath)

    def download_section(
        self,
        video_id: str,
        start_seconds: float,
        end_seconds: float,
        output_path: Path,
        cookie_file: Path | None = None,
    ) -> Path:
        """指定時間範囲のフラグメントのみをダウンロードし、出力先に保存する。

        yt-dlp の download_ranges API を使用。DASH形式のフラグメントレベルで
        部分ダウンロードを行い、ffmpegによるトリムを一体処理する。

        認証が必要な動画（メンバー限定等）は自動検出し、Cookieファイルが
        存在すればリトライする。

        Raises:
            VideoDownloadError: ダウンロード失敗
            AuthenticationRequiredError: 認証が必要だがCookieが未設定
        """
        from yt_dlp.utils import download_range_func

        opts: dict = {
            **self._common_opts(),
            "format": (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                "/best[ext=mp4]"
                "/bestvideo*+bestaudio*/best*"
            ),
            "format_sort": ["proto:https"],
            "download_ranges": download_range_func(
                None, [(start_seconds, end_seconds)]
            ),
            "outtmpl": str(output_path),
        }
        used_cookie = False
        if cookie_file:
            opts["cookiefile"] = str(cookie_file)
            used_cookie = True
        elif self._config.cookie_file_path.exists():
            opts["cookiefile"] = str(self._config.cookie_file_path)
            used_cookie = True

        url = f"https://www.youtube.com/watch?v={video_id}"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            if self._is_auth_error(msg):
                if not used_cookie and self._config.cookie_file_path.exists():
                    return self._download_section_with_cookie(
                        opts, url, output_path,
                    )
                raise AuthenticationRequiredError(
                    "認証が必要です。`kirinuki cookie set` で"
                    f"Cookieを設定してください: {msg}"
                ) from e
            # Cookie未使用かつコンフィグにCookieがあれば、
            # メンバー限定動画の可能性があるのでリトライ
            if not used_cookie and self._config.cookie_file_path.exists():
                return self._download_section_with_cookie(
                    opts, url, output_path,
                )
            raise VideoDownloadError(
                f"動画のダウンロードに失敗しました: {msg}"
            ) from e

        return output_path

    def _download_section_with_cookie(
        self,
        opts: dict,
        url: str,
        output_path: Path,
    ) -> Path:
        """Cookie付きでダウンロードをリトライする。

        認証が必要と推定してリトライしているため、ここでも失敗した場合は
        認証エラー（Cookie期限切れ等）として扱う。
        """
        opts["cookiefile"] = str(self._config.cookie_file_path)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
        except yt_dlp.DownloadError as e:
            msg = str(e)
            raise AuthenticationRequiredError(
                "認証が必要です。Cookieを更新してください"
                f" (`kirinuki cookie set`): {msg}"
            ) from e
        return output_path

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
