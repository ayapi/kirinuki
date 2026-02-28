"""DatabaseClientのテスト"""

import sqlite3
from pathlib import Path

import pytest

from kirinuki.infra.db import DatabaseClient


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
