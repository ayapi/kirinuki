"""話題セグメンテーションサービスのテスト"""

from unittest.mock import MagicMock

import pytest

from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.infra.database import Database
from kirinuki.models.domain import SubtitleEntry, TopicSegment


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    database.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
    database.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
    return database


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.dimensions = 1536
    return mock


@pytest.fixture
def service(db, mock_llm, mock_embedding):
    return SegmentationService(db=db, llm_client=mock_llm, embedding_provider=mock_embedding)


class TestSegmentVideo:
    def test_segment_and_store(self, service, mock_llm, mock_embedding, db):
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="自己紹介"),
            TopicSegment(start_ms=60000, end_ms=120000, summary="ゲーム開始"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        segments = service.segment_video("vid1", "テスト字幕テキスト")
        assert len(segments) == 2
        assert segments[0].summary == "自己紹介"

        # DBに保存されていることを確認
        stored = db.list_segments("vid1")
        assert len(stored) == 2

    def test_empty_subtitle(self, service, mock_llm):
        mock_llm.analyze_topics.return_value = []
        segments = service.segment_video("vid1", "")
        assert segments == []


class TestChunking:
    def test_build_subtitle_text(self, service):
        entries = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="こんにちは"),
            SubtitleEntry(start_ms=60000, duration_ms=5000, text="テスト"),
            SubtitleEntry(start_ms=120000, duration_ms=5000, text="おわり"),
        ]
        text = service._build_subtitle_text(entries)
        assert "[00:00]" in text
        assert "[01:00]" in text
        assert "[02:00]" in text
        assert "こんにちは" in text

    def test_chunk_long_subtitle(self, service):
        # 5時間分の字幕を生成（45分チャンクで分割されるはず）
        entries = []
        for i in range(0, 5 * 60, 1):  # 5時間、1分ごとに字幕
            entries.append(
                SubtitleEntry(
                    start_ms=i * 60 * 1000,
                    duration_ms=5000,
                    text=f"テスト字幕 {i}分",
                )
            )
        chunks = service._chunk_entries(entries, chunk_minutes=45, overlap_minutes=5)
        assert len(chunks) > 1


class TestResplitOversized:
    def test_resplit_oversized_segment(self, service, mock_llm, mock_embedding, db):
        """max_segment_ms超のセグメントが再分割される"""
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題"),  # 10分
        ]
        mock_llm.analyze_topics_resplit.return_value = [
            TopicSegment(start_ms=0, end_ms=300000, summary="【長い話題】前半"),
            TopicSegment(start_ms=300000, end_ms=600000, summary="【長い話題】後半"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(10)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 600, max_segment_ms=300000
        )
        assert len(segments) == 2
        mock_llm.analyze_topics_resplit.assert_called_once()

    def test_keeps_segment_under_max(self, service, mock_llm, mock_embedding, db):
        """max_segment_ms以下のセグメントはそのまま保持"""
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="短い話題"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]

        entries = [SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")]
        segments = service.segment_video_from_entries(
            "vid1", entries, 60, max_segment_ms=300000
        )
        assert len(segments) == 1
        mock_llm.analyze_topics_resplit.assert_not_called()

    def test_keeps_original_when_resplit_fails(self, service, mock_llm, mock_embedding, db):
        """再分割が失敗した場合は元セグメントを保持"""
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題"),
        ]
        mock_llm.analyze_topics_resplit.side_effect = Exception("API error")
        mock_embedding.embed.return_value = [[0.1] * 1536]

        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(10)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 600, max_segment_ms=300000
        )
        assert len(segments) == 1
        assert segments[0].summary == "長い話題"

    def test_resplit_results_are_snapped(self, service, mock_llm, mock_embedding, db):
        """再分割結果がsnap_to_entriesで字幕エントリーにスナップされる"""
        # LLMのstart_msが字幕エントリーと微妙にずれているケース
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題"),
        ]
        mock_llm.analyze_topics_resplit.return_value = [
            TopicSegment(start_ms=2000, end_ms=305000, summary="【長い話題】前半"),
            TopicSegment(start_ms=305000, end_ms=598000, summary="【長い話題】後半"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(10)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 600, max_segment_ms=300000
        )
        assert len(segments) == 2
        # resplit結果がsnap後に字幕エントリーの境界に揃っていること
        stored = db.list_segments("vid1")
        assert stored[0].start_ms == 0  # 2000 → snapped to 0
        assert stored[1].start_ms == 300000  # 305000 → snapped to 300000

    def test_keeps_original_when_resplit_returns_single(self, service, mock_llm, mock_embedding, db):
        """再分割が1つしか返さない場合は元セグメントを保持"""
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題"),
        ]
        mock_llm.analyze_topics_resplit.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="同じ話題"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]

        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(10)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 600, max_segment_ms=300000
        )
        assert len(segments) == 1
        assert segments[0].summary == "長い話題"


class TestResegment:
    def test_resegment_video(self, service, mock_llm, mock_embedding, db):
        """既存セグメントを削除して再セグメンテーション"""
        # 既存セグメント
        db.save_segments_with_vectors(
            "vid1",
            [{"start_ms": 0, "end_ms": 3600000, "summary": "旧セグメント"}],
            [[0.1] * 1536],
        )
        # 字幕データ
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])

        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=1800000, summary="新セグメント1"),
            TopicSegment(start_ms=1800000, end_ms=3600000, summary="新セグメント2"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536, [0.2] * 1536]

        segments = service.resegment_video("vid1")
        assert len(segments) == 2
        assert segments[0].summary == "新セグメント1"

    def test_resegment_no_subtitles(self, service, db):
        """字幕がない場合は空リスト"""
        segments = service.resegment_video("vid1")
        assert segments == []

    def test_resegment_nonexistent_video(self, service, db):
        """存在しない動画IDでは空リスト"""
        segments = service.resegment_video("nonexistent")
        assert segments == []

    def test_resegment_keeps_segments_on_llm_failure(self, service, mock_llm, mock_embedding, db):
        """LLMが空リストを返した場合、旧セグメントが保持される"""
        # 既存セグメント
        db.save_segments_with_vectors(
            "vid1",
            [{"start_ms": 0, "end_ms": 3600000, "summary": "旧セグメント"}],
            [[0.1] * 1536],
        )
        # 字幕データ
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])

        # LLMが空リストを返す（JSONパースエラー等でセグメント生成失敗）
        mock_llm.analyze_topics.return_value = []

        segments = service.resegment_video("vid1")
        assert segments == []

        # 旧セグメントが保持されていることを確認
        stored = db.list_segments("vid1")
        assert len(stored) == 1
        assert stored[0].summary == "旧セグメント"


class TestSegmentVersionRecording:
    def test_segment_version_recorded_on_save(self, service, mock_llm, mock_embedding, db):
        """セグメント保存時にプロンプトバージョンが記録される"""
        from kirinuki.infra.llm_client import SEGMENT_PROMPT_VERSION

        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="話題1"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]

        entries = [SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")]
        service.segment_video_from_entries("vid1", entries, 60)

        result = db.get_video_ids_with_segment_version(SEGMENT_PROMPT_VERSION)
        assert "vid1" in result

    def test_segment_version_updated_on_resegment(self, service, mock_llm, mock_embedding, db):
        """再セグメンテーション時にバージョンが更新される"""
        from kirinuki.infra.llm_client import SEGMENT_PROMPT_VERSION

        # 初回セグメンテーション
        db.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕"),
        ])
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=3600000, summary="セグメント"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]

        service.resegment_video("vid1")
        result = db.get_video_ids_with_segment_version(SEGMENT_PROMPT_VERSION)
        assert "vid1" in result

    def test_no_version_recorded_when_llm_returns_empty(self, service, mock_llm, mock_embedding, db):
        """LLMが空リストを返した場合はバージョンが記録されない"""
        from kirinuki.infra.llm_client import SEGMENT_PROMPT_VERSION

        mock_llm.analyze_topics.return_value = []

        entries = [SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")]
        service.segment_video_from_entries("vid1", entries, 60)

        result = db.get_video_ids_with_segment_version(SEGMENT_PROMPT_VERSION)
        assert "vid1" not in result


class TestListSegments:
    def test_list(self, service, db, mock_llm, mock_embedding):
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="話題1"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]
        service.segment_video("vid1", "テスト")
        segs = service.list_segments("vid1")
        assert len(segs) == 1
