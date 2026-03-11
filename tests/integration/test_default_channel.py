"""デフォルトチャンネルID機能の統合テスト"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.infra.db import DatabaseClient
from kirinuki.models.domain import ChannelSummary, VideoSummary
from kirinuki.models.recommendation import SegmentRecommendation


def _setup_single_channel_db(tmp_path: Path) -> Path:
    """1チャンネルのみ登録されたDBを準備する"""
    db_path = tmp_path / "single.db"
    DatabaseClient(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
        ("UC_ONLY", "唯一のチャンネル", "https://youtube.com/c/only"),
    )
    conn.execute(
        """INSERT INTO videos (video_id, channel_id, title, published_at,
           duration_seconds, subtitle_language, is_auto_subtitle)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("vid001", "UC_ONLY", "テスト動画", "2026-02-01T00:00:00", 3600, "ja", 0),
    )
    conn.execute(
        "INSERT INTO segments (video_id, start_ms, end_ms, summary) VALUES (?, ?, ?, ?)",
        ("vid001", 0, 60000, "テスト話題"),
    )
    conn.commit()
    conn.close()
    return db_path


def _setup_multi_channel_db(tmp_path: Path) -> Path:
    """複数チャンネルが登録されたDBを準備する"""
    db_path = tmp_path / "multi.db"
    DatabaseClient(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
        ("UC_A", "チャンネルA", "https://youtube.com/c/a"),
    )
    conn.execute(
        "INSERT INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
        ("UC_B", "チャンネルB", "https://youtube.com/c/b"),
    )
    conn.commit()
    conn.close()
    return db_path


def _fake_evaluate(
    video_id: str, segments: list[dict[str, str | int]], prompt_version: str
) -> list[SegmentRecommendation]:
    return [
        SegmentRecommendation(
            segment_id=seg["id"],
            video_id=video_id,
            start_time=seg["start_ms"] / 1000.0,
            end_time=seg["end_ms"] / 1000.0,
            score=8,
            summary="テスト要約",
            appeal="テスト魅力",
            prompt_version=prompt_version,
        )
        for seg in segments
    ]


class TestChannelVideosDefaultChannel:
    """channel videos コマンドのチャンネルID省略テスト"""

    @patch("kirinuki.cli.main.create_app_context")
    def test_single_channel_auto_select(self, mock_ctx):
        """1チャンネル登録時、チャンネルID省略で動作する"""
        mock_context = MagicMock()
        mock_context.db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_ONLY",
                name="唯一のチャンネル",
                url="https://youtube.com/c/only",
                video_count=1,
            ),
        ]
        mock_context.channel_service.list_videos.return_value = [
            VideoSummary(
                video_id="vid001",
                title="テスト動画",
                published_at=None,
                duration_seconds=3600,
            ),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(cli, ["channel", "videos"])
        assert result.exit_code == 0
        assert "テスト動画" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_multiple_channels_error(self, mock_ctx):
        """複数チャンネル登録時、チャンネルID省略でエラー"""
        mock_context = MagicMock()
        mock_context.db.list_channels.return_value = [
            ChannelSummary(
                channel_id="UC_A",
                name="チャンネルA",
                url="https://youtube.com/c/a",
                video_count=3,
            ),
            ChannelSummary(
                channel_id="UC_B",
                name="チャンネルB",
                url="https://youtube.com/c/b",
                video_count=7,
            ),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(cli, ["channel", "videos"])
        assert result.exit_code != 0
        assert "チャンネルA" in result.output
        assert "チャンネルB" in result.output

    @patch("kirinuki.cli.main.create_app_context")
    def test_explicit_id_still_works(self, mock_ctx):
        """チャンネルID明示指定時は従来通り動作する"""
        mock_context = MagicMock()
        mock_context.channel_service.list_videos.return_value = [
            VideoSummary(
                video_id="vid001",
                title="テスト動画",
                published_at=None,
                duration_seconds=3600,
            ),
        ]
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_context)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(cli, ["channel", "videos", "UC_EXPLICIT"])
        assert result.exit_code == 0
        mock_context.db.list_channels.assert_not_called()


class TestSuggestDefaultChannel:
    """suggest コマンドのチャンネルID省略テスト"""

    def test_single_channel_auto_select(self, tmp_path: Path) -> None:
        """1チャンネル登録時、チャンネルID省略で動作する"""
        db_path = _setup_single_channel_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, ["suggest", "--threshold", "1"])
        assert result.exit_code == 0

    def test_multiple_channels_error(self, tmp_path: Path) -> None:
        """複数チャンネル登録時、チャンネルID省略でエラー"""
        db_path = _setup_multi_channel_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, ["suggest"])
        assert result.exit_code != 0
        assert "チャンネルA" in result.output
        assert "チャンネルB" in result.output

    def test_explicit_id_still_works(self, tmp_path: Path) -> None:
        """チャンネルID明示指定時は従来通り動作する"""
        db_path = _setup_single_channel_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, ["suggest", "UC_ONLY", "--threshold", "1"])
        assert result.exit_code == 0
