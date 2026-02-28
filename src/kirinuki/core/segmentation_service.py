"""LLMによる話題セグメンテーションサービス"""

import logging

from kirinuki.infra.database import Database
from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.infra.llm_client import LlmClient
from kirinuki.models.domain import Segment, SubtitleEntry, TopicSegment

logger = logging.getLogger(__name__)

CHUNK_MINUTES = 45
OVERLAP_MINUTES = 5


class SegmentationService:
    def __init__(
        self,
        db: Database,
        llm_client: LlmClient,
        embedding_provider: OpenAIEmbeddingProvider,
    ) -> None:
        self._db = db
        self._llm = llm_client
        self._embedding = embedding_provider

    def segment_video(self, video_id: str, subtitle_text: str) -> list[Segment]:
        if not subtitle_text.strip():
            return []

        segments_raw = self._llm.analyze_topics(subtitle_text)
        if not segments_raw:
            return []

        summaries = [s.summary for s in segments_raw]
        vectors = self._embedding.embed(summaries)

        segments_data = [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "summary": s.summary}
            for s in segments_raw
        ]
        self._db.save_segments_with_vectors(video_id, segments_data, vectors)

        return self._db.list_segments(video_id)

    def segment_video_from_entries(
        self, video_id: str, entries: list[SubtitleEntry], duration_seconds: int
    ) -> list[Segment]:
        """字幕エントリーから話題セグメンテーションを実行する（長時間配信のチャンク分割対応）"""
        if not entries:
            return []

        # 4時間超はチャンク分割
        if duration_seconds > 4 * 3600:
            chunks = self._chunk_entries(entries, CHUNK_MINUTES, OVERLAP_MINUTES)
            all_segments: list[TopicSegment] = []
            for chunk in chunks:
                text = self._build_subtitle_text(chunk)
                segs = self._llm.analyze_topics(text)
                all_segments.extend(segs)
            # 重複排除（オーバーラップ区間）
            segments_raw = self._deduplicate_segments(all_segments)
        else:
            text = self._build_subtitle_text(entries)
            segments_raw = self._llm.analyze_topics(text)

        if not segments_raw:
            return []

        summaries = [s.summary for s in segments_raw]
        vectors = self._embedding.embed(summaries)

        segments_data = [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "summary": s.summary}
            for s in segments_raw
        ]
        self._db.save_segments_with_vectors(video_id, segments_data, vectors)

        return self._db.list_segments(video_id)

    def list_segments(self, video_id: str) -> list[Segment]:
        return self._db.list_segments(video_id)

    def _build_subtitle_text(self, entries: list[SubtitleEntry]) -> str:
        lines = []
        for entry in entries:
            total_seconds = entry.start_ms // 1000
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            lines.append(f"[{minutes:02d}:{seconds:02d}] {entry.text}")
        return "\n".join(lines)

    def _chunk_entries(
        self,
        entries: list[SubtitleEntry],
        chunk_minutes: int = CHUNK_MINUTES,
        overlap_minutes: int = OVERLAP_MINUTES,
    ) -> list[list[SubtitleEntry]]:
        chunk_ms = chunk_minutes * 60 * 1000
        overlap_ms = overlap_minutes * 60 * 1000
        step_ms = chunk_ms - overlap_ms

        chunks: list[list[SubtitleEntry]] = []
        start_ms = 0

        while True:
            end_ms = start_ms + chunk_ms
            chunk = [e for e in entries if e.start_ms >= start_ms and e.start_ms < end_ms]
            if not chunk:
                break
            chunks.append(chunk)
            start_ms += step_ms
            if start_ms >= entries[-1].start_ms:
                break

        return chunks

    def _deduplicate_segments(self, segments: list[TopicSegment]) -> list[TopicSegment]:
        if not segments:
            return []
        segments.sort(key=lambda s: s.start_ms)
        deduped: list[TopicSegment] = [segments[0]]
        for seg in segments[1:]:
            last = deduped[-1]
            # 前のセグメントと大きく重複する場合はスキップ
            overlap = max(0, last.end_ms - seg.start_ms)
            seg_duration = seg.end_ms - seg.start_ms
            if seg_duration > 0 and overlap / seg_duration > 0.5:
                continue
            deduped.append(seg)
        return deduped
