"""suggest機能の結合テスト"""

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from kirinuki.cli.main import cli
from kirinuki.infra.database import Database
from kirinuki.models.recommendation import SegmentRecommendation


def _setup_full_db(tmp_path: Path) -> Path:
    """結合テスト用のフルDBセットアップ"""
    from datetime import datetime, timezone

    db_path = tmp_path / "integration.db"
    db = Database(db_path=db_path, embedding_dimensions=1536)
    db.initialize()

    db.save_channel("UC_INT", "結合テストチャンネル", "https://youtube.com/c/int")

    for i in range(3):
        db.save_video(
            video_id=f"int_vid{i}",
            channel_id="UC_INT",
            title=f"結合テスト動画 {i}",
            published_at=datetime(2026, 2, 10 + i, 20, 0, 0, tzinfo=timezone.utc),
            duration_seconds=7200,
            subtitle_language="ja",
            is_auto_subtitle=False,
        )
        db.save_segments(
            f"int_vid{i}",
            [
                {
                    "start_ms": j * 120000,
                    "end_ms": (j + 1) * 120000,
                    "summary": f"結合テスト話題 {i}-{j}: 面白いエピソード",
                }
                for j in range(3)
            ],
        )

    db.close()
    return db_path


def _fake_evaluate_varied(
    video_id: str, segments: list[dict[str, str | int]], prompt_version: str
) -> list[SegmentRecommendation]:
    """セグメントごとにスコアを変えるモック"""
    scores = [9, 5, 7]
    return [
        SegmentRecommendation(
            segment_id=seg["id"],
            video_id=video_id,
            start_time=seg["start_ms"] / 1000.0,
            end_time=seg["end_ms"] / 1000.0,
            score=scores[i % len(scores)],
            summary=f"要約: {seg['summary']}",
            appeal="切り抜きに向いている理由: 独立性が高く面白い",
            prompt_version=prompt_version,
        )
        for i, seg in enumerate(segments)
    ]


class TestE2ETextOutput:
    def test_text_output_contains_all_required_info(self, tmp_path: Path) -> None:
        db_path = _setup_full_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments",
                   side_effect=_fake_evaluate_varied):
            result = runner.invoke(cli, ["suggest", "UC_INT", "--threshold", "1"])

        assert result.exit_code == 0
        output = result.output
        # URL含む
        assert "youtube.com/watch?v=" in output
        # スコア含む
        assert "/10]" in output
        # 要約含む
        assert "要約:" in output
        # 魅力含む
        assert "魅力:" in output

    def test_text_output_filters_by_threshold(self, tmp_path: Path) -> None:
        db_path = _setup_full_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments",
                   side_effect=_fake_evaluate_varied):
            result = runner.invoke(cli, ["suggest", "UC_INT", "--threshold", "8"])

        assert result.exit_code == 0
        output = result.output
        # score=9のみ通過、score=5やscore=7は通過しない
        assert "[9/10]" in output
        assert "[5/10]" not in output


class TestE2EJsonOutput:
    def test_json_output_is_parseable(self, tmp_path: Path) -> None:
        db_path = _setup_full_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments",
                   side_effect=_fake_evaluate_varied):
            result = runner.invoke(
                cli, ["suggest", "UC_INT", "--json", "--threshold", "1"]
            )

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "videos" in parsed
        assert "total_candidates" in parsed
        assert "filtered_count" in parsed

    def test_json_output_has_required_fields(self, tmp_path: Path) -> None:
        db_path = _setup_full_db(tmp_path)
        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments",
                   side_effect=_fake_evaluate_varied):
            result = runner.invoke(
                cli, ["suggest", "UC_INT", "--json", "--threshold", "1"]
            )

        parsed = json.loads(result.output)
        video = parsed["videos"][0]
        assert "video_id" in video
        assert "title" in video
        assert "broadcast_start_at" in video
        assert "recommendations" in video

        rec = video["recommendations"][0]
        assert "score" in rec
        assert "summary" in rec
        assert "appeal" in rec
        assert "youtube_url" in rec
        assert "start_time" in rec
        assert "end_time" in rec


class TestE2EErrorCases:
    def test_zero_archives_shows_error(self, tmp_path: Path) -> None:
        db_path = tmp_path / "empty.db"
        db = Database(db_path=db_path, embedding_dimensions=1536)
        db.initialize()
        db.save_channel("UC_EMPTY", "空", "https://youtube.com/c/empty")
        db.close()

        runner = CliRunner()
        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path):
            result = runner.invoke(cli, ["suggest", "UC_EMPTY"])

        # エラーメッセージが表示される
        assert "同期" in result.output or "同期" in (result.stderr_bytes or b"").decode("utf-8", errors="replace")

    def test_below_threshold_shows_guidance(self, tmp_path: Path) -> None:
        db_path = _setup_full_db(tmp_path)
        runner = CliRunner()

        def low_score_evaluate(
            video_id: str, segments: list[dict[str, str | int]], prompt_version: str
        ) -> list[SegmentRecommendation]:
            return [
                SegmentRecommendation(
                    segment_id=seg["id"],
                    video_id=video_id,
                    start_time=seg["start_ms"] / 1000.0,
                    end_time=seg["end_ms"] / 1000.0,
                    score=2,
                    summary="低スコア",
                    appeal="あまり向いていない",
                    prompt_version=prompt_version,
                )
                for seg in segments
            ]

        with patch("kirinuki.cli.suggest.get_db_path", return_value=db_path), \
             patch("kirinuki.infra.llm_client.LlmClient.evaluate_segments",
                   side_effect=low_score_evaluate):
            result = runner.invoke(cli, ["suggest", "UC_INT", "--threshold", "7"])

        assert result.exit_code == 0
        assert "0件" in result.output or "該当なし" in result.output
        assert "--threshold" in result.output
