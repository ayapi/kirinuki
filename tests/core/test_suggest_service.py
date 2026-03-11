"""SuggestServiceのユニットテスト"""

from pathlib import Path

import pytest

from kirinuki.core.errors import ChannelNotFoundError, NoArchivesError
from kirinuki.core.suggest import SuggestService
from kirinuki.infra.database import Database
from kirinuki.models.recommendation import SegmentRecommendation, SuggestOptions


def _setup_db(tmp_path: Path) -> Database:
    """テスト用DBを準備する"""
    db = Database(db_path=tmp_path / "test.db", embedding_dimensions=1536)
    db.initialize()
    db.save_channel("UC123", "テストチャンネル", "https://youtube.com/c/test")
    return db


def _add_videos(db: Database, count: int) -> None:
    """テスト用動画をN件追加する"""
    from datetime import datetime, timezone
    for i in range(count):
        db.save_video(
            video_id=f"vid{i:03d}",
            channel_id="UC123",
            title=f"テスト動画 {i}",
            published_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            duration_seconds=3600,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )


def _add_segments(db: Database, video_id: str, count: int) -> None:
    """テスト用セグメントを追加する"""
    segments_data = [
        {"start_ms": i * 60000, "end_ms": (i + 1) * 60000, "summary": f"話題{i}: テスト話題の要約"}
        for i in range(count)
    ]
    db.save_segments(video_id, segments_data)


class FakeLLMClient:
    """テスト用のLLMクライアント"""

    def __init__(self, score: int = 8) -> None:
        self.score = score
        self.call_count = 0

    def evaluate_segments(
        self, video_id: str, segments: list[dict[str, str | int]], prompt_version: str
    ) -> list[SegmentRecommendation]:
        self.call_count += 1
        return [
            SegmentRecommendation(
                segment_id=seg["id"],
                video_id=video_id,
                start_time=seg["start_ms"] / 1000.0,
                end_time=seg["end_ms"] / 1000.0,
                score=self.score,
                summary=f"要約: {seg['summary']}",
                appeal=f"魅力: エンタメ性が高く独立して楽しめる",
                prompt_version=prompt_version,
            )
            for seg in segments
        ]


class TestSuggestOptionsDefaults:
    def test_video_ids_default_none(self) -> None:
        opts = SuggestOptions(channel_id="UC123")
        assert opts.video_ids is None

    def test_channel_id_default_none(self) -> None:
        opts = SuggestOptions()
        assert opts.channel_id is None

    def test_video_ids_set(self) -> None:
        opts = SuggestOptions(video_ids=["vid001", "vid002"])
        assert opts.video_ids == ["vid001", "vid002"]
        assert opts.channel_id is None


class TestSuggestResultWarnings:
    def test_warnings_default_empty(self) -> None:
        from kirinuki.models.recommendation import SuggestResult

        result = SuggestResult(videos=[], total_candidates=0, filtered_count=0)
        assert result.warnings == []

    def test_warnings_set(self) -> None:
        from kirinuki.models.recommendation import SuggestResult

        result = SuggestResult(
            videos=[], total_candidates=0, filtered_count=0,
            warnings=["動画ID 'abc' はデータベースに存在しません"],
        )
        assert len(result.warnings) == 1


class TestLatestVideoSelection:
    def test_select_latest_3_videos(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 5)
        for i in range(5):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=3, threshold=1)
        result = service.suggest(opts)

        assert len(result.videos) == 3

    def test_select_with_fewer_archives(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 2)
        for i in range(2):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=3, threshold=1)
        result = service.suggest(opts)

        assert len(result.videos) == 2

    def test_zero_archives_raises_error(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123")

        with pytest.raises(NoArchivesError):
            service.suggest(opts)

    def test_unregistered_channel_raises_error(self, tmp_path: Path) -> None:
        db = Database(db_path=tmp_path / "test.db", embedding_dimensions=1536)
        db.initialize()
        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UNKNOWN")

        with pytest.raises(ChannelNotFoundError):
            service.suggest(opts)


class TestVideoIdFiltering:
    def test_video_ids_uses_get_videos_by_ids(self, tmp_path: Path) -> None:
        """video_ids指定時はget_videos_by_idsが呼ばれる"""
        db = _setup_db(tmp_path)
        _add_videos(db, 5)
        for i in range(5):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(video_ids=["vid000", "vid002"], threshold=1)
        result = service.suggest(opts)

        video_ids = [v.video_id for v in result.videos]
        assert set(video_ids) == {"vid000", "vid002"}

    def test_video_ids_ignores_count(self, tmp_path: Path) -> None:
        """video_ids指定時はcountは無視される"""
        db = _setup_db(tmp_path)
        _add_videos(db, 5)
        for i in range(5):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(video_ids=["vid000", "vid001", "vid002"], count=1, threshold=1)
        result = service.suggest(opts)

        assert len(result.videos) == 3

    def test_video_ids_skips_channel_check(self, tmp_path: Path) -> None:
        """video_ids指定時はチャンネルIDのチェックをスキップ"""
        db = _setup_db(tmp_path)
        _add_videos(db, 2)
        for i in range(2):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        # channel_id=None でもvideo_idsがあればエラーにならない
        opts = SuggestOptions(video_ids=["vid000"], threshold=1)
        result = service.suggest(opts)
        assert len(result.videos) == 1

    def test_partial_missing_ids_adds_warnings(self, tmp_path: Path) -> None:
        """一部の動画IDが存在しない場合は警告を出す"""
        db = _setup_db(tmp_path)
        _add_videos(db, 2)
        for i in range(2):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(video_ids=["vid000", "MISSING"], threshold=1)
        result = service.suggest(opts)

        assert len(result.videos) == 1
        assert len(result.warnings) == 1
        assert "MISSING" in result.warnings[0]

    def test_all_missing_ids_raises_error(self, tmp_path: Path) -> None:
        """全動画IDが存在しない場合はNoArchivesErrorを送出"""
        db = _setup_db(tmp_path)
        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(video_ids=["MISSING1", "MISSING2"])

        with pytest.raises(NoArchivesError):
            service.suggest(opts)

    def test_without_video_ids_uses_channel(self, tmp_path: Path) -> None:
        """video_ids未指定時は従来のchannel_id+count動作"""
        db = _setup_db(tmp_path)
        _add_videos(db, 5)
        for i in range(5):
            _add_segments(db, f"vid{i:03d}", 2)

        llm = FakeLLMClient()
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=2, threshold=1)
        result = service.suggest(opts)

        assert len(result.videos) == 2


class TestThresholdFiltering:
    def test_all_pass_threshold(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 1)
        _add_segments(db, "vid000", 3)

        llm = FakeLLMClient(score=8)
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=1, threshold=7)
        result = service.suggest(opts)

        assert result.filtered_count == 3
        assert result.total_candidates == 3

    def test_partial_pass_threshold(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 1)
        _add_segments(db, "vid000", 3)

        llm = FakeLLMClient(score=8)
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=1, threshold=9)
        result = service.suggest(opts)

        # score=8 < threshold=9
        assert result.filtered_count == 0

    def test_none_pass_threshold(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 1)
        _add_segments(db, "vid000", 3)

        llm = FakeLLMClient(score=3)
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=1, threshold=7)
        result = service.suggest(opts)

        assert result.filtered_count == 0
        assert result.total_candidates == 3


class TestCaching:
    def test_cache_hit_skips_llm(self, tmp_path: Path) -> None:
        db = _setup_db(tmp_path)
        _add_videos(db, 1)
        _add_segments(db, "vid000", 2)

        llm = FakeLLMClient(score=8)
        service = SuggestService(db=db, llm=llm)
        opts = SuggestOptions(channel_id="UC123", count=1, threshold=1)

        # 1回目: LLM呼び出しが発生
        service.suggest(opts)
        assert llm.call_count == 1

        # 2回目: キャッシュヒットでLLM呼び出しなし
        service.suggest(opts)
        assert llm.call_count == 1
