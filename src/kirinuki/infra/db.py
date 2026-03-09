"""SQLiteデータベースクライアント"""

import sqlite3
from pathlib import Path

from kirinuki.models.domain import ChannelSummary
from kirinuki.models.recommendation import SegmentRecommendation


class DatabaseClient:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                last_synced_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT,
                duration_seconds INTEGER NOT NULL,
                subtitle_language TEXT NOT NULL,
                is_auto_subtitle INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subtitles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                text TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                summary TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS segment_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 10),
                summary TEXT NOT NULL,
                appeal TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (segment_id) REFERENCES segments(id),
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            )
        """)

        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_recommendations_video_id
            ON segment_recommendations(video_id)
        """)

        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_recommendations_segment_prompt
            ON segment_recommendations(segment_id, prompt_version)
        """)

        conn.commit()
        conn.close()

    def list_channels(self) -> list[ChannelSummary]:
        """登録チャンネル一覧を取得する"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT c.channel_id, c.name, c.url, c.last_synced_at,
                   COUNT(v.video_id) as video_count
            FROM channels c
            LEFT JOIN videos v ON c.channel_id = v.channel_id
            GROUP BY c.channel_id
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            ChannelSummary(
                channel_id=row["channel_id"],
                name=row["name"],
                url=row["url"],
                video_count=row["video_count"],
                last_synced_at=row["last_synced_at"],
            )
            for row in rows
        ]

    def get_latest_videos(self, channel_id: str, count: int) -> list[dict[str, str]]:
        """チャンネルの最新N件のアーカイブを配信日時降順で取得する"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT video_id, title, published_at, duration_seconds
            FROM videos
            WHERE channel_id = ?
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (channel_id, count),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_videos_by_ids(self, video_ids: list[str]) -> list[dict[str, str]]:
        """指定された動画IDの情報を取得する。存在しないIDは結果に含まれない。"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in video_ids)
        cursor = conn.execute(
            f"""
            SELECT video_id, title, published_at, duration_seconds
            FROM videos
            WHERE video_id IN ({placeholders})
            ORDER BY published_at DESC
            """,
            video_ids,
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_segments_for_video(self, video_id: str) -> list[dict[str, str | int]]:
        """動画のセグメント一覧を取得する"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT id, video_id, start_ms, end_ms, summary
            FROM segments
            WHERE video_id = ?
            ORDER BY start_ms
            """,
            (video_id,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_cached_recommendations(
        self, video_id: str, prompt_version: str
    ) -> list[SegmentRecommendation] | None:
        """キャッシュ済み推薦結果を取得。なければNone"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT sr.segment_id, sr.video_id, sr.score, sr.summary, sr.appeal,
                   sr.prompt_version, s.start_ms, s.end_ms
            FROM segment_recommendations sr
            JOIN segments s ON sr.segment_id = s.id
            WHERE sr.video_id = ? AND sr.prompt_version = ?
            """,
            (video_id, prompt_version),
        )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return None
        return [
            SegmentRecommendation(
                segment_id=row["segment_id"],
                video_id=row["video_id"],
                start_time=row["start_ms"] / 1000.0,
                end_time=row["end_ms"] / 1000.0,
                score=row["score"],
                summary=row["summary"],
                appeal=row["appeal"],
                prompt_version=row["prompt_version"],
            )
            for row in rows
        ]

    def save_recommendations(self, recommendations: list[SegmentRecommendation]) -> None:
        """推薦結果をDBに保存する（UPSERT）"""
        conn = sqlite3.connect(str(self.db_path))
        for rec in recommendations:
            conn.execute(
                """
                INSERT INTO segment_recommendations
                    (segment_id, video_id, score, summary, appeal, prompt_version)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(segment_id, prompt_version)
                DO UPDATE SET score=excluded.score, summary=excluded.summary,
                              appeal=excluded.appeal, created_at=CURRENT_TIMESTAMP
                """,
                (rec.segment_id, rec.video_id, rec.score, rec.summary, rec.appeal, rec.prompt_version),
            )
        conn.commit()
        conn.close()

    def channel_exists(self, channel_id: str) -> bool:
        """チャンネルが登録済みかどうか"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "SELECT 1 FROM channels WHERE channel_id = ?", (channel_id,)
        )
        result = cursor.fetchone() is not None
        conn.close()
        return result
