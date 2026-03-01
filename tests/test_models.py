"""モデルとConfig設定のテスト"""

import os
from pathlib import Path

import pytest

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import (
    Channel,
    MatchType,
    SearchResult,
    Segment,
    SkipReason,
    SubtitleEntry,
    SubtitleLine,
    SyncResult,
    Video,
)


class TestAppConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        config = AppConfig(db_path=tmp_path / "data.db")
        assert config.llm_model == "claude-haiku-4-5-20251001"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_dimensions == 1536
        assert config.cookie_file_path == Path.home() / ".kirinuki" / "cookies.txt"

    def test_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KIRINUKI_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("KIRINUKI_OPENAI_API_KEY", "test-openai")
        config = AppConfig(db_path=tmp_path / "data.db")
        assert config.anthropic_api_key == "test-key"
        assert config.openai_api_key == "test-openai"


class TestDomainModels:
    def test_channel(self) -> None:
        ch = Channel(channel_id="UC123", name="Test Channel", url="https://youtube.com/c/test")
        assert ch.channel_id == "UC123"
        assert ch.last_synced_at is None

    def test_video(self) -> None:
        v = Video(
            video_id="abc123",
            channel_id="UC123",
            title="Test Video",
            duration_seconds=3600,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )
        assert v.video_id == "abc123"
        assert v.published_at is None

    def test_subtitle_entry(self) -> None:
        e = SubtitleEntry(start_ms=1000, duration_ms=5000, text="テスト字幕")
        assert e.start_ms == 1000

    def test_subtitle_line(self) -> None:
        sl = SubtitleLine(
            id=1, video_id="abc123", start_ms=1000, duration_ms=5000, text="テスト字幕"
        )
        assert sl.video_id == "abc123"

    def test_segment(self) -> None:
        s = Segment(id=1, video_id="abc123", start_ms=0, end_ms=60000, summary="テスト話題")
        assert s.summary == "テスト話題"

    def test_search_result(self) -> None:
        r = SearchResult(
            video_title="Test Video",
            channel_name="Test Channel",
            start_time_ms=0,
            end_time_ms=60000,
            summary="テスト話題",
            youtube_url="https://youtube.com/watch?v=abc123&t=0",
            score=0.95,
        )
        assert r.score == 0.95

    def test_search_result_match_type_keyword(self) -> None:
        r = SearchResult(
            video_title="Test Video",
            channel_name="Test Channel",
            start_time_ms=0,
            end_time_ms=60000,
            summary="テスト話題",
            youtube_url="https://youtube.com/watch?v=abc123&t=0",
            match_type=MatchType.KEYWORD,
            snippet="マッチした字幕テキスト",
        )
        assert r.match_type == MatchType.KEYWORD
        assert r.snippet == "マッチした字幕テキスト"
        assert r.similarity is None

    def test_search_result_match_type_semantic(self) -> None:
        r = SearchResult(
            video_title="Test Video",
            channel_name="Test Channel",
            start_time_ms=0,
            end_time_ms=60000,
            summary="テスト話題",
            youtube_url="https://youtube.com/watch?v=abc123&t=0",
            match_type=MatchType.SEMANTIC,
            similarity=0.85,
        )
        assert r.match_type == MatchType.SEMANTIC
        assert r.snippet is None
        assert r.similarity == 0.85

    def test_search_result_match_type_hybrid(self) -> None:
        r = SearchResult(
            video_title="Test Video",
            channel_name="Test Channel",
            start_time_ms=0,
            end_time_ms=60000,
            summary="テスト話題",
            youtube_url="https://youtube.com/watch?v=abc123&t=0",
            match_type=MatchType.HYBRID,
            snippet="マッチした字幕",
            similarity=0.9,
        )
        assert r.match_type == MatchType.HYBRID
        assert r.snippet == "マッチした字幕"
        assert r.similarity == 0.9

    def test_search_result_defaults_backward_compatible(self) -> None:
        r = SearchResult(
            video_title="Test Video",
            channel_name="Test Channel",
            start_time_ms=0,
            end_time_ms=60000,
            summary="テスト話題",
            youtube_url="https://youtube.com/watch?v=abc123&t=0",
        )
        assert r.match_type is None
        assert r.snippet is None
        assert r.similarity is None

    def test_sync_result_new_fields(self) -> None:
        r = SyncResult(auth_errors=3, unavailable_skipped=5)
        assert r.auth_errors == 3
        assert r.unavailable_skipped == 5

    def test_sync_result_defaults(self) -> None:
        r = SyncResult()
        assert r.auth_errors == 0
        assert r.unavailable_skipped == 0
        assert r.not_live_skipped == 0

    def test_sync_result_not_live_skipped(self) -> None:
        r = SyncResult(not_live_skipped=7)
        assert r.not_live_skipped == 7

    def test_sync_result_skip_reasons(self) -> None:
        r = SyncResult(skip_reasons={SkipReason.NO_SUBTITLE_AVAILABLE: 3, SkipReason.PARSE_FAILED: 1})
        assert r.skip_reasons[SkipReason.NO_SUBTITLE_AVAILABLE] == 3
        assert r.skip_reasons[SkipReason.PARSE_FAILED] == 1

    def test_sync_result_skip_reasons_default_empty(self) -> None:
        r = SyncResult()
        assert r.skip_reasons == {}

    def test_sync_result_segmentation_retry_defaults(self) -> None:
        r = SyncResult()
        assert r.segmentation_retried == 0
        assert r.segmentation_retry_failed == 0

    def test_sync_result_segmentation_retry_values(self) -> None:
        r = SyncResult(segmentation_retried=3, segmentation_retry_failed=1)
        assert r.segmentation_retried == 3
        assert r.segmentation_retry_failed == 1


class TestMatchType:
    def test_values(self) -> None:
        assert MatchType.KEYWORD == "keyword"
        assert MatchType.SEMANTIC == "semantic"
        assert MatchType.HYBRID == "hybrid"

    def test_is_str(self) -> None:
        assert isinstance(MatchType.KEYWORD, str)


class TestSkipReason:
    def test_values(self) -> None:
        assert SkipReason.NO_SUBTITLE_AVAILABLE == "no_subtitle_available"
        assert SkipReason.NO_TARGET_LANGUAGE == "no_target_language"
        assert SkipReason.PARSE_FAILED == "parse_failed"
        assert SkipReason.FETCH_FAILED == "fetch_failed"
        assert SkipReason.NOT_LIVE_ARCHIVE == "not_live_archive"

    def test_is_str(self) -> None:
        assert isinstance(SkipReason.NO_SUBTITLE_AVAILABLE, str)


class TestVideoUnavailableError:
    def test_error_attributes(self) -> None:
        from kirinuki.core.errors import VideoUnavailableError

        err = VideoUnavailableError("vid1", "Video has been removed")
        assert err.video_id == "vid1"
        assert "vid1" in str(err)
        assert "Video has been removed" in str(err)

    def test_is_segment_extractor_error(self) -> None:
        from kirinuki.core.errors import SegmentExtractorError, VideoUnavailableError

        err = VideoUnavailableError("vid1", "reason")
        assert isinstance(err, SegmentExtractorError)
