"""SQLite + FTS5 + sqlite-vec データベースアクセス層"""

import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec

from kirinuki.models.domain import (
    Channel,
    ChannelSummary,
    Segment,
    SubtitleEntry,
    Video,
    VideoSummary,
)

SCHEMA_VERSION = 1

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
    synced_at TEXT NOT NULL
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

        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

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
        self._conn.commit()

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
        self._conn.commit()

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
    ) -> None:
        assert self._conn is not None
        self._conn.execute(
            """INSERT OR IGNORE INTO videos
               (video_id, channel_id, title, published_at, duration_seconds,
                subtitle_language, is_auto_subtitle, synced_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                video_id,
                channel_id,
                title,
                published_at.isoformat() if published_at else None,
                duration_seconds,
                subtitle_language,
                int(is_auto_subtitle),
                datetime.now(tz=timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

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
        self._conn.commit()

    def fts_search(self, query: str, limit: int = 50) -> list[dict]:
        rows = self._execute(
            """SELECT video_id, start_ms, duration_ms, text
               FROM subtitle_fts WHERE subtitle_fts MATCH ?
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [
            {"video_id": row[0], "start_ms": row[1], "duration_ms": row[2], "text": row[3]}
            for row in rows
        ]

    # --- Segment CRUD ---

    def save_segments(self, video_id: str, segments_data: list[dict]) -> list[int]:
        assert self._conn is not None
        ids = []
        for seg in segments_data:
            cursor = self._conn.execute(
                "INSERT INTO segments (video_id, start_ms, end_ms, summary) VALUES (?, ?, ?, ?)",
                (video_id, seg["start_ms"], seg["end_ms"], seg["summary"]),
            )
            ids.append(cursor.lastrowid or 0)
        self._conn.commit()
        return ids

    def save_segments_with_vectors(
        self,
        video_id: str,
        segments_data: list[dict],
        vectors: list[list[float]],
    ) -> None:
        assert self._conn is not None
        segment_ids = self.save_segments(video_id, segments_data)
        for seg_id, vec in zip(segment_ids, vectors):
            self._conn.execute(
                "INSERT INTO segment_vectors (segment_id, embedding) VALUES (?, ?)",
                (seg_id, _serialize_f32(vec)),
            )
        self._conn.commit()

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

    def vector_search(self, query_vector: list[float], limit: int = 10) -> list[dict]:
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
            (_serialize_f32(query_vector), limit),
        ).fetchall()
        return [
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
        self._conn.commit()

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
        self._conn.commit()
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
        self._conn.commit()
        return cursor.rowcount

    def fts_search_segments(self, query: str, limit: int = 50) -> list[dict]:
        """FTS検索結果から関連するセグメントを特定して返す"""
        rows = self._execute(
            """SELECT DISTINCT s.id, s.video_id, s.start_ms, s.end_ms, s.summary,
                      v.title, c.name as channel_name
               FROM subtitle_fts f
               JOIN segments s ON f.video_id = s.video_id
                   AND CAST(f.start_ms AS INTEGER) >= s.start_ms
                   AND CAST(f.start_ms AS INTEGER) < s.end_ms
               JOIN videos v ON s.video_id = v.video_id
               JOIN channels c ON v.channel_id = c.channel_id
               WHERE subtitle_fts MATCH ?
               LIMIT ?""",
            (query, limit),
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
            }
            for row in rows
        ]
