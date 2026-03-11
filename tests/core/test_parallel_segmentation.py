"""チャンク処理・resplitの並列実行テスト"""

import threading
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
    database.save_video("vid1", "UC1", "Video 1", None, 3600 * 5, "ja", False)
    return database


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.dimensions = 1536
    return mock


def _make_long_entries(minutes: int = 300) -> list[SubtitleEntry]:
    """指定分数分の字幕エントリーを生成する"""
    return [
        SubtitleEntry(start_ms=i * 60_000, duration_ms=5000, text=f"テスト字幕 {i}分")
        for i in range(minutes)
    ]


class TestChunkParallelExecution:
    def test_chunks_processed_in_parallel(self, db, mock_llm, mock_embedding):
        """複数チャンクがThreadPoolExecutorで並列処理される"""
        import time as time_mod

        thread_ids: list[int] = []
        lock = threading.Lock()

        def fake_analyze(text: str) -> list[TopicSegment]:
            with lock:
                thread_ids.append(threading.current_thread().ident)
            time_mod.sleep(0.01)  # 並列実行を促す
            return [TopicSegment(start_ms=0, end_ms=60000, summary="テスト")]

        mock_llm.analyze_topics.side_effect = fake_analyze
        mock_embedding.embed.return_value = [[0.1] * 1536]

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=4,
        )
        entries = _make_long_entries(300)
        service.segment_video_from_entries("vid1", entries, 5 * 3600)

        # 複数チャンクが処理されている（analyze_topicsが複数回呼ばれる）
        assert mock_llm.analyze_topics.call_count > 1
        # 複数のスレッドが使われている（並列実行の証拠）
        unique_threads = set(thread_ids)
        assert len(unique_threads) > 1

    def test_chunk_results_maintain_order(self, db, mock_llm, mock_embedding):
        """並列処理でもチャンクの結果順序が維持される"""
        call_order: list[int] = []
        lock = threading.Lock()

        def fake_analyze(text: str) -> list[TopicSegment]:
            # テキストから分数を抽出して順序を記録
            first_line = text.split("\n")[0]
            minute = int(first_line.split("]")[0].split(":")[0].strip("["))
            with lock:
                call_order.append(minute)
            return [TopicSegment(
                start_ms=minute * 60000,
                end_ms=(minute + 10) * 60000,
                summary=f"話題{minute}分",
            )]

        mock_llm.analyze_topics.side_effect = fake_analyze
        mock_embedding.embed.return_value = [[0.1] * 1536] * mock_llm.analyze_topics.call_count

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=4,
        )
        entries = _make_long_entries(300)

        # embed のreturn_valueを動的に設定
        mock_embedding.embed.side_effect = lambda texts: [[0.1] * 1536] * len(texts)

        segments = service.segment_video_from_entries("vid1", entries, 5 * 3600)

        # 結果のセグメントが時系列順であること
        start_times = [s.start_ms for s in segments]
        assert start_times == sorted(start_times)

    def test_single_chunk_skips_threading(self, db, mock_llm, mock_embedding):
        """1チャンクの場合はスレッドプールを使わない"""
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="テスト"),
        ]
        mock_embedding.embed.return_value = [[0.1] * 1536]

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=4,
        )
        # 短い動画だがテキスト量が多い場合（1チャンクに収まるケース）
        entries = [SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト")]
        service.segment_video_from_entries("vid1", entries, 60)

        assert mock_llm.analyze_topics.call_count == 1

    def test_max_workers_limits_concurrency(self, db, mock_llm, mock_embedding):
        """max_workersが同時実行数を制限する"""
        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        def fake_analyze(text: str) -> list[TopicSegment]:
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            import time
            time.sleep(0.01)  # 並列実行を促す
            with lock:
                current_concurrent -= 1
            return [TopicSegment(start_ms=0, end_ms=60000, summary="テスト")]

        mock_llm.analyze_topics.side_effect = fake_analyze
        mock_embedding.embed.side_effect = lambda texts: [[0.1] * 1536] * len(texts)

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=2,
        )
        entries = _make_long_entries(300)
        service.segment_video_from_entries("vid1", entries, 5 * 3600)

        assert max_concurrent <= 2


class TestResplitParallelExecution:
    def test_multiple_oversized_segments_parallel(self, db, mock_llm, mock_embedding):
        """複数のoversizedセグメントが並列で再分割される"""
        import time as time_mod

        thread_ids: list[int] = []
        lock = threading.Lock()

        # 3つの大きなセグメントを返す
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題1"),
            TopicSegment(start_ms=600000, end_ms=1200000, summary="長い話題2"),
            TopicSegment(start_ms=1200000, end_ms=1800000, summary="長い話題3"),
        ]

        def fake_resplit(text: str, parent: str) -> list[TopicSegment]:
            with lock:
                thread_ids.append(threading.current_thread().ident)
            time_mod.sleep(0.01)  # 並列実行を促す
            # 各セグメントを2分割
            if "話題1" in parent:
                return [
                    TopicSegment(start_ms=0, end_ms=300000, summary="話題1前半"),
                    TopicSegment(start_ms=300000, end_ms=600000, summary="話題1後半"),
                ]
            elif "話題2" in parent:
                return [
                    TopicSegment(start_ms=600000, end_ms=900000, summary="話題2前半"),
                    TopicSegment(start_ms=900000, end_ms=1200000, summary="話題2後半"),
                ]
            else:
                return [
                    TopicSegment(start_ms=1200000, end_ms=1500000, summary="話題3前半"),
                    TopicSegment(start_ms=1500000, end_ms=1800000, summary="話題3後半"),
                ]

        mock_llm.analyze_topics_resplit.side_effect = fake_resplit
        mock_embedding.embed.side_effect = lambda texts: [[0.1] * 1536] * len(texts)

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=4,
        )
        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(30)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 1800, max_segment_ms=300000,
        )

        # 3つのセグメントが再分割された
        assert mock_llm.analyze_topics_resplit.call_count == 3
        # 複数スレッドで実行された
        unique_threads = set(thread_ids)
        assert len(unique_threads) > 1
        # 結果が6セグメント（3×2）
        assert len(segments) == 6

    def test_resplit_order_preserved(self, db, mock_llm, mock_embedding):
        """再分割結果の順序が正しく維持される"""
        # oversized 2つ + 通常 1つ（中間）の混在
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=600000, summary="長い話題A"),
            TopicSegment(start_ms=600000, end_ms=660000, summary="短い話題B"),
            TopicSegment(start_ms=660000, end_ms=1260000, summary="長い話題C"),
        ]

        def fake_resplit(text: str, parent: str) -> list[TopicSegment]:
            if "A" in parent:
                return [
                    TopicSegment(start_ms=0, end_ms=300000, summary="A前半"),
                    TopicSegment(start_ms=300000, end_ms=600000, summary="A後半"),
                ]
            else:
                return [
                    TopicSegment(start_ms=660000, end_ms=960000, summary="C前半"),
                    TopicSegment(start_ms=960000, end_ms=1260000, summary="C後半"),
                ]

        mock_llm.analyze_topics_resplit.side_effect = fake_resplit
        mock_embedding.embed.side_effect = lambda texts: [[0.1] * 1536] * len(texts)

        service = SegmentationService(
            db=db, llm_client=mock_llm, embedding_provider=mock_embedding,
            max_workers=4,
        )
        entries = [
            SubtitleEntry(start_ms=i * 60000, duration_ms=5000, text=f"テスト{i}")
            for i in range(21)
        ]
        segments = service.segment_video_from_entries(
            "vid1", entries, 1260, max_segment_ms=300000,
        )

        # A前半, A後半, 短い話題B, C前半, C後半 = 5セグメント
        assert len(segments) == 5
        summaries = [s.summary for s in segments]
        # 順序が維持されている
        assert "A前半" in summaries[0] or summaries[0] == "A前半"
        start_times = [s.start_ms for s in segments]
        assert start_times == sorted(start_times)
