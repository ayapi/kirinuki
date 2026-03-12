"""migrate サブコマンドのテスト"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.infra.database import Database
from kirinuki.infra.ytdlp_client import VideoMeta


def _setup_db_for_backfill(tmp_path: Path) -> Path:
    """バックフィルテスト用DBを準備する"""
    db_path = tmp_path / "test.db"
    db = Database(db_path=db_path, embedding_dimensions=1536)
    db.initialize()
    db.save_channel("UC1", "テストチャンネル", "https://youtube.com/c/test")
    # broadcast_start_at=NULL の動画を2つ追加
    db.save_video(
        "vid1", "UC1", "Video 1",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
    )
    db.save_video(
        "vid2", "UC1", "Video 2",
        published_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
        duration_seconds=7200, subtitle_language="ja", is_auto_subtitle=False,
    )
    # broadcast_start_at設定済みの動画を1つ
    db.save_video(
        "vid3", "UC1", "Video 3",
        published_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        duration_seconds=5400, subtitle_language="ja", is_auto_subtitle=False,
        broadcast_start_at=datetime(2024, 3, 1, 20, 0, tzinfo=timezone.utc),
    )
    db.close()
    return db_path


class TestMigrateGroup:
    def test_migrate_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["migrate", "--help"])
        assert result.exit_code == 0
        assert "backfill-broadcast-start" in result.output


class TestBackfillBroadcastStart:
    def test_no_targets(self, tmp_path: Path) -> None:
        """対象動画がない場合のメッセージ"""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.save_channel("UC1", "Ch", "https://youtube.com/c/test")
        db.save_video(
            "vid1", "UC1", "V1",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
            broadcast_start_at=datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc),
        )
        db.close()

        runner = CliRunner()
        with patch("kirinuki.cli.main.create_app_context") as mock_ctx:
            ctx = MagicMock()
            ctx.db = Database(db_path=db_path, embedding_dimensions=1536)
            ctx.db.initialize()
            ctx.config = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(cli, ["migrate", "backfill-broadcast-start"])
            ctx.db.close()

        assert result.exit_code == 0
        assert "対象の動画はありません" in result.output

    @patch("kirinuki.cli.main.YtdlpClient")
    def test_backfill_updates_videos(self, mock_ytdlp_cls, tmp_path: Path) -> None:
        """バックフィルで動画が更新される"""
        db_path = _setup_db_for_backfill(tmp_path)

        bsa1 = datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc)
        mock_ytdlp = MagicMock()
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(
                video_id="vid1", title="Video 1",
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                duration_seconds=3600, broadcast_start_at=bsa1,
            ),
            VideoMeta(
                video_id="vid2", title="Video 2",
                published_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
                duration_seconds=7200, broadcast_start_at=None,  # フォールバック
            ),
        ]
        mock_ytdlp_cls.return_value = mock_ytdlp

        runner = CliRunner()
        with patch("kirinuki.cli.main.create_app_context") as mock_ctx:
            db = Database(db_path=db_path, embedding_dimensions=1536)
            db.initialize()
            ctx = MagicMock()
            ctx.db = db
            ctx.config = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(cli, ["migrate", "backfill-broadcast-start"])

        assert result.exit_code == 0
        assert "更新 2件" in result.output

        # DBの値を確認
        row1 = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid1'").fetchone()
        assert row1[0] == bsa1.isoformat()
        row2 = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid2'").fetchone()
        # フォールバック: published_at
        assert row2[0] is not None
        # vid3は対象外（既に設定済み）
        row3 = db._execute("SELECT broadcast_start_at FROM videos WHERE video_id='vid3'").fetchone()
        assert row3[0] is not None
        db.close()

    @patch("kirinuki.cli.main.YtdlpClient")
    def test_backfill_continues_on_error(self, mock_ytdlp_cls, tmp_path: Path) -> None:
        """エラーが発生しても残りの動画の処理を継続する"""
        db_path = _setup_db_for_backfill(tmp_path)

        mock_ytdlp = MagicMock()
        mock_ytdlp.fetch_video_metadata.side_effect = [
            Exception("Network error"),
            VideoMeta(
                video_id="vid2", title="Video 2",
                published_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
                duration_seconds=7200,
                broadcast_start_at=datetime(2024, 2, 1, 20, 0, tzinfo=timezone.utc),
            ),
        ]
        mock_ytdlp_cls.return_value = mock_ytdlp

        runner = CliRunner()
        with patch("kirinuki.cli.main.create_app_context") as mock_ctx:
            db = Database(db_path=db_path, embedding_dimensions=1536)
            db.initialize()
            ctx = MagicMock()
            ctx.db = db
            ctx.config = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(cli, ["migrate", "backfill-broadcast-start"])

        assert result.exit_code == 0
        assert "更新 1件" in result.output
        assert "エラー 1件" in result.output
        db.close()

    @patch("kirinuki.cli.main.YtdlpClient")
    def test_backfill_summary_with_skip(self, mock_ytdlp_cls, tmp_path: Path) -> None:
        """published_atもNoneの動画はスキップされサマリーに表示される"""
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.save_channel("UC1", "Ch", "https://youtube.com/c/test")
        # published_at=None かつ broadcast_start_at=NULL
        db.save_video(
            "vid1", "UC1", "Video 1",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            duration_seconds=3600, subtitle_language="ja", is_auto_subtitle=False,
        )
        db.save_video(
            "vid_no_date", "UC1", "No Date Video",
            published_at=None,
            duration_seconds=7200, subtitle_language="ja", is_auto_subtitle=False,
        )
        db.close()

        mock_ytdlp = MagicMock()
        mock_ytdlp.fetch_video_metadata.side_effect = [
            VideoMeta(
                video_id="vid1", title="V1",
                published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                duration_seconds=3600,
                broadcast_start_at=datetime(2024, 1, 1, 20, 0, tzinfo=timezone.utc),
            ),
            VideoMeta(
                video_id="vid_no_date", title="No Date",
                published_at=None, duration_seconds=7200,
                broadcast_start_at=None,
            ),
        ]
        mock_ytdlp_cls.return_value = mock_ytdlp

        runner = CliRunner()
        with patch("kirinuki.cli.main.create_app_context") as mock_ctx:
            db = Database(db_path=db_path, embedding_dimensions=1536)
            db.initialize()
            ctx = MagicMock()
            ctx.db = db
            ctx.config = MagicMock()
            mock_ctx.return_value.__enter__ = MagicMock(return_value=ctx)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            result = runner.invoke(cli, ["migrate", "backfill-broadcast-start"])

        assert result.exit_code == 0
        assert "更新 1件" in result.output
        assert "スキップ 1件" in result.output
        db.close()
