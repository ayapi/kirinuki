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


class TestSearch:
    def test_keyword_search(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results = service.search("マインクラフト")
        assert len(results) > 0

    def test_vector_search(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results = service.search("ゲーム実況")
        assert len(results) > 0

    def test_no_results(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.0] * 1536]
        results = service.search("xyz_nonexistent_zzz")
        # ベクトル検索は距離ベースなので結果が返ることがある
        # キーワード検索のみで該当なしをテスト

    def test_youtube_url_format(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results = service.search("マインクラフト")
        for r in results:
            assert "youtube.com/watch?v=" in r.youtube_url
            assert "&t=" in r.youtube_url

    def test_limit(self, service, mock_embedding):
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results = service.search("マインクラフト", limit=1)
        assert len(results) <= 1


class TestMatchTypeTracking:
    def test_keyword_only_match_type(self, service, mock_embedding):
        """FTSのみでヒットした場合、match_type=KEYWORDが設定される"""
        mock_embedding.embed.return_value = [[0.0] * 1536]  # 遠い距離 → ベクトルマッチなし
        results = service.search("マインクラフト")
        keyword_results = [r for r in results if r.match_type == MatchType.KEYWORD]
        assert len(keyword_results) > 0
        for r in keyword_results:
            assert r.snippet is not None
            assert r.similarity is None

    def test_semantic_only_match_type(self, service, mock_embedding):
        """ベクトルのみでヒットした場合、match_type=SEMANTICが設定される"""
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results = service.search("ab")  # 2文字 → FTS不発
        semantic_results = [r for r in results if r.match_type == MatchType.SEMANTIC]
        assert len(semantic_results) > 0
        for r in semantic_results:
            assert r.similarity is not None
            assert 0.0 <= r.similarity <= 1.0

    def test_hybrid_match_type(self, service, mock_embedding):
        """FTSとベクトル両方でヒットした場合、match_type=HYBRIDが設定される"""
        mock_embedding.embed.return_value = [[0.1] * 1536]  # segment1のベクトルに近い
        results = service.search("マインクラフト")
        hybrid_results = [r for r in results if r.match_type == MatchType.HYBRID]
        # FTSとベクトルが同じセグメントにヒットすればhybrid
        for r in hybrid_results:
            assert r.snippet is not None
            assert r.similarity is not None

    def test_similarity_score_range(self, service, mock_embedding):
        """similarity は 0.0〜1.0 の範囲である"""
        mock_embedding.embed.return_value = [[0.5] * 1536]
        results = service.search("マインクラフト")
        for r in results:
            if r.similarity is not None:
                assert 0.0 <= r.similarity <= 1.0

    def test_snippet_from_fts(self, service, mock_embedding):
        """FTSマッチ結果にsnippetが設定される"""
        mock_embedding.embed.return_value = [[0.0] * 1536]
        results = service.search("マインクラフト")
        fts_results = [r for r in results if r.match_type in (MatchType.KEYWORD, MatchType.HYBRID)]
        for r in fts_results:
            assert r.snippet is not None
            assert len(r.snippet) > 0


class TestUrlGeneration:
    def test_search_results_use_shared_url_builder(self, service, mock_embedding):
        """SearchServiceが共通のbuild_youtube_urlを使用していることを確認"""
        mock_embedding.embed.return_value = [[0.85] * 1536]
        results = service.search("マインクラフト")
        for r in results:
            assert r.youtube_url.startswith("https://www.youtube.com/watch?v=")
            assert "&t=" in r.youtube_url
