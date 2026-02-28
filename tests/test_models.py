"""モデルとConfig設定のテスト"""

import os
from pathlib import Path

import pytest

from kirinuki.models.config import AppConfig
from kirinuki.models.domain import (
    Channel,
    SearchResult,
    Segment,
    SubtitleEntry,
    SubtitleLine,
    Video,
)


class TestAppConfig:
    def test_defaults(self, tmp_path: Path) -> None:
        config = AppConfig(db_path=tmp_path / "data.db")
        assert config.llm_model == "claude-haiku-4-5-20251001"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_dimensions == 1536
        assert config.cookie_file_path is None

    def test_from_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KIRINUKI_ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("KIRINUKI_OPENAI_API_KEY", "test-openai")
        monkeypatch.setenv("KIRINUKI_COOKIE_FILE_PATH", "/tmp/cookies.txt")
        config = AppConfig(db_path=tmp_path / "data.db")
        assert config.anthropic_api_key == "test-key"
        assert config.openai_api_key == "test-openai"
        assert config.cookie_file_path == Path("/tmp/cookies.txt")


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
