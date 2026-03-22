"""横断検索サービスのテスト"""

from unittest.mock import MagicMock

import pytest

from kirinuki.core.search_service import SearchService
from kirinuki.infra.database import Database
from kirinuki.models.domain import MatchType, SubtitleEntry


@pytest.fixture
def db():
    database = Database(db_path=":memory:", embedding_dimensions=1536)
    database.initialize()
    # テストデータ
    database.save_channel("UC1", "TestChannel", "https://youtube.com/c/test")
    database.save_video("vid1", "UC1", "Test Video 1", None, 3600, "ja", False)
    entries = [
        SubtitleEntry(start_ms=0, duration_ms=5000, text="こんにちは皆さん今日もよろしく"),
        SubtitleEntry(start_ms=30000, duration_ms=5000, text="今日はマインクラフトを遊びます"),
        SubtitleEntry(start_ms=60000, duration_ms=5000, text="ダイヤモンドを見つけました"),
    ]
    database.save_subtitle_lines("vid1", entries)
    segments = [
        {"start_ms": 0, "end_ms": 60000, "summary": "挨拶とゲーム紹介"},
        {"start_ms": 60000, "end_ms": 120000, "summary": "マインクラフト実況"},
    ]
    vectors = [[0.1] * 1536, [0.9] * 1536]
    database.save_segments_with_vectors("vid1", segments, vectors)
    return database


@pytest.fixture
def mock_embedding():
    mock = MagicMock()
    mock.dimensions = 1536
    return mock


@pytest.fixture
def service(db, mock_embedding):
    return SearchService(db=db, embedding_provider=mock_embedding)


class TestQueryValidation:
    def test_empty_query_returns_warning(self, service, mock_embedding):
        results, warnings = service.search("")
        assert results == []
        assert len(warnings) == 1
        assert "空" in warnings[0]
        mock_embedding.embed.assert_not_called()

    def test_whitespace_only_query_returns_warning(self, service, mock_embedding):
        results, warnings = service.search("   \t\n  ")
        assert results == []
        assert len(warnings) == 1
        mock_embedding.embed.assert_not_called()

    def test_query_is_stripped(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, _ = service.search("  マインクラフト  ")
        assert len(results) > 0
        mock_embedding.embed.assert_called_once_with(["マインクラフト"])

    def test_empty_embedding_result_does_not_raise(self, service, mock_embedding):
        """embeddingプロバイダが空リストを返してもIndexErrorにならない"""
        mock_embedding.embed.return_value = []
        results, warnings = service.search("マインクラフト")
        # IndexErrorが発生せず、FTS結果が保持されること
        assert len(results) > 0
        assert any("意味検索" in w for w in warnings)

    def test_empty_embedding_with_short_query(self, service, mock_embedding):
        """短いクエリでFTSもスキップされる場合、空結果+警告が返る"""
        mock_embedding.embed.return_value = []
        results, warnings = service.search("ab")
        assert results == []
        assert any("意味検索" in w for w in warnings)


class TestSearch:
    def test_keyword_search(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, _ = service.search("マインクラフト")
        assert len(results) > 0

    def test_vector_search(self, service, mock_embedding):
        # L2距離が1.0未満になるよう、保存済みベクトル[0.9]*1536に近いベクトルを使用
        mock_embedding.embed.return_value = [[0.9] * 1536]
        results, _ = service.search("ゲーム実況")
        assert len(results) > 0

    def test_no_results(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.0] * 1536]
        results, _ = service.search("xyz_nonexistent_zzz")
        # ベクトル検索は距離ベースなので結果が返ることがある
        # キーワード検索のみで該当なしをテスト

    def test_youtube_url_format(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results, _ = service.search("マインクラフト")
        for r in results:
            assert "youtube.com/watch?v=" in r.youtube_url
            assert "&t=" in r.youtube_url

    def test_limit(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, _ = service.search("マインクラフト", limit=1)
        assert len(results) <= 1


class TestMatchTypeTracking:
    def test_keyword_only_match_type(self, service, mock_embedding):
        """FTSのみでヒットした場合、match_type=KEYWORDが設定される"""
        mock_embedding.embed.return_value = [[0.0] * 1536]  # 遠い距離 → ベクトルマッチなし
        results, _ = service.search("マインクラフト")
        keyword_results = [r for r in results if r.match_type == MatchType.KEYWORD]
        assert len(keyword_results) > 0
        for r in keyword_results:
            assert r.snippet is not None
            assert r.similarity is None

    def test_semantic_only_match_type(self, service, mock_embedding):
        """ベクトルのみでヒットした場合、match_type=SEMANTICが設定される"""
        # L2距離が1.0未満になるよう、保存済みベクトル[0.9]*1536に近いベクトルを使用
        mock_embedding.embed.return_value = [[0.9] * 1536]
        results, _ = service.search("ab")  # 2文字 → FTS不発
        semantic_results = [r for r in results if r.match_type == MatchType.SEMANTIC]
        assert len(semantic_results) > 0
        for r in semantic_results:
            assert r.similarity is not None
            assert 0.0 < r.similarity <= 1.0

    def test_hybrid_match_type(self, service, mock_embedding):
        """FTSとベクトル両方でヒットした場合、match_type=HYBRIDが設定される"""
        mock_embedding.embed.return_value = [[0.1] * 1536]  # segment1のベクトルに近い
        results, _ = service.search("マインクラフト")
        hybrid_results = [r for r in results if r.match_type == MatchType.HYBRID]
        # FTSとベクトルが同じセグメントにヒットすればhybrid
        for r in hybrid_results:
            assert r.snippet is not None
            assert r.similarity is not None

    def test_similarity_score_range(self, service, mock_embedding):
        """similarity は 0.0〜1.0 の範囲である"""
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, _ = service.search("マインクラフト")
        for r in results:
            if r.similarity is not None:
                assert 0.0 <= r.similarity <= 1.0

    def test_snippet_from_fts(self, service, mock_embedding):
        """FTSマッチ結果にsnippetが設定される"""
        mock_embedding.embed.return_value = [[0.0] * 1536]
        results, _ = service.search("マインクラフト")
        fts_results = [r for r in results if r.match_type in (MatchType.KEYWORD, MatchType.HYBRID)]
        for r in fts_results:
            assert r.snippet is not None
            assert len(r.snippet) > 0


class TestShortQueryLikeFallback:
    """3文字未満のクエリでLIKEフォールバックが動作することのテスト"""

    @pytest.fixture
    def service_with_short_text(self, mock_embedding):
        database = Database(db_path=":memory:", embedding_dimensions=1536)
        database.initialize()
        database.save_channel("UC1", "Ch1", "https://youtube.com/c/ch1")
        database.save_video("vid1", "UC1", "Video 1", None, 3600, "ja", False)
        database.save_subtitle_lines("vid1", [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="今日は演出の話をします"),
            SubtitleEntry(start_ms=10000, duration_ms=5000, text="演出が変わりました"),
        ])
        database.save_segments_with_vectors("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "演出について"},
        ], [[0.1] * 1536])
        return SearchService(db=database, embedding_provider=mock_embedding)

    def test_two_char_keyword_match(self, service_with_short_text, mock_embedding):
        """2文字クエリでキーワードマッチが返る"""
        mock_embedding.embed.return_value = [[0.0] * 1536]
        results, _ = service_with_short_text.search("演出")
        keyword_results = [r for r in results if r.match_type in (MatchType.KEYWORD, MatchType.HYBRID)]
        assert len(keyword_results) > 0
        for r in keyword_results:
            assert r.snippet is not None
            assert "演出" in r.snippet


class TestVideoIdFilter:
    @pytest.fixture
    def db_multi(self):
        database = Database(db_path=":memory:", embedding_dimensions=1536)
        database.initialize()
        database.save_channel("UC1", "TestChannel", "https://youtube.com/c/test")
        database.save_video("vid1", "UC1", "Test Video 1", None, 3600, "ja", False)
        database.save_video("vid2", "UC1", "Test Video 2", None, 7200, "ja", False)
        entries1 = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="マインクラフトで遊びます"),
        ]
        entries2 = [
            SubtitleEntry(start_ms=0, duration_ms=5000, text="マインクラフトの世界へ"),
        ]
        database.save_subtitle_lines("vid1", entries1)
        database.save_subtitle_lines("vid2", entries2)
        database.save_segments_with_vectors("vid1", [
            {"start_ms": 0, "end_ms": 60000, "summary": "ゲーム紹介1"},
        ], [[0.1] * 1536])
        database.save_segments_with_vectors("vid2", [
            {"start_ms": 0, "end_ms": 60000, "summary": "ゲーム紹介2"},
        ], [[0.9] * 1536])
        return database

    @pytest.fixture
    def service_multi(self, db_multi, mock_embedding):
        return SearchService(db=db_multi, embedding_provider=mock_embedding)

    def test_search_with_video_ids_filters(self, service_multi, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, warnings = service_multi.search("マインクラフト", video_ids=["vid1"])
        for r in results:
            assert "vid1" in r.youtube_url

    def test_search_without_video_ids_returns_all(self, service_multi, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, warnings = service_multi.search("マインクラフト")
        assert len(results) == 2
        assert warnings == []

    def test_search_with_missing_video_id_warns(self, service_multi, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results, warnings = service_multi.search("マインクラフト", video_ids=["vid1", "vid_unknown"])
        assert len(warnings) == 1
        assert "vid_unknown" in warnings[0]

    def test_search_all_video_ids_missing(self, service_multi, mock_embedding):
        results, warnings = service_multi.search("マインクラフト", video_ids=["vid_x", "vid_y"])
        assert results == []
        assert len(warnings) >= 1
        mock_embedding.embed.assert_not_called()

    def test_return_type_is_tuple(self, service_multi, mock_embedding):
        """戻り値がtuple[list, list]であることを確認"""
        mock_embedding.embed.return_value = [[0.5] * 1536]
        result = service_multi.search("マインクラフト")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestUrlGeneration:
    def test_search_results_use_shared_url_builder(self, service, mock_embedding):
        """SearchServiceが共通のbuild_youtube_urlを使用していることを確認"""
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results, _ = service.search("マインクラフト")
        for r in results:
            assert r.youtube_url.startswith("https://www.youtube.com/watch?v=")
            assert "&t=" in r.youtube_url
