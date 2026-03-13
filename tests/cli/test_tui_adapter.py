"""TUIアダプター関数のユニットテスト"""

import pytest

from kirinuki.cli.tui import adapt_search_results, adapt_segments, adapt_suggest_results
from kirinuki.models.domain import MatchType, SearchResult, Segment
from kirinuki.models.recommendation import (
    SegmentRecommendation,
    SuggestResult,
    VideoWithRecommendations,
)


class TestAdaptSearchResults:
    def test_basic_conversion(self) -> None:
        results = [
            SearchResult(
                video_title="テスト動画",
                channel_name="テストch",
                start_time_ms=60000,
                end_time_ms=120000,
                summary="面白い話題",
                youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=60",
                score=0.85,
                match_type=MatchType.KEYWORD,
            ),
        ]
        candidates = adapt_search_results(results)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.video_id == "dQw4w9WgXcQ"
        assert c.start_ms == 60000
        assert c.end_ms == 120000
        assert c.summary == "面白い話題"
        assert c.video_title == "テスト動画"
        assert c.channel_name == "テストch"
        assert c.score == 0.85
        assert c.match_type == "keyword"

    def test_display_label_format(self) -> None:
        results = [
            SearchResult(
                video_title="動画タイトル",
                channel_name="ch名",
                start_time_ms=1083000,
                end_time_ms=1171000,
                summary="話題の要約",
                youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1083",
                score=0.85,
                match_type=MatchType.KEYWORD,
            ),
        ]
        candidates = adapt_search_results(results)
        label = candidates[0].display_label
        assert "0.85" in label
        assert "動画タイトル" in label
        assert "話題の要約" in label

    def test_empty_input(self) -> None:
        assert adapt_search_results([]) == []

    def test_invalid_url_skipped(self) -> None:
        results = [
            SearchResult(
                video_title="test",
                channel_name="ch",
                start_time_ms=0,
                end_time_ms=1000,
                summary="summary",
                youtube_url="https://invalid-url.com/page",
            ),
        ]
        candidates = adapt_search_results(results)
        assert len(candidates) == 0


class TestAdaptSegments:
    def test_basic_conversion(self) -> None:
        segments = [
            Segment(id=1, video_id="abc12345678", start_ms=60000, end_ms=180000, summary="話題A"),
            Segment(id=2, video_id="abc12345678", start_ms=180000, end_ms=300000, summary="話題B"),
        ]
        candidates = adapt_segments(segments)
        assert len(candidates) == 2
        assert candidates[0].video_id == "abc12345678"
        assert candidates[0].start_ms == 60000
        assert candidates[0].summary == "話題A"
        assert candidates[1].summary == "話題B"

    def test_display_label_format(self) -> None:
        segments = [
            Segment(id=1, video_id="abc12345678", start_ms=1083000, end_ms=1171000, summary="要約テスト"),
        ]
        candidates = adapt_segments(segments)
        label = candidates[0].display_label
        assert "要約テスト" in label
        # 時間範囲が含まれる
        assert "18:03" in label

    def test_empty_input(self) -> None:
        assert adapt_segments([]) == []


class TestAdaptSuggestResults:
    def test_basic_conversion(self) -> None:
        result = SuggestResult(
            videos=[
                VideoWithRecommendations(
                    video_id="vid12345678",
                    title="動画タイトル",
                    broadcast_start_at="2025-01-01",
                    recommendations=[
                        SegmentRecommendation(
                            segment_id=1,
                            video_id="vid12345678",
                            start_time=60.0,
                            end_time=180.0,
                            score=8,
                            summary="おすすめ話題",
                            appeal="とても面白い",
                            prompt_version="v3",
                        ),
                    ],
                ),
            ],
            total_candidates=10,
            filtered_count=1,
        )
        candidates = adapt_suggest_results(result)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.video_id == "vid12345678"
        assert c.start_ms == 60000
        assert c.end_ms == 180000
        assert c.summary == "おすすめ話題"
        assert c.recommend_score == 8
        assert c.appeal == "とても面白い"
        assert c.video_title == "動画タイトル"

    def test_display_label_format(self) -> None:
        result = SuggestResult(
            videos=[
                VideoWithRecommendations(
                    video_id="vid12345678",
                    title="動画名",
                    broadcast_start_at="2025-01-01",
                    recommendations=[
                        SegmentRecommendation(
                            segment_id=1,
                            video_id="vid12345678",
                            start_time=60.0,
                            end_time=120.0,
                            score=9,
                            summary="話題",
                            appeal="魅力",
                            prompt_version="v3",
                        ),
                    ],
                ),
            ],
            total_candidates=5,
            filtered_count=1,
        )
        candidates = adapt_suggest_results(result)
        label = candidates[0].display_label
        assert "9/10" in label
        assert "動画名" in label

    def test_multiple_videos_flattened(self) -> None:
        result = SuggestResult(
            videos=[
                VideoWithRecommendations(
                    video_id="vid_a_123456",
                    title="動画A",
                    broadcast_start_at="2025-01-01",
                    recommendations=[
                        SegmentRecommendation(
                            segment_id=1, video_id="vid_a_123456",
                            start_time=0.0, end_time=60.0,
                            score=7, summary="A1", appeal="a", prompt_version="v3",
                        ),
                    ],
                ),
                VideoWithRecommendations(
                    video_id="vid_b_123456",
                    title="動画B",
                    broadcast_start_at="2025-01-02",
                    recommendations=[
                        SegmentRecommendation(
                            segment_id=2, video_id="vid_b_123456",
                            start_time=30.0, end_time=90.0,
                            score=9, summary="B1", appeal="b", prompt_version="v3",
                        ),
                    ],
                ),
            ],
            total_candidates=10,
            filtered_count=2,
        )
        candidates = adapt_suggest_results(result)
        assert len(candidates) == 2

    def test_empty_videos(self) -> None:
        result = SuggestResult(videos=[], total_candidates=0, filtered_count=0)
        assert adapt_suggest_results(result) == []
