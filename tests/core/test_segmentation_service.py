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


class TestListSegments:
    def test_list(self, service, db, mock_llm, mock_embedding):
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="話題1"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]
        service.segment_video("vid1", "テスト")
        segs = service.list_segments("vid1")
        assert len(segs) == 1
