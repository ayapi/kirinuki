"""データベース層のテスト"""

import sqlite3
import time
from datetime import datetime, timezone

import pytest

from kirinuki.infra.database import Database, SCHEMA_VERSION
from kirinuki.models.domain import SubtitleEntry
from kirinuki.models.recommendation import SegmentRecommendation


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
        assert row[0] == 2

    def test_videos_table_has_broadcast_start_at(self, db: Database) -> None:
        columns = db._execute("PRAGMA table_info(videos)").fetchall()
        column_names = {row[1] for row in columns}
        assert "broadcast_start_at" in column_names

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

class TestUnavailableVideosCRUD:
    def test_save_and_get_unavailable(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_unavailable_video("vid1", "UC1", "auth_required", "Join this channel")
        db.save_unavailable_video("vid2", "UC1", "unavailable", "Video removed")
        ids = db.get_unavailable_video_ids("UC1")
        assert ids == {"vid1", "vid2"}

    def test_get_unavailable_empty(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        ids = db.get_unavailable_video_ids("UC1")
        assert ids == set()

    def test_upsert_unavailable(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_unavailable_video("vid1", "UC1", "auth_required", "reason1")
        db.save_unavailable_video("vid1", "UC1", "unavailable", "reason2")
        ids = db.get_unavailable_video_ids("UC1")
        assert ids == {"vid1"}

    def test_get_auth_unavailable_recorded_at(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        assert db.get_auth_unavailable_recorded_at("UC1") is None
        db.save_unavailable_video("vid1", "UC1", "auth_required", "reason")
        recorded = db.get_auth_unavailable_recorded_at("UC1")
        assert recorded is not None

    def test_clear_unavailable_by_type(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_unavailable_video("vid1", "UC1", "auth_required", "reason")
        db.save_unavailable_video("vid2", "UC1", "unavailable", "reason")
        cleared = db.clear_unavailable_by_type("UC1", "auth_required")
        assert cleared == 1
        ids = db.get_unavailable_video_ids("UC1")
        assert ids == {"vid2"}

    def test_clear_all_unavailable_channel(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        db.save_unavailable_video("vid1", "UC1", "auth_required", "reason")
        db.save_unavailable_video("vid2", "UC2", "unavailable", "reason")
        cleared = db.clear_all_unavailable("UC1")
        assert cleared == 1
        assert db.get_unavailable_video_ids("UC1") == set()
        assert db.get_unavailable_video_ids("UC2") == {"vid2"}

    def test_clear_all_unavailable_global(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        db.save_unavailable_video("vid1", "UC1", "auth_required", "reason")
        db.save_unavailable_video("vid2", "UC2", "unavailable", "reason")
        cleared = db.clear_all_unavailable()
        assert cleared == 2

    def test_unavailable_table_exists(self, db: Database) -> None:
        tables = db._execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}
        assert "unavailable_videos" in table_names


class TestDeleteSegments:
    def test_deletes_segments_and_vectors(self, db: Database) -> None:
        """セグメントとベクトルを両方削除する"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "ゲーム開始"},
        ]
        vectors = [[0.1] * 1536, [0.2] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)

        deleted = db.delete_segments("vid1")
        assert deleted == 2
        assert db.list_segments("vid1") == []

    def test_returns_zero_for_no_segments(self, db: Database) -> None:
        """セグメントがない動画では0を返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        deleted = db.delete_segments("vid1")
        assert deleted == 0

    def test_deletes_segment_versions(self, db: Database) -> None:
        """セグメント削除時にsegment_versionsも一緒に削除される"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [{"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"}]
        vectors = [[0.1] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)
        db.save_segment_version("vid1", "v1")

        # 削除前: バージョン記録が存在する
        assert db.get_video_ids_with_segment_version("v1") == {"vid1"}

        db.delete_segments("vid1")

        # 削除後: バージョン記録も消えている
        assert db.get_video_ids_with_segment_version("v1") == set()

    def test_deletes_segments_with_recommendations(self, db: Database) -> None:
        """segment_recommendationsがある場合でもFK違反せず削除できる"""
        from kirinuki.models.recommendation import SegmentRecommendation

        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"},
        ]
        vectors = [[0.1] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)
        seg_id = db.list_segments("vid1")[0].id

        db.save_recommendations([
            SegmentRecommendation(
                segment_id=seg_id,
                video_id="vid1",
                start_time=0.0,
                end_time=60.0,
                score=8,
                summary="おすすめ動画",
                appeal="面白い",
                prompt_version="v1",
            )
        ])

        # FK制約違反なく削除できることを検証
        deleted = db.delete_segments("vid1")
        assert deleted == 1
        assert db.list_segments("vid1") == []
        # 子行も削除されている
        row = db._conn.execute("SELECT COUNT(*) FROM segment_recommendations").fetchone()
        assert row[0] == 0

    def test_does_not_affect_other_videos(self, db: Database) -> None:
        """他の動画のセグメントには影響しない"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_segments_with_vectors(
            "vid1",
            [{"start_ms": 0, "end_ms": 60000, "summary": "topic1"}],
            [[0.1] * 1536],
        )
        db.save_segments_with_vectors(
            "vid2",
            [{"start_ms": 0, "end_ms": 60000, "summary": "topic2"}],
            [[0.2] * 1536],
        )

        db.delete_segments("vid1")
        assert db.list_segments("vid1") == []
        assert len(db.list_segments("vid2")) == 1


class TestGetSegmentedVideoIds:
    def test_returns_segmented_video_ids(self, db: Database) -> None:
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_video("vid3", "UC1", "Video 3", None, 5400, "ja", False)
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "t1"}])
        db.save_segments("vid3", [{"start_ms": 0, "end_ms": 60000, "summary": "t3"}])

        result = db.get_segmented_video_ids()
        assert set(result) == {"vid1", "vid3"}

    def test_returns_empty_when_no_segments(self, db: Database) -> None:
        result = db.get_segmented_video_ids()
        assert result == []


class TestGetUnsegmentedVideoIds:
    def test_returns_unsegmented_videos_only(self, db: Database) -> None:
        """セグメント済みと未済が混在する場合、未済のみ返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_video("vid3", "UC1", "Video 3", None, 5400, "ja", False)
        # vid1のみセグメント済み
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "topic"}])
        result = db.get_unsegmented_video_ids("UC1")
        assert set(result) == {"vid2", "vid3"}

    def test_returns_empty_when_all_segmented(self, db: Database) -> None:
        """全動画がセグメント済みなら空リスト"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "topic"}])
        result = db.get_unsegmented_video_ids("UC1")
        assert result == []

    def test_returns_empty_for_channel_with_no_videos(self, db: Database) -> None:
        """動画がないチャンネルでは空リスト"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        result = db.get_unsegmented_video_ids("UC1")
        assert result == []

    def test_filters_by_channel_id(self, db: Database) -> None:
        """他チャンネルの動画は含まない"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC2", "Video 2", None, 7200, "ja", False)
        result = db.get_unsegmented_video_ids("UC1")
        assert result == ["vid1"]


class TestGetUnsegmentedVideoIdsAll:
    def test_returns_videos_with_subtitles_but_no_segments(self, db: Database) -> None:
        """字幕ありセグメントなしの動画を返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        # vid1: 字幕あり＋セグメントあり
        db.save_subtitle_lines("vid1", [SubtitleEntry(start_ms=0, duration_ms=5000, text="hello")])
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "topic"}])
        # vid2: 字幕あり＋セグメントなし
        db.save_subtitle_lines("vid2", [SubtitleEntry(start_ms=0, duration_ms=5000, text="world")])
        result = db.get_unsegmented_video_ids_all()
        assert result == ["vid2"]

    def test_excludes_videos_without_subtitles(self, db: Database) -> None:
        """字幕もセグメントもない動画は含まない"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        result = db.get_unsegmented_video_ids_all()
        assert result == []

    def test_returns_empty_when_all_segmented(self, db: Database) -> None:
        """全動画がセグメント済みなら空リスト"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_subtitle_lines("vid1", [SubtitleEntry(start_ms=0, duration_ms=5000, text="hello")])
        db.save_segments("vid1", [{"start_ms": 0, "end_ms": 60000, "summary": "topic"}])
        result = db.get_unsegmented_video_ids_all()
        assert result == []

    def test_spans_multiple_channels(self, db: Database) -> None:
        """複数チャンネルを横断して取得する"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC2", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid1", [SubtitleEntry(start_ms=0, duration_ms=5000, text="hello")])
        db.save_subtitle_lines("vid2", [SubtitleEntry(start_ms=0, duration_ms=5000, text="world")])
        result = db.get_unsegmented_video_ids_all()
        assert set(result) == {"vid1", "vid2"}


class TestGetResegmentTargetVideoIds:
    def test_returns_videos_ordered_by_published_at_desc(self, db: Database) -> None:
        """公開日の新しい順で返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid_old", "UC1", "Old Video", datetime(2024, 1, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_new", "UC1", "New Video", datetime(2024, 6, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_mid", "UC1", "Mid Video", datetime(2024, 3, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_subtitle_lines("vid_old", [SubtitleEntry(start_ms=0, duration_ms=5000, text="old")])
        db.save_subtitle_lines("vid_new", [SubtitleEntry(start_ms=0, duration_ms=5000, text="new")])
        db.save_subtitle_lines("vid_mid", [SubtitleEntry(start_ms=0, duration_ms=5000, text="mid")])
        result = db.get_resegment_target_video_ids()
        assert result == ["vid_new", "vid_mid", "vid_old"]

    def test_includes_subtitle_only_and_both_excludes_segment_only(self, db: Database) -> None:
        """字幕のみ・両方ある動画は含まれるが、セグメントのみの動画は除外される"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid_sub", "UC1", "Subtitle Only", datetime(2024, 3, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_seg", "UC1", "Segment Only", datetime(2024, 2, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_both", "UC1", "Both", datetime(2024, 1, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_none", "UC1", "Neither", datetime(2024, 4, 1, tzinfo=timezone.utc), 3600, "ja", False)
        # 字幕のみ
        db.save_subtitle_lines("vid_sub", [SubtitleEntry(start_ms=0, duration_ms=5000, text="sub")])
        # セグメントのみ（字幕なしなのでresegment不可）
        db.save_segments("vid_seg", [{"start_ms": 0, "end_ms": 60000, "summary": "seg"}])
        # 両方
        db.save_subtitle_lines("vid_both", [SubtitleEntry(start_ms=0, duration_ms=5000, text="both")])
        db.save_segments("vid_both", [{"start_ms": 0, "end_ms": 60000, "summary": "both"}])
        result = db.get_resegment_target_video_ids()
        assert set(result) == {"vid_sub", "vid_both"}
        assert "vid_seg" not in result
        assert "vid_none" not in result

    def test_null_published_at_comes_last(self, db: Database) -> None:
        """published_atがNULLの動画は末尾に来る"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid_null", "UC1", "No Date", None, 3600, "ja", False)
        db.save_video("vid_dated", "UC1", "Has Date", datetime(2024, 1, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_subtitle_lines("vid_null", [SubtitleEntry(start_ms=0, duration_ms=5000, text="null")])
        db.save_subtitle_lines("vid_dated", [SubtitleEntry(start_ms=0, duration_ms=5000, text="dated")])
        result = db.get_resegment_target_video_ids()
        assert result == ["vid_dated", "vid_null"]

    def test_returns_empty_when_no_targets(self, db: Database) -> None:
        """対象動画がなければ空リスト"""
        result = db.get_resegment_target_video_ids()
        assert result == []


class TestGetSubtitleEntries:
    def test_returns_entries_ordered_by_start_ms(self, db: Database) -> None:
        """字幕エントリーを開始時刻順で返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        entries = [
            SubtitleEntry(start_ms=5000, duration_ms=3000, text="2番目"),
            SubtitleEntry(start_ms=0, duration_ms=5000, text="1番目"),
            SubtitleEntry(start_ms=10000, duration_ms=4000, text="3番目"),
        ]
        db.save_subtitle_lines("vid1", entries)
        result = db.get_subtitle_entries("vid1")
        assert len(result) == 3
        assert result[0].text == "1番目"
        assert result[1].text == "2番目"
        assert result[2].text == "3番目"
        assert result[0].start_ms == 0
        assert result[0].duration_ms == 5000

    def test_returns_empty_for_no_subtitles(self, db: Database) -> None:
        """字幕がない動画では空リスト"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        result = db.get_subtitle_entries("vid1")
        assert result == []

    def test_returns_empty_for_nonexistent_video(self, db: Database) -> None:
        """存在しない動画IDでは空リスト"""
        result = db.get_subtitle_entries("nonexistent")
        assert result == []


class TestFtsSearchSegmentsSnippet:
    def test_fts_search_segments_returns_snippet(self, db: Database) -> None:
        """FTS検索結果にスニペット（マッチした字幕テキスト）が含まれる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        entries = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="こんにちは皆さん今日もよろしく"),
            SubtitleEntry(start_ms=30000, duration_ms=5000, text="今日はマインクラフトを遊びます"),
            SubtitleEntry(start_ms=60000, duration_ms=5000, text="ダイヤモンドを見つけました"),
        ]
        db.save_subtitle_lines("vid1", entries)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "挨拶とゲーム紹介"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "マインクラフト実況"},
        ]
        vectors = [[0.1] * 1536, [0.9] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)

        results = db.fts_search_segments("マインクラフト")
        assert len(results) > 0
        assert "snippet" in results[0]
        assert "マインクラフト" in results[0]["snippet"]

    def test_fts_search_segments_multiple_matches_concatenated(self, db: Database) -> None:
        """同一セグメント内の複数マッチ行が連結される"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        entries = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="今日はマインクラフトを遊びます"),
            SubtitleEntry(start_ms=10000, duration_ms=5000, text="マインクラフトの世界へようこそ"),
        ]
        db.save_subtitle_lines("vid1", entries)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "ゲーム紹介"},
        ]
        vectors = [[0.1] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)

        results = db.fts_search_segments("マインクラフト")
        assert len(results) == 1
        snippet = results[0]["snippet"]
        assert "…" in snippet  # 区切り文字で連結されている


class TestFtsSearchSegmentsVideoIdFilter:
    @pytest.fixture
    def db_with_multi_videos(self, db: Database):
        """複数動画のテストデータ"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="マインクラフトで遊びます"),
        ])
        db.save_subtitle_lines("vid2", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="マインクラフトの世界へ"),
        ])
        db.save_segments_with_vectors("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "ゲーム紹介1"},
        ], [[0.1] * 1536])
        db.save_segments_with_vectors("vid2", [
            {"start_ms": 0, "end_ms": 60000, "summary": "ゲーム紹介2"},
        ], [[0.2] * 1536])
        return db

    def test_filter_by_single_video_id(self, db_with_multi_videos: Database) -> None:
        results = db_with_multi_videos.fts_search_segments("マインクラフト", video_ids=["vid1"])
        assert len(results) == 1
        assert results[0]["video_id"] == "vid1"

    def test_filter_by_multiple_video_ids(self, db_with_multi_videos: Database) -> None:
        results = db_with_multi_videos.fts_search_segments("マインクラフト", video_ids=["vid1", "vid2"])
        assert len(results) == 2
        video_ids = {r["video_id"] for r in results}
        assert video_ids == {"vid1", "vid2"}

    def test_no_filter_returns_all(self, db_with_multi_videos: Database) -> None:
        results = db_with_multi_videos.fts_search_segments("マインクラフト")
        assert len(results) == 2

    def test_filter_with_none_returns_all(self, db_with_multi_videos: Database) -> None:
        results = db_with_multi_videos.fts_search_segments("マインクラフト", video_ids=None)
        assert len(results) == 2


class TestLikeSearchSegments:
    """like_search_segments（FTS trigram 3文字未満クエリ用LIKEフォールバック）のテスト"""

    @pytest.fixture
    def db_with_data(self, db: Database):
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="今日は演出の話をします"),
            SubtitleEntry(start_ms=10000, duration_ms=5000, text="演出が変わりました"),
            SubtitleEntry(start_ms=60000, duration_ms=5000, text="別の話題です"),
        ])
        db.save_subtitle_lines("vid2", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="この演出はすごい"),
        ])
        db.save_segments_with_vectors("vid1", [
            {"start_ms": 0, "end_ms": 30000, "summary": "演出について"},
            {"start_ms": 60000, "end_ms": 120000, "summary": "別の話題"},
        ], [[0.1] * 1536, [0.2] * 1536])
        db.save_segments_with_vectors("vid2", [
            {"start_ms": 0, "end_ms": 60000, "summary": "演出紹介"},
        ], [[0.3] * 1536])
        return db

    def test_two_char_query_matches(self, db_with_data: Database) -> None:
        """2文字クエリでLIKE検索がヒットする"""
        results = db_with_data.like_search_segments("演出")
        assert len(results) >= 1
        for r in results:
            assert "演出" in r["snippet"]

    def test_returns_same_dict_format_as_fts(self, db_with_data: Database) -> None:
        """返却dictのキーがfts_search_segmentsと同一"""
        results = db_with_data.like_search_segments("演出")
        expected_keys = {"segment_id", "video_id", "start_ms", "end_ms", "summary",
                         "video_title", "channel_name", "snippet"}
        for r in results:
            assert set(r.keys()) == expected_keys

    def test_multiple_matches_concatenated(self, db_with_data: Database) -> None:
        """同一セグメント内の複数マッチ行が連結される"""
        results = db_with_data.like_search_segments("演出")
        vid1_results = [r for r in results if r["video_id"] == "vid1"]
        assert len(vid1_results) >= 1
        snippet = vid1_results[0]["snippet"]
        assert "…" in snippet

    def test_video_id_filter(self, db_with_data: Database) -> None:
        """video_idsフィルタで絞り込める"""
        results = db_with_data.like_search_segments("演出", video_ids=["vid1"])
        assert all(r["video_id"] == "vid1" for r in results)

    def test_no_match(self, db_with_data: Database) -> None:
        """マッチしないクエリは空リスト"""
        results = db_with_data.like_search_segments("xyz存在しない")
        assert results == []

    def test_wildcard_characters_escaped(self, db_with_data: Database) -> None:
        """クエリ内の%や_がワイルドカードとして解釈されない"""
        results = db_with_data.like_search_segments("%")
        assert results == []
        results = db_with_data.like_search_segments("_")
        assert results == []

    def test_one_char_query(self, db_with_data: Database) -> None:
        """1文字クエリでもマッチする"""
        results = db_with_data.like_search_segments("演")
        assert len(results) >= 1


class TestSegmentVersionsCRUD:
    def test_save_and_get_segment_version(self, db: Database) -> None:
        """バージョンを記録して取得できる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segment_version("vid1", "v1")
        result = db.get_video_ids_with_segment_version("v1")
        assert result == {"vid1"}

    def test_get_version_returns_empty_for_different_version(self, db: Database) -> None:
        """異なるバージョンでは空セットを返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segment_version("vid1", "v1")
        result = db.get_video_ids_with_segment_version("v2")
        assert result == set()

    def test_upsert_updates_version(self, db: Database) -> None:
        """同じvideo_idで再度保存するとバージョンが更新される"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segment_version("vid1", "v1")
        db.save_segment_version("vid1", "v2")
        assert db.get_video_ids_with_segment_version("v1") == set()
        assert db.get_video_ids_with_segment_version("v2") == {"vid1"}

    def test_delete_segment_version(self, db: Database) -> None:
        """バージョン記録を削除できる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_segment_version("vid1", "v1")
        db.delete_segment_version("vid1")
        assert db.get_video_ids_with_segment_version("v1") == set()

    def test_multiple_videos_different_versions(self, db: Database) -> None:
        """複数動画が異なるバージョンを持てる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_segment_version("vid1", "v1")
        db.save_segment_version("vid2", "v2")
        assert db.get_video_ids_with_segment_version("v1") == {"vid1"}
        assert db.get_video_ids_with_segment_version("v2") == {"vid2"}

    def test_segment_versions_table_exists(self, db: Database) -> None:
        """segment_versionsテーブルが作成される"""
        tables = db._execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row[0] for row in tables}
        assert "segment_versions" in table_names


class TestValidateVideoIds:
    def test_all_exist(self, db: Database) -> None:
        """全IDが存在する場合"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        existing, missing = db.validate_video_ids(["vid1", "vid2"])
        assert set(existing) == {"vid1", "vid2"}
        assert missing == []

    def test_some_missing(self, db: Database) -> None:
        """一部が存在しない場合"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        existing, missing = db.validate_video_ids(["vid1", "vid_unknown"])
        assert existing == ["vid1"]
        assert missing == ["vid_unknown"]

    def test_all_missing(self, db: Database) -> None:
        """全IDが存在しない場合"""
        existing, missing = db.validate_video_ids(["vid_x", "vid_y"])
        assert existing == []
        assert set(missing) == {"vid_x", "vid_y"}

    def test_empty_list(self, db: Database) -> None:
        """空リストの場合"""
        existing, missing = db.validate_video_ids([])
        assert existing == []
        assert missing == []


class TestVectorSearch:
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


class TestVectorSearchVideoIdFilter:
    @pytest.fixture
    def db_multi(self, db: Database):
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        db.save_video("vid2", "UC1", "Video 2", None, 7200, "ja", False)
        db.save_segments_with_vectors("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "topic1"},
        ], [[0.1] * 1536])
        db.save_segments_with_vectors("vid2", [
            {"start_ms": 0, "end_ms": 60000, "summary": "topic2"},
        ], [[0.9] * 1536])
        return db

    def test_filter_by_single_video_id(self, db_multi: Database) -> None:
        results = db_multi.vector_search([0.5] * 1536, limit=10, video_ids=["vid1"])
        assert len(results) >= 1
        for r in results:
            assert r["video_id"] == "vid1"

    def test_filter_by_multiple_video_ids(self, db_multi: Database) -> None:
        results = db_multi.vector_search([0.5] * 1536, limit=10, video_ids=["vid1", "vid2"])
        assert len(results) == 2

    def test_no_filter_returns_all(self, db_multi: Database) -> None:
        results = db_multi.vector_search([0.5] * 1536, limit=10)
        assert len(results) == 2

    def test_filter_with_none_returns_all(self, db_multi: Database) -> None:
        results = db_multi.vector_search([0.5] * 1536, limit=10, video_ids=None)
        assert len(results) == 2


# --- test_db.py から統合されたテスト ---


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

    def test_returns_broadcast_start_at_key(self, db: Database) -> None:
        """返却dictにbroadcast_start_atキーが含まれる"""
        _setup_db_with_videos(db)
        result = db.get_videos_by_ids(["vid000"])
        assert "broadcast_start_at" in result[0]

    def test_orders_by_broadcast_start_at_coalesce(self, db: Database) -> None:
        """COALESCE(broadcast_start_at, published_at)降順でソートされる"""
        db.save_channel("UCX", "ChX", "https://youtube.com/c/chx")
        db.save_video(
            "va", "UCX", "Video A",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 3, 1, 20, 0, tzinfo=timezone.utc),
        )
        db.save_video(
            "vb", "UCX", "Video B",
            published_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
        )
        result = db.get_videos_by_ids(["va", "vb"])
        # va: COALESCE(2024-03-01T20:00, ...) > vb: COALESCE(NULL, 2024-02-01)
        assert result[0]["video_id"] == "va"
        assert result[1]["video_id"] == "vb"


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


class TestMigrationV1ToV2:
    def test_migrate_v1_to_v2(self, tmp_path) -> None:
        """v1 DBがv2にマイグレーションされる"""
        db_path = tmp_path / "test.db"
        # v1スキーマのDBを手動作成
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                url TEXT NOT NULL, last_synced_at TEXT
            );
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL REFERENCES channels(channel_id),
                title TEXT NOT NULL, published_at TEXT,
                duration_seconds INTEGER NOT NULL,
                subtitle_language TEXT NOT NULL,
                is_auto_subtitle INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
        """)
        conn.execute("INSERT INTO schema_version (version) VALUES (1)")
        conn.execute(
            "INSERT INTO channels VALUES ('UC1', 'Ch1', 'https://youtube.com/c/ch1', NULL)"
        )
        conn.execute(
            "INSERT INTO videos VALUES ('vid1', 'UC1', 'Video 1', '2024-01-01', 3600, 'ja', 0, '2024-01-01')"
        )
        conn.commit()
        conn.close()

        # Database.initialize()でマイグレーション実行
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()

        # バージョンが2に更新されている
        row = db._execute("SELECT version FROM schema_version").fetchone()
        assert row[0] == 2

        # broadcast_start_atカラムが存在する
        columns = db._execute("PRAGMA table_info(videos)").fetchall()
        column_names = {r[1] for r in columns}
        assert "broadcast_start_at" in column_names

        # 既存データのbroadcast_start_atはNULL
        row = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid1'").fetchone()
        assert row[0] is None
        db.close()


class TestSaveVideoBroadcastStartAt:
    def test_save_with_broadcast_start_at(self, db: Database) -> None:
        """broadcast_start_atが保存される"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        bsa = datetime(2024, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
        db.save_video(
            video_id="vid1", channel_id="UC1", title="Video 1",
            published_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=bsa,
        )
        row = db._execute(
            "SELECT broadcast_start_at FROM videos WHERE video_id='vid1'"
        ).fetchone()
        assert row[0] == bsa.isoformat()

    def test_save_without_broadcast_start_at(self, db: Database) -> None:
        """broadcast_start_at省略時はNULL"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        row = db._execute(
            "SELECT broadcast_start_at FROM videos WHERE video_id='vid1'"
        ).fetchone()
        assert row[0] is None


class TestGetLatestVideosUntil:
    @pytest.fixture
    def db_with_broadcast(self, db: Database):
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        # 3つの動画: broadcast_start_at付き2つ、NULL1つ
        db.save_video(
            "vid1", "UC1", "Video 1",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc),
        )
        db.save_video(
            "vid2", "UC1", "Video 2",
            published_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 2, 1, 20, 0, tzinfo=timezone.utc),
        )
        db.save_video(
            "vid3", "UC1", "Video 3",
            published_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
        )  # broadcast_start_at=NULL
        return db

    def test_until_filters_by_broadcast_start_at(self, db_with_broadcast: Database) -> None:
        """until指定でbroadcast_start_at以前の動画のみ返す"""
        until = datetime(2024, 1, 31, 23, 59, 59, tzinfo=timezone.utc)
        result = db_with_broadcast.get_latest_videos("UC1", 10, until=until)
        ids = [r["video_id"] for r in result]
        assert "vid1" in ids
        assert "vid2" not in ids

    def test_until_includes_null_broadcast_with_published_at(self, db_with_broadcast: Database) -> None:
        """broadcast_start_at=NULLの動画はpublished_atでフィルタされる"""
        until = datetime(2024, 3, 15, tzinfo=timezone.utc)
        result = db_with_broadcast.get_latest_videos("UC1", 10, until=until)
        ids = [r["video_id"] for r in result]
        assert "vid3" in ids  # NULL broadcast but published_at <= until

    def test_without_until_returns_all(self, db_with_broadcast: Database) -> None:
        """until未指定時は全動画を返す"""
        result = db_with_broadcast.get_latest_videos("UC1", 10)
        assert len(result) == 3

    def test_sort_order_uses_coalesce(self, db_with_broadcast: Database) -> None:
        """COALESCE(broadcast_start_at, published_at)降順でソートされる"""
        result = db_with_broadcast.get_latest_videos("UC1", 10)
        # vid3: COALESCE(NULL, 2024-03-01) = 2024-03-01
        # vid2: COALESCE(2024-02-01T20:00, ...) = 2024-02-01T20:00
        # vid1: COALESCE(2024-01-01T20:00, ...) = 2024-01-01T20:00
        ids = [r["video_id"] for r in result]
        assert ids == ["vid3", "vid2", "vid1"]

    def test_returns_broadcast_start_at_key(self, db_with_broadcast: Database) -> None:
        """返却dictにbroadcast_start_atキーが含まれる"""
        result = db_with_broadcast.get_latest_videos("UC1", 10)
        for r in result:
            assert "broadcast_start_at" in r

    def test_broadcast_start_at_uses_coalesce(self, db_with_broadcast: Database) -> None:
        """broadcast_start_at値はCOALESCE(broadcast_start_at, published_at)"""
        result = db_with_broadcast.get_latest_videos("UC1", 10)
        by_id = {r["video_id"]: r for r in result}
        # vid1: broadcast_start_at = 2024-01-01T20:00:00+00:00
        assert "2024-01-01T20:00:00" in by_id["vid1"]["broadcast_start_at"]
        # vid3: broadcast_start_at=NULL → published_at = 2024-03-01T00:00:00+00:00
        assert "2024-03-01" in by_id["vid3"]["broadcast_start_at"]


class TestBackfillMethods:
    def test_get_videos_without_broadcast_start(self, db: Database) -> None:
        """broadcast_start_atがNULLの動画のみ返す"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video(
            "vid1", "UC1", "Video 1", None, 3600, "ja", False,
            broadcast_start_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        db.save_video("vid2", "UC1", "Video 2", None, 3600, "ja", False)
        result = db.get_videos_without_broadcast_start()
        ids = [r["video_id"] for r in result]
        assert ids == ["vid2"]

    def test_get_videos_without_broadcast_start_empty(self, db: Database) -> None:
        """全動画にbroadcast_start_atが設定済みの場合は空リスト"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video(
            "vid1", "UC1", "Video 1", None, 3600, "ja", False,
            broadcast_start_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        result = db.get_videos_without_broadcast_start()
        assert result == []

    def test_update_broadcast_start_at(self, db: Database) -> None:
        """broadcast_start_atを更新できる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        bsa = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)
        db.update_broadcast_start_at("vid1", bsa)
        row = db._execute(
            "SELECT broadcast_start_at FROM videos WHERE video_id='vid1'"
        ).fetchone()
        assert row[0] == bsa.isoformat()


class TestGetAllVideos:
    @pytest.fixture
    def db_with_multi_channel(self, db: Database):
        """複数チャンネルに動画を登録したDB"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_channel("UC2", "Ch2", "https://youtube.com/c/ch2")
        db.save_video(
            "vid1", "UC1", "Video 1",
            published_at=datetime(2024, 1, 10, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 1, 10, 20, 0, tzinfo=timezone.utc),
        )
        db.save_video(
            "vid2", "UC2", "Video 2",
            published_at=datetime(2024, 2, 15, tzinfo=timezone.utc),
            duration_seconds=1800, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 2, 15, 20, 0, tzinfo=timezone.utc),
        )
        db.save_video(
            "vid3", "UC1", "Video 3",
            published_at=datetime(2024, 3, 20, tzinfo=timezone.utc),
            duration_seconds=7200, subtitle_language="ja", is_auto_subtitle=False,
        )  # broadcast_start_at=NULL → COALESCEでpublished_at使用
        return db

    def test_returns_all_videos_sorted_by_broadcast_desc(self, db_with_multi_channel: Database) -> None:
        """全チャンネルの動画がCOALESCE(broadcast_start_at, published_at)降順で返る"""
        result = db_with_multi_channel.get_all_videos(count=10)
        assert len(result) == 3
        assert result[0].video_id == "vid3"  # 2024-03-20
        assert result[1].video_id == "vid2"  # 2024-02-15T20:00
        assert result[2].video_id == "vid1"  # 2024-01-10T20:00

    def test_published_at_uses_coalesce(self, db_with_multi_channel: Database) -> None:
        """published_atにCOALESCE(broadcast_start_at, published_at)の値が返る"""
        result = db_with_multi_channel.get_all_videos(count=10)
        # vid2: broadcast_start_at=2024-02-15T20:00 が返る（published_atではなく）
        vid2 = [v for v in result if v.video_id == "vid2"][0]
        assert vid2.published_at == datetime(2024, 2, 15, 20, 0, tzinfo=timezone.utc)
        # vid3: broadcast_start_at=NULL → published_at=2024-03-20 が返る
        vid3 = [v for v in result if v.video_id == "vid3"][0]
        assert vid3.published_at == datetime(2024, 3, 20, 0, 0, tzinfo=timezone.utc)

    def test_count_limits_results(self, db_with_multi_channel: Database) -> None:
        """count指定で取得件数が制限される"""
        result = db_with_multi_channel.get_all_videos(count=2)
        assert len(result) == 2
        assert result[0].video_id == "vid3"
        assert result[1].video_id == "vid2"

    def test_empty_db_returns_empty_list(self, db: Database) -> None:
        """動画が0件の場合は空リストを返す"""
        result = db.get_all_videos(count=10)
        assert result == []

    def test_multi_channel_videos_mixed(self, db_with_multi_channel: Database) -> None:
        """複数チャンネルの動画が混在して返る"""
        result = db_with_multi_channel.get_all_videos(count=10)
        channel_ids = set()
        for v in result:
            # VideoSummaryにはchannel_idがないのでvideo_idで確認
            pass
        # vid1=UC1, vid2=UC2, vid3=UC1 が全て含まれる
        video_ids = [v.video_id for v in result]
        assert "vid1" in video_ids
        assert "vid2" in video_ids
        assert "vid3" in video_ids
