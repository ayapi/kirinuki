"""データベース層のテスト"""

import time
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
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        segments_data = [
            {"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"},
        ]
        vectors = [[0.1] * 1536]
        db.save_segments_with_vectors("vid1", segments_data, vectors)
        seg_id = db.list_segments("vid1")[0].id

        # segment_recommendationsテーブルを手動作成し子行を挿入
        db._conn.execute(
            """CREATE TABLE IF NOT EXISTS segment_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL REFERENCES segments(id),
                recommendation TEXT NOT NULL
            )"""
        )
        db._conn.execute(
            "INSERT INTO segment_recommendations (segment_id, recommendation) VALUES (?, ?)",
            (seg_id, "おすすめ動画"),
        )
        db._conn.commit()

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

    def test_includes_subtitle_only_segment_only_and_both(self, db: Database) -> None:
        """字幕のみ・セグメントのみ・両方ある動画が全て含まれる"""
        db.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        db.save_video("vid_sub", "UC1", "Subtitle Only", datetime(2024, 3, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_seg", "UC1", "Segment Only", datetime(2024, 2, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_both", "UC1", "Both", datetime(2024, 1, 1, tzinfo=timezone.utc), 3600, "ja", False)
        db.save_video("vid_none", "UC1", "Neither", datetime(2024, 4, 1, tzinfo=timezone.utc), 3600, "ja", False)
        # 字幕のみ
        db.save_subtitle_lines("vid_sub", [SubtitleEntry(start_ms=0, duration_ms=5000, text="sub")])
        # セグメントのみ
        db.save_segments("vid_seg", [{"start_ms": 0, "end_ms": 60000, "summary": "seg"}])
        # 両方
        db.save_subtitle_lines("vid_both", [SubtitleEntry(start_ms=0, duration_ms=5000, text="both")])
        db.save_segments("vid_both", [{"start_ms": 0, "end_ms": 60000, "summary": "both"}])
        result = db.get_resegment_target_video_ids()
        assert set(result) == {"vid_sub", "vid_seg", "vid_both"}
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
