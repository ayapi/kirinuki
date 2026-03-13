"""RecommendationFormatterのユニットテスト"""

import json

from kirinuki.core.clip_utils import parse_time_ranges
from kirinuki.core.formatter import (
    RecommendationFormatter,
    format_broadcast_date,
    format_time,
    format_time_range,
)
from kirinuki.models.recommendation import (
    SegmentRecommendation,
    SuggestResult,
    VideoWithRecommendations,
)


def _make_rec(
    segment_id: int = 1,
    video_id: str = "abc123",
    start_time: float = 60.0,
    end_time: float = 180.0,
    score: int = 8,
    summary: str = "テスト要約",
    appeal: str = "テスト魅力",
) -> SegmentRecommendation:
    return SegmentRecommendation(
        segment_id=segment_id,
        video_id=video_id,
        start_time=start_time,
        end_time=end_time,
        score=score,
        summary=summary,
        appeal=appeal,
        prompt_version="v1",
    )


def _make_result(
    videos: list[VideoWithRecommendations] | None = None,
) -> SuggestResult:
    if videos is None:
        videos = [
            VideoWithRecommendations(
                video_id="abc123",
                title="テスト動画1",
                broadcast_start_at="2026-01-15T00:00:00",
                recommendations=[
                    _make_rec(segment_id=1, start_time=120.0, end_time=300.0, score=9),
                    _make_rec(segment_id=2, start_time=60.0, end_time=120.0, score=7),
                ],
            ),
        ]
    total = sum(len(v.recommendations) for v in videos)
    return SuggestResult(videos=videos, total_candidates=total, filtered_count=total)


class TestFormatBroadcastDate:
    def test_utc_to_local(self) -> None:
        """UTC ISO文字列がローカルタイムゾーンのYYYY-MM-DD HH:MM形式に変換される"""
        from datetime import datetime, timezone

        # UTC 2026-01-15T20:00:00+00:00 → ローカル変換
        result = format_broadcast_date("2026-01-15T20:00:00+00:00")
        # ローカルタイムゾーンでの期待値を動的に算出
        utc_dt = datetime(2026, 1, 15, 20, 0, tzinfo=timezone.utc)
        expected = utc_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        assert result == expected

    def test_naive_datetime(self) -> None:
        """タイムゾーンなしISO文字列もフォーマットされる"""
        result = format_broadcast_date("2026-01-15T20:00:00")
        assert "2026-01-15" in result
        assert ":" in result

    def test_invalid_string_returned_as_is(self) -> None:
        """パース不可の文字列はそのまま返す"""
        assert format_broadcast_date("not-a-date") == "not-a-date"

    def test_empty_string_returned_as_is(self) -> None:
        assert format_broadcast_date("") == ""


class TestFormatTime:
    def test_under_one_hour(self) -> None:
        assert format_time(65.0) == "1:05"

    def test_over_one_hour(self) -> None:
        assert format_time(3661.0) == "1:01:01"

    def test_zero(self) -> None:
        assert format_time(0.0) == "0:00"


class TestFormatTimeRange:
    def test_basic_range(self) -> None:
        result = format_time_range(60.0, 180.0)
        assert result == "1:00-3:00"

    def test_no_spaces_around_hyphen(self) -> None:
        result = format_time_range(120.0, 300.0)
        assert " " not in result

    def test_over_one_hour(self) -> None:
        result = format_time_range(3600.0, 5400.0)
        assert result == "1:00:00-1:30:00"

    def test_mixed_duration(self) -> None:
        """開始が1時間未満、終了が1時間以上"""
        result = format_time_range(1800.0, 3700.0)
        assert result == "30:00-1:01:40"

    def test_roundtrip_with_clip_parser(self) -> None:
        """format_time_rangeの出力がclipパーサーで正しくパースされる"""
        result = format_time_range(1083.0, 1171.0)
        ranges = parse_time_ranges(result)
        assert len(ranges) == 1
        assert ranges[0].start_seconds == 1083.0
        assert ranges[0].end_seconds == 1171.0

    def test_roundtrip_over_one_hour(self) -> None:
        """1時間以上のラウンドトリップ"""
        result = format_time_range(3661.0, 5400.0)
        ranges = parse_time_ranges(result)
        assert len(ranges) == 1
        assert ranges[0].start_seconds == 3661.0
        assert ranges[0].end_seconds == 5400.0


class TestFormatText:
    def test_contains_video_header(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        text = fmt.format_text(result)
        assert "テスト動画1" in text
        assert "2026-01-15" in text

    def test_contains_recommendation_info(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        text = fmt.format_text(result)
        assert "テスト要約" in text
        assert "テスト魅力" in text

    def test_contains_youtube_url(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        text = fmt.format_text(result)
        assert "https://www.youtube.com/watch?v=abc123&t=" in text

    def test_contains_score(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        text = fmt.format_text(result)
        assert "9" in text
        assert "7" in text

    def test_within_video_sorted_by_time(self) -> None:
        """同一動画内の推薦は時系列順"""
        fmt = RecommendationFormatter()
        result = _make_result()
        text = fmt.format_text(result)
        # start_time=60.0 (segment 2) が start_time=120.0 (segment 1) より前に来る
        pos_60 = text.find("1:00")
        pos_120 = text.find("2:00")
        assert pos_60 < pos_120

    def test_groups_sorted_by_max_score_desc(self) -> None:
        """動画グループは最高スコアの降順"""
        fmt = RecommendationFormatter()
        videos = [
            VideoWithRecommendations(
                video_id="low",
                title="低スコア動画",
                broadcast_start_at="2026-01-10T00:00:00",
                recommendations=[_make_rec(video_id="low", score=5)],
            ),
            VideoWithRecommendations(
                video_id="high",
                title="高スコア動画",
                broadcast_start_at="2026-01-15T00:00:00",
                recommendations=[_make_rec(video_id="high", score=10)],
            ),
        ]
        result = _make_result(videos=videos)
        text = fmt.format_text(result)
        pos_high = text.find("高スコア動画")
        pos_low = text.find("低スコア動画")
        assert pos_high < pos_low

    def test_empty_result(self) -> None:
        fmt = RecommendationFormatter()
        result = SuggestResult(videos=[], total_candidates=5, filtered_count=0)
        text = fmt.format_text(result)
        assert "該当なし" in text or "0件" in text


class TestFormatJson:
    def test_valid_json(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        json_str = fmt.format_json(result)
        parsed = json.loads(json_str)
        assert isinstance(parsed, dict)

    def test_contains_required_fields(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        json_str = fmt.format_json(result)
        parsed = json.loads(json_str)

        assert "videos" in parsed
        assert "total_candidates" in parsed
        assert "filtered_count" in parsed

        video = parsed["videos"][0]
        assert "video_id" in video
        assert "title" in video
        assert "broadcast_start_at" in video
        assert "recommendations" in video

        rec = video["recommendations"][0]
        assert "score" in rec
        assert "summary" in rec
        assert "appeal" in rec
        assert "start_time" in rec
        assert "end_time" in rec
        assert "youtube_url" in rec

    def test_youtube_url_in_json(self) -> None:
        fmt = RecommendationFormatter()
        result = _make_result()
        json_str = fmt.format_json(result)
        parsed = json.loads(json_str)
        rec = parsed["videos"][0]["recommendations"][0]
        assert rec["youtube_url"].startswith("https://www.youtube.com/watch?v=")
