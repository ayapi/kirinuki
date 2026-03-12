"""yt-dlpクライアントのテスト（モック使用）"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import yt_dlp

from kirinuki.core.errors import AuthenticationRequiredError, VideoUnavailableError
from kirinuki.infra.ytdlp_client import YtdlpClient
from kirinuki.models.config import AppConfig
from kirinuki.models.domain import SkipReason


@pytest.fixture
def client(tmp_path):
    config = AppConfig(db_path=tmp_path / "data.db")
    return YtdlpClient(config)


class TestListChannelVideoIds:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_flat_extraction(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "dQw4w9WgXcQ", "title": "Video 1"},
                {"id": "9bZkp7q19f0", "title": "Video 2"},
                {"id": "JGwWNGJdvx8", "title": "Video 3"},
            ]
        }
        ids = client.list_channel_video_ids("https://youtube.com/c/test")
        assert ids == ["dQw4w9WgXcQ", "9bZkp7q19f0", "JGwWNGJdvx8"]
        # /streams で呼ばれることを確認
        call_url = mock_ydl.extract_info.call_args[0][0]
        assert call_url.endswith("/streams")

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_empty_channel(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"entries": []}
        ids = client.list_channel_video_ids("https://youtube.com/c/empty")
        assert ids == []

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_filters_non_video_ids(self, mock_ydl_cls, client):
        """チャンネルIDなど11文字でないIDはフィルタされる"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "UCU_vZ0kggiHFOxnvHqHt_aQ", "title": "Videos"},
                {"id": "dQw4w9WgXcQ", "title": "Real Video"},
                {"id": "UCU_vZ0kggiHFOxnvHqHt_aQ", "title": "Shorts"},
            ]
        }
        ids = client.list_channel_video_ids("https://youtube.com/@test")
        assert ids == ["dQw4w9WgXcQ"]

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_deduplicates_video_ids(self, mock_ydl_cls, client):
        """重複する動画IDが除去される"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "dQw4w9WgXcQ", "title": "Video 1"},
                {"id": "dQw4w9WgXcQ", "title": "Video 1 dup"},
                {"id": "9bZkp7q19f0", "title": "Video 2"},
            ]
        }
        ids = client.list_channel_video_ids("https://youtube.com/@test")
        assert ids == ["dQw4w9WgXcQ", "9bZkp7q19f0"]

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_url_with_tab_suffix_normalized(self, mock_ydl_cls, client):
        """既にタブパスがあるURLは正規化されて /streams が付く"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"entries": []}
        client.list_channel_video_ids("https://youtube.com/@test/videos")
        call_url = mock_ydl.extract_info.call_args[0][0]
        assert call_url == "https://youtube.com/@test/streams"


class TestFetchVideoMetadata:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_metadata(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Test Video",
            "upload_date": "20240101",
            "duration": 3600,
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.video_id == "vid1"
        assert meta.title == "Test Video"
        assert meta.duration_seconds == 3600

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_metadata_live_status_was_live(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Live Stream",
            "upload_date": "20240101",
            "duration": 7200,
            "live_status": "was_live",
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.live_status == "was_live"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_metadata_live_status_not_live(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Regular Video",
            "upload_date": "20240101",
            "duration": 600,
            "live_status": "not_live",
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.live_status == "not_live"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_metadata_live_status_none(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Unknown Video",
            "upload_date": "20240101",
            "duration": 600,
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.live_status is None


class TestFetchVideoMetadataBroadcastStartAt:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_release_timestamp_extracted(self, mock_ydl_cls, client):
        """release_timestampがbroadcast_start_atに変換される"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Live Stream",
            "upload_date": "20240615",
            "duration": 7200,
            "live_status": "was_live",
            "release_timestamp": 1718467200,  # 2024-06-15T16:00:00Z
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.broadcast_start_at is not None
        assert meta.broadcast_start_at == datetime(2024, 6, 15, 16, 0, 0, tzinfo=timezone.utc)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_no_release_timestamp_returns_none(self, mock_ydl_cls, client):
        """release_timestampがない場合broadcast_start_atはNone"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Regular Video",
            "upload_date": "20240101",
            "duration": 600,
        }
        meta = client.fetch_video_metadata("vid1")
        assert meta.broadcast_start_at is None


class TestFetchSubtitle:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_json3_subtitle_from_file(self, mock_ydl_cls, client, tmp_path):
        """json3ファイルが書き出された場合にSubtitleDataが返る"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        json3_content = '{"events":[{"tStartMs":0,"dDurationMs":5000,"segs":[{"utf8":"こんにちは"}]},{"tStartMs":5000,"dDurationMs":3000,"segs":[{"utf8":"テスト"}]}]}'

        def fake_extract(url, download=False):
            # 一時ディレクトリ内にjson3ファイルを書き出す
            opts = mock_ydl_cls.call_args[0][0]
            outtmpl = opts.get("outtmpl", "")
            # outtmplからディレクトリを取得
            from pathlib import Path
            tmpdir = Path(outtmpl).parent
            sub_file = tmpdir / "vid1.ja.json3"
            sub_file.write_text(json3_content, encoding="utf-8")
            return {
                "id": "vid1",
                "title": "Test",
                "duration": 100,
                "subtitles": {"ja": [{"ext": "json3"}]},
                "automatic_captions": {},
                "requested_subtitles": {
                    "ja": {
                        "ext": "json3",
                        "filepath": str(sub_file),
                    }
                },
            }

        mock_ydl.extract_info.side_effect = fake_extract

        subtitle_data, skip_reason = client.fetch_subtitle("vid1")
        assert subtitle_data is not None
        assert skip_reason is None
        assert subtitle_data.language == "ja"
        assert not subtitle_data.is_auto_generated
        assert len(subtitle_data.entries) == 2
        assert subtitle_data.entries[0].text == "こんにちは"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_vtt_subtitle_from_file(self, mock_ydl_cls, client):
        """vttファイルが書き出された場合にSubtitleDataが返る"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        vtt_content = """WEBVTT

00:00:00.000 --> 00:00:05.000
こんにちは

00:00:05.000 --> 00:00:08.000
テスト
"""

        def fake_extract(url, download=False):
            from pathlib import Path
            opts = mock_ydl_cls.call_args[0][0]
            tmpdir = Path(opts.get("outtmpl", "")).parent
            sub_file = tmpdir / "vid1.ja.vtt"
            sub_file.write_text(vtt_content, encoding="utf-8")
            return {
                "id": "vid1",
                "title": "Test",
                "duration": 100,
                "subtitles": {},
                "automatic_captions": {"ja": [{"ext": "vtt"}]},
                "requested_subtitles": {
                    "ja": {
                        "ext": "vtt",
                        "filepath": str(sub_file),
                    }
                },
            }

        mock_ydl.extract_info.side_effect = fake_extract

        subtitle_data, skip_reason = client.fetch_subtitle("vid1")
        assert subtitle_data is not None
        assert skip_reason is None
        assert subtitle_data.is_auto_generated
        assert len(subtitle_data.entries) == 2

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_no_subtitle_returns_skip_reason(self, mock_ydl_cls, client):
        """字幕なしの場合SkipReasonが返る"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "title": "Test",
            "duration": 100,
            "subtitles": {},
            "automatic_captions": {},
            "requested_subtitles": None,
        }
        subtitle_data, skip_reason = client.fetch_subtitle("vid1")
        assert subtitle_data is None
        assert skip_reason == SkipReason.NO_SUBTITLE_AVAILABLE


class TestIsAuthError:
    def test_sign_in(self, client):
        assert client._is_auth_error("Sign in to confirm your age") is True

    def test_login(self, client):
        assert client._is_auth_error("Please login to view this content") is True

    def test_members_only(self, client):
        assert client._is_auth_error("This is members-only content") is True

    def test_join_channel(self, client):
        assert client._is_auth_error("Join this channel to get access") is True

    def test_sign_in_lowercase(self, client):
        assert client._is_auth_error("please sign in to continue") is True

    def test_join_channel_mixed_case(self, client):
        assert client._is_auth_error("JOIN THIS CHANNEL to get access") is True

    def test_generic_error(self, client):
        assert client._is_auth_error("Video has been removed") is False

    def test_empty(self, client):
        assert client._is_auth_error("") is False


class TestFetchVideoMetadataErrors:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_error_auth(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError(
            "Join this channel to get access to members-only content"
        )
        with pytest.raises(AuthenticationRequiredError):
            client.fetch_video_metadata("vid1")

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_error_unavailable(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError("Video unavailable")
        with pytest.raises(VideoUnavailableError) as exc_info:
            client.fetch_video_metadata("vid1")
        assert exc_info.value.video_id == "vid1"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_info_none_raises_unavailable(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = None
        with pytest.raises(VideoUnavailableError) as exc_info:
            client.fetch_video_metadata("vid1")
        assert exc_info.value.video_id == "vid1"


class TestCookieAuth:
    def test_cookie_option_set_when_file_exists(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        c = YtdlpClient(config)
        opts = c._base_opts()
        assert opts.get("cookiefile") == str(cookie_file)

    def test_no_cookie_option_when_file_not_exists(self, tmp_path):
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=tmp_path / "nonexistent_cookies.txt",
        )
        c = YtdlpClient(config)
        opts = c._base_opts()
        assert "cookiefile" not in opts


class TestBaseOptsIgnoreNoFormatsError:
    """_base_opts()がignore_no_formats_error=Trueを含むことを検証する (Task 2.1)"""

    def test_base_opts_contains_ignore_no_formats_error(self, client):
        opts = client._base_opts()
        assert opts.get("ignore_no_formats_error") is True

    def test_base_opts_contains_skip_download(self, client):
        opts = client._base_opts()
        assert opts.get("skip_download") is True

    def test_base_opts_with_cookie(self, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        c = YtdlpClient(config)
        opts = c._base_opts()
        assert opts.get("ignore_no_formats_error") is True
        assert opts.get("skip_download") is True
        assert opts.get("cookiefile") == str(cookie_file)


class TestDownloadVideoNoFormatSuppression:
    """download_video()がignore_no_formats_errorの影響を受けないことを検証する (Task 2.2)"""

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_opts_no_ignore_no_formats_error(
        self, mock_ydl_cls, client, tmp_path
    ):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "requested_downloads": [{"filepath": str(tmp_path / "vid1.mp4")}],
        }
        client.download_video("vid1", tmp_path)
        call_opts = mock_ydl_cls.call_args[0][0]
        assert "ignore_no_formats_error" not in call_opts

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_download_opts_has_format_spec(self, mock_ydl_cls, client, tmp_path):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "id": "vid1",
            "requested_downloads": [{"filepath": str(tmp_path / "vid1.mp4")}],
        }
        client.download_video("vid1", tmp_path)
        call_opts = mock_ydl_cls.call_args[0][0]
        assert call_opts.get("format") == "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo*+bestaudio*/best*"


class TestFormatUnavailableWithMetadata:
    """フォーマット不可動画でもメタデータ・字幕が取得できることを検証する (Task 2.3)"""

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_metadata_success_despite_no_formats(self, mock_ydl_cls, client):
        """ignore_no_formats_errorにより、フォーマット不可でもメタデータが返る"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        # フォーマット不可でもメタデータは返るシナリオ
        mock_ydl.extract_info.return_value = {
            "id": "restricted1",
            "title": "Format Restricted Video",
            "upload_date": "20240601",
            "duration": 7200,
            "formats": [],  # フォーマットなし
        }
        meta = client.fetch_video_metadata("restricted1")
        assert meta.video_id == "restricted1"
        assert meta.title == "Format Restricted Video"
        assert meta.duration_seconds == 7200

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_subtitle_success_despite_no_formats(self, mock_ydl_cls, client):
        """ignore_no_formats_errorにより、フォーマット不可でも字幕が返る"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        json3_content = '{"events":[{"tStartMs":0,"dDurationMs":5000,"segs":[{"utf8":"テスト字幕"}]}]}'

        def fake_extract(url, download=False):
            from pathlib import Path
            opts = mock_ydl_cls.call_args[0][0]
            tmpdir = Path(opts.get("outtmpl", "")).parent
            sub_file = tmpdir / "restricted1.ja.json3"
            sub_file.write_text(json3_content, encoding="utf-8")
            return {
                "id": "restricted1",
                "title": "Format Restricted Video",
                "duration": 100,
                "formats": [],
                "subtitles": {"ja": [{"ext": "json3"}]},
                "automatic_captions": {},
                "requested_subtitles": {
                    "ja": {
                        "ext": "json3",
                        "filepath": str(sub_file),
                    }
                },
            }

        mock_ydl.extract_info.side_effect = fake_extract

        subtitle_data, skip_reason = client.fetch_subtitle("restricted1")
        assert subtitle_data is not None
        assert skip_reason is None
        assert subtitle_data.video_id == "restricted1"
        assert subtitle_data.entries[0].text == "テスト字幕"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_truly_unavailable_still_raises(self, mock_ydl_cls, client):
        """真に利用不可な動画はVideoUnavailableErrorがraiseされる"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError(
            "Video unavailable: This video has been removed"
        )
        with pytest.raises(VideoUnavailableError) as exc_info:
            client.fetch_video_metadata("deleted1")
        assert exc_info.value.video_id == "deleted1"


class TestParseVtt:
    """VTTパーサーのユニットテスト"""

    def test_basic_vtt(self, client):
        vtt = """WEBVTT

00:00:00.000 --> 00:00:05.000
こんにちは

00:00:05.000 --> 00:00:08.000
テスト
"""
        entries = client._parse_vtt(vtt)
        assert len(entries) == 2
        assert entries[0].text == "こんにちは"
        assert entries[0].start_ms == 0
        assert entries[0].duration_ms == 5000
        assert entries[1].text == "テスト"
        assert entries[1].start_ms == 5000
        assert entries[1].duration_ms == 3000

    def test_html_tag_removal(self, client):
        vtt = """WEBVTT

00:00:00.000 --> 00:00:05.000
<c.colorCCCCCC>テスト</c><c> テキスト</c>
"""
        entries = client._parse_vtt(vtt)
        assert len(entries) == 1
        assert entries[0].text == "テスト テキスト"

    def test_empty_vtt(self, client):
        vtt = "WEBVTT\n\n"
        entries = client._parse_vtt(vtt)
        assert entries == []

    def test_timestamp_precision(self, client):
        vtt = """WEBVTT

01:02:03.456 --> 01:05:10.789
テスト
"""
        entries = client._parse_vtt(vtt)
        assert len(entries) == 1
        assert entries[0].start_ms == 3723456  # 1*3600000 + 2*60000 + 3*1000 + 456
        # end_ms = 1*3600000 + 5*60000 + 10*1000 + 789 = 3910789
        assert entries[0].duration_ms == 3910789 - 3723456

    def test_note_block_skipped(self, client):
        vtt = """WEBVTT

NOTE
This is a comment

00:00:00.000 --> 00:00:05.000
テスト
"""
        entries = client._parse_vtt(vtt)
        assert len(entries) == 1
        assert entries[0].text == "テスト"

    def test_kind_language_headers_skipped(self, client):
        vtt = """WEBVTT
Kind: captions
Language: ja

00:00:00.000 --> 00:00:03.000
テスト
"""
        entries = client._parse_vtt(vtt)
        assert len(entries) == 1
        assert entries[0].text == "テスト"

    def test_invalid_format_returns_empty(self, client):
        entries = client._parse_vtt("not a vtt file at all")
        assert entries == []


class TestFetchSubtitleParseFailed:
    """パース失敗時のSkipReason検証"""

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_parse_failed_returns_skip_reason(self, mock_ydl_cls, client):
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)

        def fake_extract(url, download=False):
            from pathlib import Path
            opts = mock_ydl_cls.call_args[0][0]
            tmpdir = Path(opts.get("outtmpl", "")).parent
            sub_file = tmpdir / "vid1.ja.json3"
            sub_file.write_text("not valid json", encoding="utf-8")
            return {
                "id": "vid1",
                "title": "Test",
                "duration": 100,
                "subtitles": {"ja": [{"ext": "json3"}]},
                "automatic_captions": {},
                "requested_subtitles": {
                    "ja": {"ext": "json3", "filepath": str(sub_file)}
                },
            }

        mock_ydl.extract_info.side_effect = fake_extract

        subtitle_data, skip_reason = client.fetch_subtitle("vid1")
        assert subtitle_data is None
        assert skip_reason == SkipReason.PARSE_FAILED


class TestListChannelVideoIdsStreamsTab:
    """/streams タブからの動画ID取得テスト"""

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_streams_tab_used(self, mock_ydl_cls, client):
        """/streams タブのURLでextract_infoが呼ばれる"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {
            "entries": [
                {"id": "JGwWNGJdvx8", "title": "Stream 1"},
                {"id": "xxxxxxxxxxx", "title": "Stream 2"},
            ]
        }
        ids = client.list_channel_video_ids("https://youtube.com/@test")
        assert ids == ["JGwWNGJdvx8", "xxxxxxxxxxx"]
        call_url = mock_ydl.extract_info.call_args[0][0]
        assert call_url == "https://youtube.com/@test/streams"
        assert mock_ydl.extract_info.call_count == 1

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_fetch_failure_returns_empty(self, mock_ydl_cls, client):
        """取得失敗時は空リスト"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = Exception("Network error")
        ids = client.list_channel_video_ids("https://youtube.com/@test")
        assert ids == []

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_url_with_videos_suffix_normalized_to_streams(self, mock_ydl_cls, client):
        """既に /videos サフィックスがあるURLも /streams に正規化される"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"entries": []}
        client.list_channel_video_ids("https://youtube.com/@test/videos")
        call_url = mock_ydl.extract_info.call_args[0][0]
        assert call_url == "https://youtube.com/@test/streams"

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_url_with_streams_suffix_not_doubled(self, mock_ydl_cls, client):
        """既に /streams サフィックスがあるURLは二重付加しない"""
        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"entries": []}
        client.list_channel_video_ids("https://youtube.com/@test/streams")
        call_url = mock_ydl.extract_info.call_args[0][0]
        assert call_url == "https://youtube.com/@test/streams"


class TestAuthenticationWarning:
    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_auth_error_includes_cookie_hint_when_not_set(self, mock_ydl_cls, tmp_path):
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=tmp_path / "nonexistent_cookies.txt",
        )
        client = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError("Sign in to confirm")

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            client.download_video("vid1", tmp_path)

        assert "cookie set" in str(exc_info.value)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_auth_error_without_cookie_hint_when_set(self, mock_ydl_cls, tmp_path):
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        client = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.side_effect = yt_dlp.DownloadError("Sign in to confirm")

        with pytest.raises(AuthenticationRequiredError) as exc_info:
            client.download_video("vid1", tmp_path)

        assert "cookie set" not in str(exc_info.value)


class TestDownloadSectionCookie:
    """download_section()が設定済みcookieを初回から使用することを検証する"""

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_config_cookie_used_on_first_attempt(self, mock_ydl_cls, tmp_path):
        """コンフィグにcookieがある場合、download_sectionの初回リクエストで使用される"""
        cookie_file = tmp_path / "cookies.txt"
        cookie_file.write_text("# Netscape cookie file")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=cookie_file,
        )
        client = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"id": "vid1"}

        output_path = tmp_path / "output.mp4"
        client.download_section("vid1", 0.0, 10.0, output_path)

        call_opts = mock_ydl_cls.call_args[0][0]
        assert call_opts.get("cookiefile") == str(cookie_file)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_explicit_cookie_takes_precedence(self, mock_ydl_cls, tmp_path):
        """明示的なcookie_file引数がコンフィグより優先される"""
        config_cookie = tmp_path / "config_cookies.txt"
        config_cookie.write_text("# config cookie")
        explicit_cookie = tmp_path / "explicit_cookies.txt"
        explicit_cookie.write_text("# explicit cookie")
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=config_cookie,
        )
        client = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"id": "vid1"}

        output_path = tmp_path / "output.mp4"
        client.download_section("vid1", 0.0, 10.0, output_path, cookie_file=explicit_cookie)

        call_opts = mock_ydl_cls.call_args[0][0]
        assert call_opts.get("cookiefile") == str(explicit_cookie)

    @patch("kirinuki.infra.ytdlp_client.yt_dlp.YoutubeDL")
    def test_no_cookie_when_not_configured(self, mock_ydl_cls, tmp_path):
        """cookieが未設定の場合、cookiefileオプションが設定されない"""
        config = AppConfig(
            db_path=tmp_path / "data.db",
            cookie_file_path=tmp_path / "nonexistent_cookies.txt",
        )
        client = YtdlpClient(config)

        mock_ydl = MagicMock()
        mock_ydl_cls.return_value.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"id": "vid1"}

        output_path = tmp_path / "output.mp4"
        client.download_section("vid1", 0.0, 10.0, output_path)

        call_opts = mock_ydl_cls.call_args[0][0]
        assert "cookiefile" not in call_opts
