"""resolve_video_id() のユニットテスト"""

import pytest

from kirinuki.core.clip_utils import resolve_video_id
from kirinuki.core.errors import InvalidURLError


class TestResolveVideoId:
    """URL/動画IDの統一解決"""

    def test_direct_video_id(self) -> None:
        """11文字の動画IDが直接渡された場合そのまま返す"""
        assert resolve_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_video_id_with_hyphen(self) -> None:
        """ハイフン含む動画ID"""
        assert resolve_video_id("abc-def_123") == "abc-def_123"

    def test_video_id_with_underscore(self) -> None:
        """アンダースコア含む動画ID"""
        assert resolve_video_id("_abcdefghij") == "_abcdefghij"

    def test_standard_watch_url(self) -> None:
        """youtube.com/watch?v= 形式のURL"""
        assert resolve_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url(self) -> None:
        """youtu.be/ 形式の短縮URL"""
        assert resolve_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_live_url(self) -> None:
        """youtube.com/live/ 形式のURL"""
        assert resolve_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_url_with_extra_params(self) -> None:
        """追加パラメータ付きURL"""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120"
        assert resolve_video_id(url) == "dQw4w9WgXcQ"

    def test_invalid_short_string(self) -> None:
        """短すぎる文字列は例外"""
        with pytest.raises(InvalidURLError):
            resolve_video_id("abc")

    def test_invalid_long_string(self) -> None:
        """12文字以上でURL以外は例外"""
        with pytest.raises(InvalidURLError):
            resolve_video_id("abcdefghijkl")

    def test_empty_string(self) -> None:
        """空文字列は例外"""
        with pytest.raises(InvalidURLError):
            resolve_video_id("")

    def test_invalid_url(self) -> None:
        """非YouTube URLは例外"""
        with pytest.raises(InvalidURLError):
            resolve_video_id("https://example.com/video")

    def test_invalid_characters_in_id(self) -> None:
        """不正な文字を含む11文字は動画IDとして扱わずURL解析へ"""
        with pytest.raises(InvalidURLError):
            resolve_video_id("abc!defghij")
