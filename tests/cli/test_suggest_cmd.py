"""suggest サブコマンドのテスト"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.cli.suggest import parse_until_datetime
from kirinuki.infra.database import Database
from kirinuki.models.recommendation import SegmentRecommendation


def _setup_test_db(tmp_path: Path) -> Path:
    """テスト用DBを準備してパスを返す"""
    from datetime import datetime, timezone

    db_path = tmp_path / "test.db"
    db = Database(db_path=db_path, embedding_dimensions=1536)
    db.initialize()
    db.save_channel("UC123", "テストチャンネル", "https://youtube.com/c/test")
    for i in range(3):
        db.save_video(
            video_id=f"vid{i:03d}",
            channel_id="UC123",
            title=f"テスト動画 {i}",
            published_at=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            duration_seconds=3600,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )
        db.save_segments(
            f"vid{i:03d}",
            [
                {"start_ms": j * 60000, "end_ms": (j + 1) * 60000, "summary": f"話題{j}: テスト話題"}
                for j in range(2)
            ],
        )
    db.close()
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


class TestSuggestCommand:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["suggest", "--help"])
        assert result.exit_code == 0
        assert "--count" in result.output
        assert "--threshold" in result.output
        assert "--json" in result.output
        assert "--video-id" in result.output

    def test_text_output(self, tmp_path: Path) -> None:
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, ["suggest", "UC123", "--threshold", "1"])
        assert result.exit_code == 0
        assert "テスト動画" in result.output
        assert "youtube.com" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, ["suggest", "UC123", "--json", "--threshold", "1"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "videos" in parsed

    def test_no_archives_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.save_channel("UC_EMPTY", "空チャンネル", "https://youtube.com/c/empty")
        db.close()

        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, ["suggest", "UC_EMPTY"])
        assert result.exit_code != 0 or "同期" in result.output

    def test_channel_not_found_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.close()
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, ["suggest", "UNKNOWN"])
        assert result.exit_code != 0 or "登録" in result.output


class TestSuggestVideoIdOption:
    def test_video_id_without_channel(self, tmp_path: Path) -> None:
        """--video-id指定時はチャンネル引数なしで動作する"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, [
                "suggest", "--video-id", "vid000", "--threshold", "1",
            ])
        assert result.exit_code == 0
        assert "テスト動画 0" in result.output

    def test_multiple_video_ids(self, tmp_path: Path) -> None:
        """複数の--video-idを指定できる"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, [
                "suggest", "--video-id", "vid000", "--video-id", "vid001",
                "--threshold", "1",
            ])
        assert result.exit_code == 0
        assert "テスト動画 0" in result.output
        assert "テスト動画 1" in result.output

    def test_video_id_with_json(self, tmp_path: Path) -> None:
        """--video-id + --jsonで正しいJSON出力"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, [
                "suggest", "--video-id", "vid000", "--json", "--threshold", "1",
            ])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "videos" in parsed
        video_ids = [v["video_id"] for v in parsed["videos"]]
        assert video_ids == ["vid000"]

    def test_missing_video_id_warning(self, tmp_path: Path) -> None:
        """存在しない動画IDの警告が出力される"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, [
                "suggest", "--video-id", "vid000", "--video-id", "MISSING",
                "--threshold", "1",
            ])
        assert result.exit_code == 0
        # 警告はstderrに出力されるが、CliRunnerはデフォルトでmixする
        assert "MISSING" in result.output

    def test_all_missing_video_ids_error(self, tmp_path: Path) -> None:
        """全動画IDが存在しない場合はエラー"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, [
                "suggest", "--video-id", "MISSING1", "--video-id", "MISSING2",
            ])
        assert result.exit_code != 0


class TestParseUntilDatetime:
    def test_date_only(self) -> None:
        """YYYY-MM-DD形式は23:59:59として扱う"""
        dt = parse_until_datetime("2024-06-15")
        assert dt == datetime(2024, 6, 15, 23, 59, 59)

    def test_date_and_time(self) -> None:
        """YYYY-MM-DD HH:MM形式が正しくパースされる"""
        dt = parse_until_datetime("2024-06-15 14:30")
        assert dt == datetime(2024, 6, 15, 14, 30, 0)

    def test_invalid_format_raises(self) -> None:
        """無効な形式でclick.BadParameterが送出される"""
        import click
        with pytest.raises(click.BadParameter) as exc_info:
            parse_until_datetime("invalid-date")
        assert "YYYY-MM-DD" in str(exc_info.value)


class TestSuggestUntilOption:
    def test_until_option_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["suggest", "--help"])
        assert "--until" in result.output

    def test_until_option_with_date(self, tmp_path: Path) -> None:
        """--until YYYY-MM-DDでフィルタリングが動作する"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments", side_effect=_fake_evaluate):
            result = runner.invoke(cli, [
                "suggest", "UC123", "--until", "2026-01-02", "--threshold", "1",
            ])
        assert result.exit_code == 0

    def test_until_invalid_format_error(self, tmp_path: Path) -> None:
        """無効な--untilフォーマットでエラーメッセージが表示される"""
        db_path = _setup_test_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, [
                "suggest", "UC123", "--until", "not-a-date",
            ])
        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output
