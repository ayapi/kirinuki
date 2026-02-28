"""推薦データモデルのテスト"""

import pytest
from pydantic import ValidationError

from kirinuki.models.recommendation import (
    SegmentRecommendation,
    SuggestOptions,
    SuggestResult,
    VideoWithRecommendations,
)


class TestSegmentRecommendation:
    def test_valid_recommendation(self) -> None:
        rec = SegmentRecommendation(
            segment_id=1,
            video_id="abc123",
            start_time=60.0,
            end_time=180.0,
            score=8,
            summary="面白い話題について語っている",
            appeal="独立して楽しめる内容で、エンタメ性が高い",
            prompt_version="v1",
        )
        assert rec.segment_id == 1
        assert rec.video_id == "abc123"
        assert rec.start_time == 60.0
        assert rec.end_time == 180.0
        assert rec.score == 8
        assert rec.summary == "面白い話題について語っている"
        assert rec.appeal == "独立して楽しめる内容で、エンタメ性が高い"
        assert rec.prompt_version == "v1"

    def test_score_minimum_boundary(self) -> None:
        rec = SegmentRecommendation(
            segment_id=1,
            video_id="abc123",
            start_time=0.0,
            end_time=60.0,
            score=1,
            summary="要約",
            appeal="魅力",
            prompt_version="v1",
        )
        assert rec.score == 1

    def test_score_maximum_boundary(self) -> None:
        rec = SegmentRecommendation(
            segment_id=1,
            video_id="abc123",
            start_time=0.0,
            end_time=60.0,
            score=10,
            summary="要約",
            appeal="魅力",
            prompt_version="v1",
        )
        assert rec.score == 10

    def test_score_below_minimum_raises(self) -> None:
        with pytest.raises(ValidationError):
            SegmentRecommendation(
                segment_id=1,
                video_id="abc123",
                start_time=0.0,
                end_time=60.0,
                score=0,
                summary="要約",
                appeal="魅力",
                prompt_version="v1",
            )

    def test_score_above_maximum_raises(self) -> None:
        with pytest.raises(ValidationError):
            SegmentRecommendation(
                segment_id=1,
                video_id="abc123",
                start_time=0.0,
                end_time=60.0,
                score=11,
                summary="要約",
                appeal="魅力",
                prompt_version="v1",
            )

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            SegmentRecommendation(
                segment_id=1,
                video_id="abc123",
                start_time=0.0,
                end_time=60.0,
                score=5,
                # summary missing
                appeal="魅力",
                prompt_version="v1",
            )


class TestSuggestOptions:
    def test_defaults(self) -> None:
        opts = SuggestOptions(channel_id="UC123")
        assert opts.channel_id == "UC123"
        assert opts.count == 3
        assert opts.threshold == 7

    def test_custom_values(self) -> None:
        opts = SuggestOptions(channel_id="UC123", count=5, threshold=5)
        assert opts.count == 5
        assert opts.threshold == 5


class TestVideoWithRecommendations:
    def test_creation(self) -> None:
        rec = SegmentRecommendation(
            segment_id=1,
            video_id="abc123",
            start_time=0.0,
            end_time=60.0,
            score=8,
            summary="要約",
            appeal="魅力",
            prompt_version="v1",
        )
        video = VideoWithRecommendations(
            video_id="abc123",
            title="テスト動画",
            published_at="2026-01-01T00:00:00",
            recommendations=[rec],
        )
        assert video.video_id == "abc123"
        assert video.title == "テスト動画"
        assert len(video.recommendations) == 1


class TestSuggestResult:
    def test_creation(self) -> None:
        result = SuggestResult(
            videos=[],
            total_candidates=10,
            filtered_count=3,
        )
        assert result.total_candidates == 10
        assert result.filtered_count == 3
        assert result.videos == []
