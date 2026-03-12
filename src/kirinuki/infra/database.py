"""SQLite + FTS5 + sqlite-vec データベースアクセス層"""

import sqlite3
import struct
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import sqlite_vec

from kirinuki.models.domain import (
    Channel,
    ChannelSummary,
    Segment,
    SubtitleEntry,
    Video,
    VideoSummary,
)
from kirinuki.models.recommendation import SegmentRecommendation

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    title TEXT NOT NULL,
    published_at TEXT,
    duration_seconds INTEGER NOT NULL,
    subtitle_language TEXT NOT NULL,
    is_auto_subtitle INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL,
    broadcast_start_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);

CREATE TABLE IF NOT EXISTS subtitle_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    start_ms INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subtitle_lines_video ON subtitle_lines(video_id);

CREATE VIRTUAL TABLE IF NOT EXISTS subtitle_fts USING fts5(
    text,
    video_id UNINDEXED,
    start_ms UNINDEXED,
    duration_ms UNINDEXED,
    tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_segments_video ON segments(video_id);

CREATE TABLE IF NOT EXISTS unavailable_videos (
    video_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL REFERENCES channels(channel_id),
    error_type TEXT NOT NULL CHECK(error_type IN ('auth_required', 'unavailable')),
    reason TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unavailable_channel
    ON unavailable_videos(channel_id);
CREATE INDEX IF NOT EXISTS idx_unavailable_type
    ON unavailable_videos(channel_id, error_type);

CREATE TABLE IF NOT EXISTS segment_versions (
    video_id TEXT PRIMARY KEY REFERENCES videos(video_id),
    prompt_version TEXT NOT NULL,
    segmented_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segment_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    segment_id INTEGER NOT NULL REFERENCES segments(id),
    video_id TEXT NOT NULL REFERENCES videos(video_id),
    score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
    summary TEXT NOT NULL,
    appeal TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_recommendations_video_id
    ON segment_recommendations(video_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendations_segment_prompt
    ON segment_recommendations(segment_id, prompt_version);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);
"""


def _serialize_f32(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


class Database:
    def __init__(self, db_path: str | Path, embedding_dimensions: int = 1536) -> None:
        self._db_path = str(db_path)
        self._embedding_dimensions = embedding_dimensions
        self._conn: sqlite3.Connection | None = None
        self._in_transaction: bool = False

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """複数DB操作を単一トランザクションで包むコンテキストマネージャ。

        ブロック内の個別commit()はスキップされ、ブロック正常終了時にcommit、
        例外発生時にrollbackする。
        """
        assert self._conn is not None
        if self._in_transaction:
            yield
            return
        self._in_transaction = True
        try:
            yield
            self._conn.commit()
        except BaseException:
            self._conn.rollback()
            raise
        finally:
            self._in_transaction = False

    def _auto_commit(self) -> None:
        """トランザクション外なら即commit、トランザクション内ならスキップ。"""
        if not self._in_transaction:
            assert self._conn is not None
            self._conn.commit()

    def initialize(self) -> None:
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path)
        self._conn.enable_load_extension(True)
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")

        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA_SQL)

        # sqlite-vecベクトルテーブル
        self._conn.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS segment_vectors USING vec0(
                segment_id INTEGER PRIMARY KEY,
                embedding float[{self._embedding_dimensions}]
            )"""
        )

        # スキーマバージョン
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        elif row[0] < SCHEMA_VERSION:
            self._migrate_to_latest(row[0])

        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _migrate_to_latest(self, current_version: int) -> None:
        """現在のバージョンから最新バージョンまでマイグレーションを実行する。"""
        assert self._conn is not None
        if current_version < 2:
            self._migrate_v1_to_v2()

    def _migrate_v1_to_v2(self) -> None:
        """v1→v2: videos テーブルに broadcast_start_at カラムを追加する。"""
        assert self._conn is not None
        self._conn.execute("ALTER TABLE videos ADD COLUMN broadcast_start_at TEXT")
        self._conn.execute("UPDATE schema_version SET version = 2")

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None
        return self._conn.execute(sql, params)

    # --- Channel CRUD ---

    def save_channel(self, channel_id: str, name: str, url: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT OR IGNORE INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
            (channel_id, name, url),
        )
        self._auto_commit()

    def get_channel(self, channel_id: str) -> Channel | None:
        row = self._execute(
            "SELECT channel_id, name, url, last_synced_at FROM channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if row is None:
            return None
        return Channel(
            channel_id=row[0],
            name=row[1],
            url=row[2],
            last_synced_at=datetime.fromisoformat(row[3]) if row[3] else None,
        )

    def list_channels(self) -> list[ChannelSummary]:
        rows = self._execute(
            """SELECT c.channel_id, c.name, c.url, c.last_synced_at,
                      COUNT(v.video_id) as video_count
               FROM channels c
               LEFT JOIN videos v ON c.channel_id = v.channel_id
               GROUP BY c.channel_id"""
        ).fetchall()
        return [
            ChannelSummary(
                channel_id=row[0],
                name=row[1],
                url=row[2],
                last_synced_at=datetime.fromisoformat(row[3]) if row[3] else None,
                video_count=row[4],
            )
            for row in rows
        ]

    def update_channel_last_synced(self, channel_id: str, synced_at: datetime) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE channels SET last_synced_at = ? WHERE channel_id = ?",
            (synced_at.isoformat(), channel_id),
        )
        self._auto_commit()

    # --- Video CRUD ---

    def save_video(
        self,
        video_id: str,
        channel_id: str,
        title: str,
        published_at: datetime | None,
        duration_seconds: int,
        subtitle_language: str,
        is_auto_subtitle: bool,
        broadcast_start_at: datetime | None = None,
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """INSERT OR IGNORE INTO videos
               (video_id, channel_id, title, published_at, duration_seconds,
                subtitle_language, is_auto_subtitle, synced_at, broadcast_start_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                channel_id,
                title,
                published_at.isoformat() if published_at else None,
                duration_seconds,
                subtitle_language,
                int(is_auto_subtitle),
                datetime.now(tz=timezone.utc).isoformat(),
                broadcast_start_at.isoformat() if broadcast_start_at else None,
            ),
        )
        self._auto_commit()

    def get_video(self, video_id: str) -> Video | None:
        row = self._execute(
            """SELECT video_id, channel_id, title, published_at, duration_seconds,
                      subtitle_language, is_auto_subtitle, synced_at
               FROM videos WHERE video_id = ?""",
            (video_id,),
        ).fetchone()
        if row is None:
            return None
        return Video(
            video_id=row[0],
            channel_id=row[1],
            title=row[2],
            published_at=datetime.fromisoformat(row[3]) if row[3] else None,
            duration_seconds=row[4],
            subtitle_language=row[5],
            is_auto_subtitle=bool(row[6]),
            synced_at=datetime.fromisoformat(row[7]) if row[7] else None,
        )

    def get_existing_video_ids(self, channel_id: str) -> set[str]:
        rows = self._execute(
            "SELECT video_id FROM videos WHERE channel_id = ?",
            (channel_id,),
        ).fetchall()
        return {row[0] for row in rows}

    def get_unsegmented_video_ids(self, channel_id: str) -> list[str]:
        """セグメンテーション未完了の動画IDを返す。"""
        rows = self._execute(
            """SELECT v.video_id FROM videos v
               LEFT JOIN segments s ON v.video_id = s.video_id
               WHERE v.channel_id = ? AND s.id IS NULL""",
            (channel_id,),
        ).fetchall()
        return [row[0] for row in rows]

    def list_videos(self, channel_id: str) -> list[VideoSummary]:
        rows = self._execute(
            """SELECT video_id, title, published_at, duration_seconds
               FROM videos WHERE channel_id = ? ORDER BY published_at DESC""",
            (channel_id,),
        ).fetchall()
        return [
            VideoSummary(
                video_id=row[0],
                title=row[1],
                published_at=datetime.fromisoformat(row[2]) if row[2] else None,
                duration_seconds=row[3],
            )
            for row in rows
        ]

    # --- Subtitle CRUD ---

    def save_subtitle_lines(self, video_id: str, entries: list[SubtitleEntry]) -> None:
        assert self._conn is not None
        for entry in entries:
            self._conn.execute(
                "INSERT INTO subtitle_lines (video_id, start_ms, duration_ms, text) VALUES (?, ?, ?, ?)",
                (video_id, entry.start_ms, entry.duration_ms, entry.text),
            )
            self._conn.execute(
                "INSERT INTO subtitle_fts (text, video_id, start_ms, duration_ms) VALUES (?, ?, ?, ?)",
                (entry.text, video_id, entry.start_ms, entry.duration_ms),
            )
        self._auto_commit()

    def get_subtitle_entries(self, video_id: str) -> list[SubtitleEntry]:
        """DB保存済みの字幕行をSubtitleEntryリストとして返す。"""
        rows = self._execute(
            "SELECT start_ms, duration_ms, text FROM subtitle_lines WHERE video_id = ? ORDER BY start_ms",
            (video_id,),
        ).fetchall()
        return [
            SubtitleEntry(start_ms=row[0], duration_ms=row[1], text=row[2])
            for row in rows
        ]

    def fts_search(self, query: str, limit: int = 50) -> list[dict]:
        escaped_query = '"' + query.replace('"', '""') + '"'
        rows = self._execute(
            """SELECT video_id, start_ms, duration_ms, text
               FROM subtitle_fts WHERE subtitle_fts MATCH ?
               LIMIT ?""",
            (escaped_query, limit),
        ).fetchall()
        return [
            {"video_id": row[0], "start_ms": row[1], "duration_ms": row[2], "text": row[3]}
            for row in rows
        ]

    # --- Segment CRUD ---

    def delete_segments(self, video_id: str) -> int:
        """指定動画のセグメントとベクトルを削除する。削除したセグメント数を返す。"""
        assert self._conn is not None
        # segment_vectorsを先に削除（FK参照のため）
        self._conn.execute(
            "DELETE FROM segment_vectors WHERE segment_id IN "
            "(SELECT id FROM segments WHERE video_id = ?)",
            (video_id,),
        )
        self._conn.execute(
            "DELETE FROM segment_recommendations WHERE segment_id IN "
            "(SELECT id FROM segments WHERE video_id = ?)",
            (video_id,),
        )
        cursor = self._conn.execute(
            "DELETE FROM segments WHERE video_id = ?",
            (video_id,),
        )
        self._conn.execute(
            "DELETE FROM segment_versions WHERE video_id = ?",
            (video_id,),
        )
        self._auto_commit()
        return cursor.rowcount

    # --- Segment Version CRUD ---

    def save_segment_version(self, video_id: str, prompt_version: str) -> None:
        """セグメンテーション時のプロンプトバージョンを記録（upsert）"""
        assert self._conn is not None
        self._conn.execute(
            """INSERT INTO segment_versions (video_id, prompt_version, segmented_at)
               VALUES (?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                   prompt_version = excluded.prompt_version,
                   segmented_at = excluded.segmented_at""",
            (video_id, prompt_version, datetime.now(tz=timezone.utc).isoformat()),
        )
        self._auto_commit()

    def get_video_ids_with_segment_version(self, prompt_version: str) -> set[str]:
        """指定バージョンでセグメンテーション完了済みのvideo_idセットを返す"""
        rows = self._execute(
            "SELECT video_id FROM segment_versions WHERE prompt_version = ?",
            (prompt_version,),
        ).fetchall()
        return {row[0] for row in rows}

    def delete_segment_version(self, video_id: str) -> None:
        """セグメントバージョン記録を削除する"""
        assert self._conn is not None
        self._conn.execute(
            "DELETE FROM segment_versions WHERE video_id = ?",
            (video_id,),
        )
        self._auto_commit()

    def get_unsegmented_video_ids_all(self) -> list[str]:
        """字幕はあるがセグメントがない動画IDの一覧を返す。"""
        rows = self._execute(
            """SELECT DISTINCT sl.video_id FROM subtitle_lines sl
               LEFT JOIN segments s ON sl.video_id = s.video_id
               WHERE s.id IS NULL"""
        ).fetchall()
        return [row[0] for row in rows]

    def get_segmented_video_ids(self) -> list[str]:
        """セグメントが存在する動画IDの一覧を返す。"""
        rows = self._execute(
            "SELECT DISTINCT video_id FROM segments"
        ).fetchall()
        return [row[0] for row in rows]

    def get_resegment_target_video_ids(self) -> list[str]:
        """resegment対象の動画IDを公開日の新しい順に返す。

        字幕が存在する動画が対象（resegmentには字幕が必須のため）。
        """
        rows = self._execute(
            """SELECT v.video_id FROM videos v
               WHERE EXISTS (SELECT 1 FROM subtitle_lines sl WHERE sl.video_id = v.video_id)
               ORDER BY v.published_at IS NULL, v.published_at DESC"""
        ).fetchall()
        return [row[0] for row in rows]

    def save_segments(self, video_id: str, segments_data: list[dict]) -> list[int]:
        assert self._conn is not None
        ids = []
        for seg in segments_data:
            cursor = self._conn.execute(
                "INSERT INTO segments (video_id, start_ms, end_ms, summary) VALUES (?, ?, ?, ?)",
                (video_id, seg["start_ms"], seg["end_ms"], seg["summary"]),
            )
            ids.append(cursor.lastrowid or 0)
        self._auto_commit()
        return ids

    def save_segments_with_vectors(
        self,
        video_id: str,
        segments_data: list[dict],
        vectors: list[list[float]],
    ) -> None:
        assert self._conn is not None
        if len(segments_data) != len(vectors):
            raise ValueError(
                f"segments_data ({len(segments_data)}) と vectors ({len(vectors)}) の長さが一致しません"
            )
        with self.transaction():
            segment_ids = self.save_segments(video_id, segments_data)
            self._conn.executemany(
                "INSERT INTO segment_vectors (segment_id, embedding) VALUES (?, ?)",
                [(seg_id, _serialize_f32(vec)) for seg_id, vec in zip(segment_ids, vectors)],
            )

    def list_segments(self, video_id: str) -> list[Segment]:
        rows = self._execute(
            """SELECT id, video_id, start_ms, end_ms, summary
               FROM segments WHERE video_id = ? ORDER BY start_ms""",
            (video_id,),
        ).fetchall()
        return [
            Segment(id=row[0], video_id=row[1], start_ms=row[2], end_ms=row[3], summary=row[4])
            for row in rows
        ]

    def vector_search(
        self, query_vector: list[float], limit: int = 10, video_ids: list[str] | None = None,
    ) -> list[dict]:
        fetch_limit = limit * 5 if video_ids else limit
        rows = self._execute(
            """SELECT sv.segment_id, sv.distance,
                      s.video_id, s.start_ms, s.end_ms, s.summary,
                      v.title, c.name as channel_name
               FROM segment_vectors sv
               JOIN segments s ON sv.segment_id = s.id
               JOIN videos v ON s.video_id = v.video_id
               JOIN channels c ON v.channel_id = c.channel_id
               WHERE embedding MATCH ? AND k = ?
               ORDER BY sv.distance""",
            (_serialize_f32(query_vector), fetch_limit),
        ).fetchall()
        results = [
            {
                "segment_id": row[0],
                "distance": row[1],
                "video_id": row[2],
                "start_ms": row[3],
                "end_ms": row[4],
                "summary": row[5],
                "video_title": row[6],
                "channel_name": row[7],
            }
            for row in rows
        ]
        if video_ids:
            video_id_set = set(video_ids)
            results = [r for r in results if r["video_id"] in video_id_set]
            results = results[:limit]
        return results

    # --- Unavailable Videos CRUD ---

    def save_unavailable_video(
        self, video_id: str, channel_id: str, error_type: str, reason: str
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """INSERT INTO unavailable_videos (video_id, channel_id, error_type, reason, recorded_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(video_id) DO UPDATE SET
                   error_type = excluded.error_type,
                   reason = excluded.reason,
                   recorded_at = excluded.recorded_at""",
            (video_id, channel_id, error_type, reason, datetime.now(tz=timezone.utc).isoformat()),
        )
        self._auto_commit()

    def get_unavailable_video_ids(self, channel_id: str) -> set[str]:
        rows = self._execute(
            "SELECT video_id FROM unavailable_videos WHERE channel_id = ?",
            (channel_id,),
        ).fetchall()
        return {row[0] for row in rows}

    def get_auth_unavailable_recorded_at(self, channel_id: str) -> datetime | None:
        row = self._execute(
            """SELECT MIN(recorded_at) FROM unavailable_videos
               WHERE channel_id = ? AND error_type = 'auth_required'""",
            (channel_id,),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return datetime.fromisoformat(row[0])

    def clear_unavailable_by_type(self, channel_id: str, error_type: str) -> int:
        assert self._conn is not None
        cursor = self._conn.execute(
            "DELETE FROM unavailable_videos WHERE channel_id = ? AND error_type = ?",
            (channel_id, error_type),
        )
        self._auto_commit()
        return cursor.rowcount

    def clear_all_unavailable(self, channel_id: str | None = None) -> int:
        assert self._conn is not None
        if channel_id is not None:
            cursor = self._conn.execute(
                "DELETE FROM unavailable_videos WHERE channel_id = ?",
                (channel_id,),
            )
        else:
            cursor = self._conn.execute("DELETE FROM unavailable_videos")
        self._auto_commit()
        return cursor.rowcount

    def validate_video_ids(self, video_ids: list[str]) -> tuple[list[str], list[str]]:
        """video_idsの存在確認を行う。

        Returns:
            tuple of (存在するID, 存在しないID)
        """
        if not video_ids:
            return [], []
        placeholders = ",".join("?" for _ in video_ids)
        rows = self._execute(
            f"SELECT video_id FROM videos WHERE video_id IN ({placeholders})",
            tuple(video_ids),
        ).fetchall()
        existing_set = {row[0] for row in rows}
        existing = [vid for vid in video_ids if vid in existing_set]
        missing = [vid for vid in video_ids if vid not in existing_set]
        return existing, missing

    def fts_search_segments(
        self, query: str, limit: int = 50, video_ids: list[str] | None = None,
    ) -> list[dict]:
        """FTS検索結果から関連するセグメントを特定して返す"""
        escaped_query = '"' + query.replace('"', '""') + '"'
        params: list = [escaped_query]
        video_filter = ""
        if video_ids:
            placeholders = ",".join("?" for _ in video_ids)
            video_filter = f" AND s.video_id IN ({placeholders})"
            params.extend(video_ids)
        params.append(limit)
        rows = self._execute(
            f"""SELECT s.id, s.video_id, s.start_ms, s.end_ms, s.summary,
                      v.title, c.name as channel_name,
                      GROUP_CONCAT(f.text, '…') as snippet
               FROM subtitle_fts f
               JOIN segments s ON f.video_id = s.video_id
                   AND CAST(f.start_ms AS INTEGER) >= s.start_ms
                   AND CAST(f.start_ms AS INTEGER) < s.end_ms
               JOIN videos v ON s.video_id = v.video_id
               JOIN channels c ON v.channel_id = c.channel_id
               WHERE subtitle_fts MATCH ?{video_filter}
               GROUP BY s.id, s.video_id, s.start_ms, s.end_ms, s.summary,
                        v.title, c.name
               LIMIT ?""",
            tuple(params),
        ).fetchall()
        return [
            {
                "segment_id": row[0],
                "video_id": row[1],
                "start_ms": row[2],
                "end_ms": row[3],
                "summary": row[4],
                "video_title": row[5],
                "channel_name": row[6],
                "snippet": row[7] or "",
            }
            for row in rows
        ]

    # --- Suggest 機能用メソッド ---

    def get_latest_videos(
        self, channel_id: str, count: int, until: datetime | None = None,
    ) -> list[dict[str, str]]:
        """チャンネルの最新N件のアーカイブを配信日時降順で取得する"""
        if until is not None:
            until_str = until.strftime("%Y-%m-%dT%H:%M:%S")
            rows = self._execute(
                """SELECT video_id, title, published_at, duration_seconds
                   FROM videos
                   WHERE channel_id = ?
                     AND (substr(broadcast_start_at, 1, 19) <= ?
                          OR (broadcast_start_at IS NULL AND substr(published_at, 1, 19) <= ?))
                   ORDER BY COALESCE(broadcast_start_at, published_at) DESC
                   LIMIT ?""",
                (channel_id, until_str, until_str, count),
            ).fetchall()
        else:
            rows = self._execute(
                """SELECT video_id, title, published_at, duration_seconds
                   FROM videos
                   WHERE channel_id = ?
                   ORDER BY COALESCE(broadcast_start_at, published_at) DESC
                   LIMIT ?""",
                (channel_id, count),
            ).fetchall()
        return [
            {
                "video_id": row[0],
                "title": row[1],
                "published_at": row[2],
                "duration_seconds": row[3],
            }
            for row in rows
        ]

    def get_videos_by_ids(self, video_ids: list[str]) -> list[dict[str, str]]:
        """指定された動画IDの情報を取得する。存在しないIDは結果に含まれない。"""
        placeholders = ",".join("?" for _ in video_ids)
        rows = self._execute(
            f"""SELECT video_id, title, published_at, duration_seconds
                FROM videos
                WHERE video_id IN ({placeholders})
                ORDER BY published_at DESC""",
            tuple(video_ids),
        ).fetchall()
        return [
            {
                "video_id": row[0],
                "title": row[1],
                "published_at": row[2],
                "duration_seconds": row[3],
            }
            for row in rows
        ]

    def get_segments_for_video(self, video_id: str) -> list[dict[str, str | int]]:
        """動画のセグメント一覧をdict形式で取得する"""
        rows = self._execute(
            """SELECT id, video_id, start_ms, end_ms, summary
               FROM segments
               WHERE video_id = ?
               ORDER BY start_ms""",
            (video_id,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "video_id": row[1],
                "start_ms": row[2],
                "end_ms": row[3],
                "summary": row[4],
            }
            for row in rows
        ]

    def get_cached_recommendations(
        self, video_id: str, prompt_version: str
    ) -> list[SegmentRecommendation] | None:
        """キャッシュ済み推薦結果を取得。なければNone"""
        rows = self._execute(
            """SELECT sr.segment_id, sr.video_id, sr.score, sr.summary, sr.appeal,
                      sr.prompt_version, s.start_ms, s.end_ms
               FROM segment_recommendations sr
               JOIN segments s ON sr.segment_id = s.id
               WHERE sr.video_id = ? AND sr.prompt_version = ?""",
            (video_id, prompt_version),
        ).fetchall()
        if not rows:
            return None
        return [
            SegmentRecommendation(
                segment_id=row[0],
                video_id=row[1],
                start_time=row[6] / 1000.0,
                end_time=row[7] / 1000.0,
                score=row[2],
                summary=row[3],
                appeal=row[4],
                prompt_version=row[5],
            )
            for row in rows
        ]

    def save_recommendations(self, recommendations: list[SegmentRecommendation]) -> None:
        """推薦結果をDBに保存する（UPSERT）"""
        assert self._conn is not None
        self._conn.executemany(
            """INSERT INTO segment_recommendations
                (segment_id, video_id, score, summary, appeal, prompt_version)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id, prompt_version)
            DO UPDATE SET score=excluded.score, summary=excluded.summary,
                          appeal=excluded.appeal, created_at=CURRENT_TIMESTAMP""",
            [
                (rec.segment_id, rec.video_id, rec.score, rec.summary, rec.appeal, rec.prompt_version)
                for rec in recommendations
            ],
        )
        self._auto_commit()

    def get_videos_without_broadcast_start(self) -> list[dict[str, str]]:
        """broadcast_start_at が未設定の動画一覧を返す"""
        rows = self._execute(
            """SELECT video_id, title, published_at, duration_seconds
               FROM videos
               WHERE broadcast_start_at IS NULL"""
        ).fetchall()
        return [
            {
                "video_id": row[0],
                "title": row[1],
                "published_at": row[2],
                "duration_seconds": row[3],
            }
            for row in rows
        ]

    def update_broadcast_start_at(
        self, video_id: str, broadcast_start_at: datetime
    ) -> None:
        """動画の broadcast_start_at を更新する"""
        assert self._conn is not None
        self._conn.execute(
            "UPDATE videos SET broadcast_start_at = ? WHERE video_id = ?",
            (broadcast_start_at.isoformat(), video_id),
        )
        self._auto_commit()

    def channel_exists(self, channel_id: str) -> bool:
        """チャンネルが登録済みかどうか"""
        row = self._execute(
            "SELECT 1 FROM channels WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return row is not None
