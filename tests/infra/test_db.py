"""Database の suggest 関連メソッドのテスト"""

from datetime import datetime, timezone

import pytest

from kirinuki.infra.database import Database
from kirinuki.models.recommendation import SegmentRecommendation


@pytest.fixture
def db(tmp_path):
    """インメモリDBでテスト"""
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    return database


def _setup_db_with_videos(db: Database) -> Database:
    """テスト用DBにチャンネルと動画を追加する"""
    db.save_channel("UC123", "テストチャンネル", "https://youtube.com/c/test")
    for i in range(3):
        db.save_video(
            video_id=f"vid{i:03d}",
            channel_id="UC123",
            title=f"テスト動画 {i}",
            published_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            duration_seconds=3600,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )
    return db


class TestGetVideosByIds:
    def test_returns_existing_videos(self, db: Database) -> None:
        _setup_db_with_videos(db)
        result = db.get_videos_by_ids(["vid000", "vid001"])
        assert len(result) == 2
        ids = {r["video_id"] for r in result}
        assert ids == {"vid000", "vid001"}

    def test_excludes_missing_ids(self, db: Database) -> None:
        _setup_db_with_videos(db)
        result = db.get_videos_by_ids(["vid000", "MISSING"])
        assert len(result) == 1
        assert result[0]["video_id"] == "vid000"

    def test_all_missing_returns_empty(self, db: Database) -> None:
        _setup_db_with_videos(db)
        result = db.get_videos_by_ids(["MISSING1", "MISSING2"])
        assert result == []

    def test_return_dict_keys_match_get_latest_videos(self, db: Database) -> None:
        _setup_db_with_videos(db)
        by_ids = db.get_videos_by_ids(["vid000"])
        latest = db.get_latest_videos("UC123", 1)
        assert set(by_ids[0].keys()) == set(latest[0].keys())


class TestGetLatestVideos:
    def test_returns_latest_n_videos(self, db: Database) -> None:
        _setup_db_with_videos(db)
        result = db.get_latest_videos("UC123", 2)
        assert len(result) == 2
        # 降順確認
        assert result[0]["video_id"] == "vid002"
        assert result[1]["video_id"] == "vid001"

    def test_returns_empty_for_unknown_channel(self, db: Database) -> None:
        result = db.get_latest_videos("UNKNOWN", 5)
        assert result == []


class TestChannelExists:
    def test_existing_channel(self, db: Database) -> None:
        db.save_channel("UC123", "テスト", "https://youtube.com/c/test")
        assert db.channel_exists("UC123") is True

    def test_nonexistent_channel(self, db: Database) -> None:
        assert db.channel_exists("UNKNOWN") is False


class TestGetSegmentsForVideo:
    def test_returns_segments_as_dicts(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segments("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "話題1"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "話題2"},
        ])
        result = db.get_segments_for_video("vid1")
        assert len(result) == 2
        assert result[0]["summary"] == "話題1"
        assert "id" in result[0]
        assert "video_id" in result[0]

    def test_returns_empty_for_no_segments(self, db: Database) -> None:
        result = db.get_segments_for_video("nonexistent")
        assert result == []


class TestRecommendations:
    def test_save_and_get_cached(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        seg_ids = db.save_segments("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "話題1"},
        ])
        rec = SegmentRecommendation(
            segment_id=seg_ids[0],
            video_id="vid1",
            start_time=0.0,
            end_time=60.0,
            score=8,
            summary="要約",
            appeal="魅力",
            prompt_version="v1",
        )
        db.save_recommendations([rec])

        cached = db.get_cached_recommendations("vid1", "v1")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].score == 8
        assert cached[0].summary == "要約"

    def test_returns_none_when_no_cache(self, db: Database) -> None:
        result = db.get_cached_recommendations("vid1", "v1")
        assert result is None

    def test_upsert_updates_existing(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        seg_ids = db.save_segments("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "話題1"},
        ])
        rec1 = SegmentRecommendation(
            segment_id=seg_ids[0], video_id="vid1",
            start_time=0.0, end_time=60.0,
            score=5, summary="旧要約", appeal="旧魅力", prompt_version="v1",
        )
        db.save_recommendations([rec1])

        rec2 = SegmentRecommendation(
            segment_id=seg_ids[0], video_id="vid1",
            start_time=0.0, end_time=60.0,
            score=9, summary="新要約", appeal="新魅力", prompt_version="v1",
        )
        db.save_recommendations([rec2])

        cached = db.get_cached_recommendations("vid1", "v1")
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].score == 9
        assert cached[0].summary == "新要約"


class TestSegmentRecommendationsSchema:
    def test_creates_segment_recommendations_table(self, db: Database) -> None:
        tables = db._execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='segment_recommendations'"
        ).fetchall()
        assert len(tables) == 1

    def test_segment_recommendations_columns(self, db: Database) -> None:
        cursor = db._execute("PRAGMA table_info(segment_recommendations)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        assert "id" in columns
        assert "segment_id" in columns
        assert "video_id" in columns
        assert "score" in columns
        assert "summary" in columns
        assert "appeal" in columns
        assert "prompt_version" in columns
        assert "created_at" in columns

    def test_unique_index_on_segment_prompt(self, db: Database) -> None:
        cursor = db._execute("PRAGMA index_list(segment_recommendations)")
        indexes = cursor.fetchall()
        index_names = [idx[1] for idx in indexes]
        assert "idx_recommendations_segment_prompt" in index_names

    def test_index_on_video_id(self, db: Database) -> None:
        cursor = db._execute("PRAGMA index_list(segment_recommendations)")
        indexes = cursor.fetchall()
        index_names = [idx[1] for idx in indexes]
        assert "idx_recommendations_video_id" in index_names
