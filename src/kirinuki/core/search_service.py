"""ハイブリッド横断検索サービス"""

import logging

from kirinuki.core.clip_utils import build_youtube_url
from kirinuki.infra.database import Database
from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.models.domain import SearchResult

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self, db: Database, embedding_provider: OpenAIEmbeddingProvider) -> None:
        self._db = db
        self._embedding = embedding_provider

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        # キーワード検索（FTS5 trigram: 3文字以上必要）
        fts_results = []
        if len(query) >= 3:
            fts_results = self._db.fts_search_segments(query, limit=limit * 2)

        # ベクトル意味検索
        query_vector = self._embedding.embed([query])[0]
        vec_results = self._db.vector_search(query_vector, limit=limit * 2)

        # マージ・重複排除・スコアリング
        merged = self._merge_results(fts_results, vec_results, limit)
        return merged

    def _merge_results(
        self,
        fts_results: list[dict],
        vec_results: list[dict],
        limit: int,
    ) -> list[SearchResult]:
        seen_segment_ids: set[int] = set()
        scored: list[tuple[float, dict]] = []

        # FTS結果にスコア付与
        for i, r in enumerate(fts_results):
            seg_id = r["segment_id"]
            if seg_id not in seen_segment_ids:
                seen_segment_ids.add(seg_id)
                fts_score = 1.0 - (i / max(len(fts_results), 1))
                scored.append((fts_score, r))

        # ベクトル検索結果にスコア付与
        for i, r in enumerate(vec_results):
            seg_id = r["segment_id"]
            distance = r.get("distance", 1.0)
            vec_score = max(0.0, 1.0 - distance)
            if seg_id in seen_segment_ids:
                # 既にFTSで見つかっている場合はスコアをブースト
                for j, (s, existing) in enumerate(scored):
                    if existing["segment_id"] == seg_id:
                        scored[j] = (s + vec_score * 0.5, existing)
                        break
            else:
                seen_segment_ids.add(seg_id)
                scored.append((vec_score, r))

        # スコア順にソート
        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, r in scored[:limit]:
            video_id = r["video_id"]
            start_ms = r["start_ms"]
            results.append(
                SearchResult(
                    video_title=r.get("video_title", ""),
                    channel_name=r.get("channel_name", ""),
                    start_time_ms=start_ms,
                    end_time_ms=r["end_ms"],
                    summary=r["summary"],
                    youtube_url=build_youtube_url(video_id, start_ms),
                    score=round(score, 4),
                )
            )
        return results

