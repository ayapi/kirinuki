"""同期パイプラインE2Eテスト — チャンネル登録→同期→検索の完全ワークフロー"""

from unittest.mock import MagicMock

import pytest

from kirinuki.core.channel_service import ChannelService
from kirinuki.core.search_service import SearchService
from kirinuki.core.segmentation_service import SegmentationService
from kirinuki.core.sync_service import SyncService
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import SubtitleData, VideoMeta
from kirinuki.models.domain import SubtitleEntry, TopicSegment


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    return database


@pytest.fixture
def mock_ytdlp():
    return MagicMock()


@pytest.fixture
def mock_llm():
    return MagicMock()


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.dimensions = 1536
    mock.embed.return_value = [[0.5] * 1536, [0.8] * 1536]
    return mock


@pytest.fixture
def services(db, mock_ytdlp, mock_llm, mock_embedding):
    channel_svc = ChannelService(db=db, ytdlp_client=mock_ytdlp)
    seg_svc = SegmentationService(db=db, llm_client=mock_llm, embedding_provider=mock_embedding)
    sync_svc = SyncService(db=db, ytdlp_client=mock_ytdlp, segmentation_service=seg_svc)
    search_svc = SearchService(db=db, embedding_provider=mock_embedding)
    return {
        "channel": channel_svc,
        "sync": sync_svc,
        "segmentation": seg_svc,
        "search": search_svc,
    }


class TestFullWorkflow:
    def test_register_sync_search(
        self, services, mock_ytdlp, mock_llm, mock_embedding, db
    ) -> None:
        """チャンネル登録→同期→検索の完全フロー"""
        # 1. チャンネル登録
        mock_ytdlp.resolve_channel_name.return_value = ("UC_TEST", "テストチャンネル")
        ch = services["channel"].register("https://youtube.com/c/test")
        assert ch.channel_id == "UC_TEST"

        # 2. 同期（2本の動画）
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(video_id="vid1", title="配信#1 マインクラフト", published_at=None, duration_seconds=7200),
            VideoMeta(video_id="vid2", title="配信#2 雑談", published_at=None, duration_seconds=3600),
        ]
        mock_ytdlp.fetch_subtitle.side_effect = [
            SubtitleData(
                video_id="vid1",
                language="ja",
                is_auto_generated=False,
                entries=[
                    SubtitleEntry(start_ms=0, duration_ms=5000, text="こんにちは今日もマインクラフトやります"),
                    SubtitleEntry(start_ms=60000, duration_ms=5000, text="ダイヤモンドを見つけました"),
                    SubtitleEntry(start_ms=120000, duration_ms=5000, text="エンダードラゴンに挑戦"),
                ],
            ),
            SubtitleData(
                video_id="vid2",
                language="ja",
                is_auto_generated=True,
                entries=[
                    SubtitleEntry(start_ms=0, duration_ms=5000, text="今日は雑談配信です"),
                    SubtitleEntry(start_ms=60000, duration_ms=5000, text="最近見た映画の話"),
                ],
            ),
        ]
        mock_llm.analyze_topics.side_effect = [
            [
                TopicSegment(start_ms=0, end_ms=60000, summary="挨拶とゲーム紹介"),
                TopicSegment(start_ms=60000, end_ms=180000, summary="マインクラフト実況"),
            ],
            [
                TopicSegment(start_ms=0, end_ms=60000, summary="雑談開始"),
                TopicSegment(start_ms=60000, end_ms=120000, summary="映画レビュー"),
            ],
        ]

        result = services["sync"].sync_all()
        assert result.newly_synced == 2
        assert result.already_synced == 0

        # 3. 検索
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results = services["search"].search("マインクラフト")
        assert len(results) > 0
        # YouTube URLのフォーマット確認
        for r in results:
            assert "youtube.com/watch?v=" in r.youtube_url
            assert "&t=" in r.youtube_url

    def test_differential_sync(
        self, services, mock_ytdlp, mock_llm, mock_embedding, db
    ) -> None:
        """差分同期: 2回目の同期で既存動画がスキップされること"""
        mock_ytdlp.resolve_channel_name.return_value = ("UC_TEST", "テストチャンネル")
        services["channel"].register("https://youtube.com/c/test")

        # 1回目の同期
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Video 1", published_at=None, duration_seconds=3600
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid1",
            language="ja",
            is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="テスト字幕")],
        )
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=0, end_ms=60000, summary="テスト"),
        ]
        mock_embedding.embed.return_value = [[0.5] * 1536]

        result1 = services["sync"].sync_all()
        assert result1.newly_synced == 1

        # 2回目の同期（新規動画1本追加）
        mock_ytdlp.list_channel_video_ids.return_value = ["vid1", "vid2"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid2", title="Video 2", published_at=None, duration_seconds=7200
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid2",
            language="ja",
            is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=0, duration_ms=5000, text="2回目テスト")],
        )

        result2 = services["sync"].sync_all()
        assert result2.already_synced == 1  # vid1 はスキップ
        assert result2.newly_synced == 1  # vid2 は新規取得

    def test_skip_no_subtitle(
        self, services, mock_ytdlp, db
    ) -> None:
        """字幕なし動画のスキップ"""
        mock_ytdlp.resolve_channel_name.return_value = ("UC_TEST", "テストチャンネル")
        services["channel"].register("https://youtube.com/c/test")

        mock_ytdlp.list_channel_video_ids.return_value = ["vid_nosub"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid_nosub", title="No Sub Video", published_at=None, duration_seconds=3600
        )
        mock_ytdlp.fetch_subtitle.return_value = None

        result = services["sync"].sync_all()
        assert result.skipped == 1
        assert result.newly_synced == 0

    def test_search_timestamp_url(
        self, services, mock_ytdlp, mock_llm, mock_embedding, db
    ) -> None:
        """検索結果にタイムスタンプ付きURLが含まれること"""
        mock_ytdlp.resolve_channel_name.return_value = ("UC_TEST", "テストチャンネル")
        services["channel"].register("https://youtube.com/c/test")

        mock_ytdlp.list_channel_video_ids.return_value = ["vid1"]
        mock_ytdlp.fetch_video_metadata.return_value = VideoMeta(
            video_id="vid1", title="Video 1", published_at=None, duration_seconds=3600
        )
        mock_ytdlp.fetch_subtitle.return_value = SubtitleData(
            video_id="vid1",
            language="ja",
            is_auto_generated=False,
            entries=[SubtitleEntry(start_ms=90000, duration_ms=5000, text="テストキーワードです")],
        )
        mock_llm.analyze_topics.return_value = [
            TopicSegment(start_ms=60000, end_ms=180000, summary="テストトピック"),
        ]
        mock_embedding.embed.return_value = [[0.5] * 1536]

        services["sync"].sync_all()

        mock_embedding.embed.return_value = [[0.5] * 1536]
        results = services["search"].search("テストキーワード")
        # ベクトル検索で結果が返る
        assert len(results) > 0
        for r in results:
            assert r.youtube_url.startswith("https://www.youtube.com/watch?v=vid1&t=")
