"""LLMによる話題セグメンテーションサービス"""

import logging
import time

from kirinuki.infra.database import Database
from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.infra.llm_client import SEGMENT_PROMPT_VERSION, LlmClient
from kirinuki.models.domain import Segment, SubtitleEntry, TopicSegment

logger = logging.getLogger(__name__)

CHUNK_MINUTES = 20
OVERLAP_MINUTES = 3
MAX_CHARS_SINGLE_CALL = 80_000


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
        self,
        video_id: str,
        entries: list[SubtitleEntry],
        duration_seconds: int,
        max_segment_ms: int = 300_000,
        *,
        replace: bool = False,
    ) -> list[Segment]:
        """字幕エントリーから話題セグメンテーションを実行する（長時間配信のチャンク分割対応）"""
        if not entries:
            return []

        # テキストサイズまたは動画長でチャンク分割を判定
        t_text = time.perf_counter()
        text = self._build_subtitle_text(entries)
        text_len = len(text)
        t_build = time.perf_counter()
        logger.info("build_subtitle_text: %.2fs (%d chars)", t_build - t_text, text_len)

        if duration_seconds > 4 * 3600 or text_len > MAX_CHARS_SINGLE_CALL:
            logger.info(
                "Using chunk mode: duration=%ds, text_len=%d (threshold=%d)",
                duration_seconds, text_len, MAX_CHARS_SINGLE_CALL,
            )
            chunks = self._chunk_entries(entries, CHUNK_MINUTES, OVERLAP_MINUTES)
            all_segments: list[TopicSegment] = []
            for i, chunk in enumerate(chunks):
                t_chunk = time.perf_counter()
                chunk_text = self._build_subtitle_text(chunk)
                segs = self._llm.analyze_topics(chunk_text)
                t_chunk_done = time.perf_counter()
                logger.info(
                    "chunk %d/%d: %d entries, %d chars, %d segments, %.2fs",
                    i + 1, len(chunks), len(chunk), len(chunk_text),
                    len(segs), t_chunk_done - t_chunk,
                )
                all_segments.extend(segs)
            # 重複排除（オーバーラップ区間）
            segments_raw = self._deduplicate_segments(all_segments)
        else:
            t_api = time.perf_counter()
            segments_raw = self._llm.analyze_topics(text)
            t_done = time.perf_counter()
            logger.info("analyze_topics API call: %.2fs", t_done - t_api)

        if not segments_raw:
            return []

        # セグメント境界を最寄りの字幕エントリーにスナップ
        segments_raw = self._snap_to_entries(segments_raw, entries)

        # 長すぎるセグメントの再分割
        segments_raw = self._resplit_oversized(segments_raw, entries, max_segment_ms)

        summaries = [s.summary for s in segments_raw]
        vectors = self._embedding.embed(summaries)

        segments_data = [
            {"start_ms": s.start_ms, "end_ms": s.end_ms, "summary": s.summary}
            for s in segments_raw
        ]
        if replace:
            self._db.delete_segments(video_id)
        self._db.save_segments_with_vectors(video_id, segments_data, vectors)
        self._db.save_segment_version(video_id, SEGMENT_PROMPT_VERSION)

        return self._db.list_segments(video_id)

    def list_segments(self, video_id: str) -> list[Segment]:
        return self._db.list_segments(video_id)

    def resegment_video(self, video_id: str, max_segment_ms: int = 300_000) -> list[Segment]:
        """既存セグメントを削除して再セグメンテーションを実行する。"""
        t0 = time.perf_counter()
        entries = self._db.get_subtitle_entries(video_id)
        t1 = time.perf_counter()
        logger.info("get_subtitle_entries: %.2fs (%d entries)", t1 - t0, len(entries))
        if not entries:
            return []
        video = self._db.get_video(video_id)
        t2 = time.perf_counter()
        logger.info("get_video: %.2fs", t2 - t1)
        if video is None:
            return []
        result = self.segment_video_from_entries(
            video_id, entries, video.duration_seconds,
            max_segment_ms=max_segment_ms, replace=True,
        )
        t3 = time.perf_counter()
        logger.info("segment_video_from_entries: %.2fs", t3 - t2)
        return result

    def _snap_to_entries(
        self,
        segments: list[TopicSegment],
        entries: list[SubtitleEntry],
    ) -> list[TopicSegment]:
        """各セグメントの境界を最寄りの字幕エントリーにスナップする。"""
        if not segments or not entries:
            return segments

        entry_starts = [e.start_ms for e in entries]
        last_entry_end = entries[-1].start_ms + entries[-1].duration_ms

        def _nearest_entry_start(target_ms: int) -> int:
            best = entry_starts[0]
            best_dist = abs(target_ms - best)
            for s in entry_starts:
                d = abs(target_ms - s)
                if d < best_dist:
                    best = s
                    best_dist = d
            return best

        # 各セグメントの start_ms を最寄りの字幕エントリーにスナップ
        snapped: list[TopicSegment] = []
        for seg in segments:
            snapped_start = _nearest_entry_start(seg.start_ms)
            snapped.append(TopicSegment(start_ms=snapped_start, end_ms=seg.end_ms, summary=seg.summary))

        # end_ms を次セグメントの start_ms から導出
        for i in range(len(snapped) - 1):
            snapped[i] = TopicSegment(
                start_ms=snapped[i].start_ms,
                end_ms=snapped[i + 1].start_ms,
                summary=snapped[i].summary,
            )
        # 最後のセグメントは最終字幕エントリーの終端
        snapped[-1] = TopicSegment(
            start_ms=snapped[-1].start_ms,
            end_ms=last_entry_end,
            summary=snapped[-1].summary,
        )

        return snapped

    def _resplit_oversized(
        self,
        segments: list[TopicSegment],
        entries: list[SubtitleEntry],
        max_segment_ms: int,
    ) -> list[TopicSegment]:
        """max_segment_ms超のセグメントを再分割する（1パスのみ）。"""
        result: list[TopicSegment] = []
        for seg in segments:
            duration = seg.end_ms - seg.start_ms
            if duration <= max_segment_ms:
                result.append(seg)
                continue

            # 該当セグメントの時間範囲のSubtitleEntryを抽出
            seg_entries = [
                e for e in entries if e.start_ms >= seg.start_ms and e.start_ms < seg.end_ms
            ]
            if not seg_entries:
                result.append(seg)
                continue

            text = self._build_subtitle_text(seg_entries)
            try:
                sub_segments = self._llm.analyze_topics_resplit(text, seg.summary)
            except Exception:
                logger.warning("Resplit failed for segment %s, keeping original", seg.summary)
                result.append(seg)
                continue

            # 2つ以上に分割できた場合のみ採用
            if len(sub_segments) >= 2:
                sub_segments = self._snap_to_entries(sub_segments, seg_entries)
                result.extend(sub_segments)
            else:
                result.append(seg)

        return result

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
