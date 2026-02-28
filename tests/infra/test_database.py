"""データベース層のテスト"""

from datetime import datetime, timezone

import pytest

from kirinuki.infra.database import Database
from kirinuki.models.domain import SubtitleEntry


@pytest.fixture
def db(tmp_path):
    """インメモリDBでテスト"""
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    return database


class TestSchema:
    def test_initialize_creates_tables(self, db: Database) -> None:
        tables = db._execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}
        assert "channels" in table_names
        assert "videos" in table_names
        assert "subtitle_lines" in table_names
        assert "segments" in table_names
        assert "schema_version" in table_names

    def test_schema_version(self, db: Database) -> None:
        row = db._execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row[0] == 1

    def test_fts_table_exists(self, db: Database) -> None:
        tables = db._execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}
        assert "subtitle_fts" in table_names


class TestChannelCRUD:
    def test_save_and_get_channel(self, db: Database) -> None:
        db.save_channel("UC123", "Test Channel", "https://youtube.com/c/test")
        ch = db.get_channel("UC123")
        assert ch is not None
        assert ch.name == "Test Channel"

    def test_get_nonexistent_channel(self, db: Database) -> None:
        assert db.get_channel("NOTEXIST") is None

    def test_list_channels(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        channels = db.list_channels()
        assert len(channels) == 2

    def test_update_last_synced(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        now = datetime.now(tz=timezone.utc)
        db.update_channel_last_synced("UC1", now)
        ch = db.get_channel("UC1")
        assert ch is not None
        assert ch.last_synced_at is not None


class TestVideoCRUD:
    def test_save_and_get_video(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video(
            video_id="vid1",
            channel_id="UC1",
            title="Test Video",
            published_at=None,
            duration_seconds=3600,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )
        v = db.get_video("vid1")
        assert v is not None
        assert v.title == "Test Video"

    def test_get_existing_video_ids(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", True)
        ids = db.get_existing_video_ids("UC1")
        assert ids == {"vid1", "vid2"}

    def test_list_videos(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", True)
        videos = db.list_videos("UC1")
        assert len(videos) == 2


class TestSubtitleCRUD:
    def test_save_and_search_subtitles(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        entries = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="こんにちは皆さん"),
            SubtitleEntry(start_ms=5000, duration_ms=5000, text="今日は天気がいいですね"),
        ]
        db.save_subtitle_lines("vid1", entries)

        # FTS検索（trigram: 3文字以上が必要）
        results = db.fts_search("天気が")
        assert len(results) > 0


class TestSegmentCRUD:
    def test_save_and_list_segments(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介と挨拶"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "ゲーム実況開始"},
        ]
        db.save_segments("vid1", segments_data)
        segs = db.list_segments("vid1")
        assert len(segs) == 2
        assert segs[0].summary == "自己紹介と挨拶"

    def test_save_segments_with_vectors(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"},
        ]
        vectors = [[0.1] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)
        segs = db.list_segments("vid1")
        assert len(segs) == 1

    def test_vector_search(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介と挨拶"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "ゲーム実況開始"},
        ]
        vectors = [[0.1] * 1536, [0.9] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)

        results = db.vector_search([0.85] * 1536, limit=5)
        assert len(results) > 0
