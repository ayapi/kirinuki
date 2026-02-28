"""データベース統合テスト — FTS5・sqlite-vec・マイグレーション"""

import pytest

from kirinuki.infra.database import Database
from kirinuki.models.domain import SubtitleEntry


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    return database


class TestFTS5Japanese:
    """FTS5 trigramによる日本語検索テスト"""

    def _setup_data(self, db: Database) -> None:
        db.save_channel("UC1", "TestCh", "https://youtube.com/c/test")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        entries = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="今日はマインクラフトで遊びます"),
            SubtitleEntry(start_ms=10000, duration_ms=5000, text="ダイヤモンドを探しに行きましょう"),
            SubtitleEntry(start_ms=20000, duration_ms=5000, text="エンダードラゴンを倒します"),
            SubtitleEntry(start_ms=30000, duration_ms=5000, text="ネザーポータルを作ります"),
        ]
        db.save_subtitle_lines("vid1", entries)

    def test_trigram_partial_match(self, db: Database) -> None:
        self._setup_data(db)
        results = db.fts_search("マインクラフト")
        assert len(results) == 1
        assert "マインクラフト" in results[0]["text"]

    def test_trigram_three_chars(self, db: Database) -> None:
        self._setup_data(db)
        # 3文字でマッチ
        results = db.fts_search("ダイヤ")
        assert len(results) == 1

    def test_trigram_no_match(self, db: Database) -> None:
        self._setup_data(db)
        results = db.fts_search("存在しないキーワード")
        assert len(results) == 0

    def test_multiple_videos(self, db: Database) -> None:
        db.save_channel("UC1", "TestCh", "https://youtube.com/c/test")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid1", [SubtitleEntry(start_ms=0, duration_ms=5000, text="共通のキーワードテスト")])
        db.save_subtitle_lines("vid2", [SubtitleEntry(start_ms=0, duration_ms=5000, text="共通のキーワードテスト")])
        results = db.fts_search("キーワード")
        assert len(results) == 2


class TestVectorSearchIntegration:
    """sqlite-vecベクトル検索統合テスト"""

    def test_knn_distance_order(self, db: Database) -> None:
        db.save_channel("UC1", "TestCh", "https://youtube.com/c/test")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)

        # 3つのセグメントを異なるベクトルで登録
        segments = [
            {"start_ms": 0, "end_ms": 60000, "summary": "話題A"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "話題B"},
            {"start_ms": 120000, "end_ms": 180000, "summary": "話題C"},
        ]
        vec_a = [0.1] * 1536
        vec_b = [0.5] * 1536
        vec_c = [0.9] * 1536
        db.save_segments_with_vectors("vid1", segments, [vec_a, vec_b, vec_c])

        # vec_cに最も近いクエリ
        results = db.vector_search([0.85] * 1536, limit=3)
        assert len(results) == 3
        # 最も近い結果が先頭
        assert results[0]["summary"] == "話題C"

    def test_limit_respected(self, db: Database) -> None:
        db.save_channel("UC1", "TestCh", "https://youtube.com/c/test")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments = [
            {"start_ms": i * 60000, "end_ms": (i + 1) * 60000, "summary": f"話題{i}"}
            for i in range(10)
        ]
        vectors = [[0.1 * i] * 1536 for i in range(10)]
        db.save_segments_with_vectors("vid1", segments, vectors)
        results = db.vector_search([0.5] * 1536, limit=3)
        assert len(results) == 3


class TestMigration:
    """スキーマバージョン管理テスト"""

    def test_double_initialize(self, db: Database) -> None:
        """2回初期化しても問題ない"""
        db.initialize()
        row = db._execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == 1

    def test_idempotent_schema(self, tmp_path) -> None:
        """ファイルDBでの再初期化が冪等であること"""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.save_channel("UC1", "TestCh", "https://youtube.com/c/test")
        db.close()

        # 再初期化
        db2 = Database(db_path=db_path, embedding_dimensions=1536)
        db2.initialize()
        ch = db2.get_channel("UC1")
        assert ch is not None
        assert ch.name == "TestCh"
        db2.close()
