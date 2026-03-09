"""DatabaseClientのテスト"""

import sqlite3
from pathlib import Path

import pytest

from kirinuki.infra.db import DatabaseClient


def _setup_db_with_videos(tmp_path: Path) -> DatabaseClient:
    """テスト用DBにチャンネルと動画を追加する"""
    db = DatabaseClient(tmp_path / "test.db")
    conn = sqlite3.connect(str(db.db_path))
    conn.execute(
        "INSERT INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
        ("UC123", "テストチャンネル", "https://youtube.com/c/test"),
    )
    for i in range(3):
        conn.execute(
            """INSERT INTO videos (video_id, channel_id, title, published_at,
               duration_seconds, subtitle_language, is_auto_subtitle)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (f"vid{i:03d}", "UC123", f"テスト動画 {i}",
             f"2026-01-{i+1:02d}T00:00:00", 3600, "ja", 0),
        )
    conn.commit()
    conn.close()
    return db


class TestGetVideosByIds:
    def test_returns_existing_videos(self, tmp_path: Path) -> None:
        db = _setup_db_with_videos(tmp_path)
        result = db.get_videos_by_ids(["vid000", "vid001"])
        assert len(result) == 2
        ids = {r["video_id"] for r in result}
        assert ids == {"vid000", "vid001"}

    def test_excludes_missing_ids(self, tmp_path: Path) -> None:
        db = _setup_db_with_videos(tmp_path)
        result = db.get_videos_by_ids(["vid000", "MISSING"])
        assert len(result) == 1
        assert result[0]["video_id"] == "vid000"

    def test_all_missing_returns_empty(self, tmp_path: Path) -> None:
        db = _setup_db_with_videos(tmp_path)
        result = db.get_videos_by_ids(["MISSING1", "MISSING2"])
        assert result == []

    def test_return_dict_keys_match_get_latest_videos(self, tmp_path: Path) -> None:
        db = _setup_db_with_videos(tmp_path)
        by_ids = db.get_videos_by_ids(["vid000"])
        latest = db.get_latest_videos("UC123", 1)
        assert set(by_ids[0].keys()) == set(latest[0].keys())


class TestDatabaseInit:
    def test_creates_segment_recommendations_table(self, tmp_path: Path) -> None:
        db = DatabaseClient(tmp_path / "test.db")
        conn = sqlite3.connect(str(db.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='segment_recommendations'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_segment_recommendations_schema(self, tmp_path: Path) -> None:
        db = DatabaseClient(tmp_path / "test.db")
        conn = sqlite3.connect(str(db.db_path))
        cursor = conn.execute("PRAGMA table_info(segment_recommendations)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert "id" in columns
        assert "segment_id" in columns
        assert "video_id" in columns
        assert "score" in columns
        assert "summary" in columns
        assert "appeal" in columns
        assert "prompt_version" in columns
        assert "created_at" in columns
        conn.close()

    def test_unique_index_on_segment_prompt(self, tmp_path: Path) -> None:
        db = DatabaseClient(tmp_path / "test.db")
        conn = sqlite3.connect(str(db.db_path))
        cursor = conn.execute("PRAGMA index_list(segment_recommendations)")
        indexes = cursor.fetchall()
        index_names = [idx[1] for idx in indexes]
        assert "idx_recommendations_segment_prompt" in index_names
        conn.close()

    def test_index_on_video_id(self, tmp_path: Path) -> None:
        db = DatabaseClient(tmp_path / "test.db")
        conn = sqlite3.connect(str(db.db_path))
        cursor = conn.execute("PRAGMA index_list(segment_recommendations)")
        indexes = cursor.fetchall()
        index_names = [idx[1] for idx in indexes]
        assert "idx_recommendations_video_id" in index_names
        conn.close()

    def test_creates_all_required_tables(self, tmp_path: Path) -> None:
        """channels, videos, subtitles, segments, segment_recommendations が作成される"""
        db = DatabaseClient(tmp_path / "test.db")
        conn = sqlite3.connect(str(db.db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        expected = {"channels", "videos", "subtitles", "segments", "segment_recommendations"}
        assert expected.issubset(tables)
        conn.close()
