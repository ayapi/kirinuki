"""LlmClient.evaluate_segments のテスト（モック使用）"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.llm_client import LlmClient
from kirinuki.models.config import AppConfig


SAMPLE_SEGMENTS = [
    {"id": 1, "start_ms": 0, "end_ms": 60000, "summary": "自己紹介"},
    {"id": 2, "start_ms": 60000, "end_ms": 120000, "summary": "ゲーム開始"},
]


def _make_response_text(text: str, stop_reason: str = "end_turn") -> MagicMock:
    """Anthropic API のレスポンスモックを作成する"""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_response.stop_reason = stop_reason
    return mock_response


def _valid_json() -> str:
    """正常な評価レスポンスJSON"""
    return json.dumps(
        {
            "evaluations": [
                {
                    "segment_id": 1,
                    "score": 8,
                    "summary": "配信者が自己紹介をしている",
                    "appeal": "初見の視聴者に向けた分かりやすい自己紹介",
                },
                {
                    "segment_id": 2,
                    "score": 6,
                    "summary": "ゲームプレイが始まる",
                    "appeal": "ゲーム開始の瞬間は切り抜きに適している",
                },
            ]
        }
    )


@pytest.fixture
def mock_anthropic():
    with patch("kirinuki.infra.llm_client.anthropic.Anthropic") as mock_cls:
        yield mock_cls


@pytest.fixture
def client(tmp_path, mock_anthropic):
    config = AppConfig(
        db_path=tmp_path / "data.db",
        anthropic_api_key="test-key",
        llm_model="test-model",
    )
    return LlmClient(config)


class TestEvaluateSegmentsNormal:
    """Task 2.1: 正常系テスト"""

    def test_returns_recommendations(self, client, mock_anthropic):
        """有効な JSON レスポンスが SegmentRecommendation リストに正しく変換される"""
        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.return_value = _make_response_text(_valid_json())

        result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")

        assert len(result) == 2
        assert result[0].segment_id == 1
        assert result[0].score == 8
        assert result[0].video_id == "video1"
        assert result[0].summary == "配信者が自己紹介をしている"
        assert result[0].appeal == "初見の視聴者に向けた分かりやすい自己紹介"
        assert result[0].prompt_version == "v1"
        assert result[0].start_time == 0.0
        assert result[0].end_time == 60.0

    def test_no_response_model_parameter(self, client, mock_anthropic):
        """messages.create() が response_model パラメータなしで呼び出される"""
        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.return_value = _make_response_text(_valid_json())

        client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")

        call_kwargs = mock_instance.messages.create.call_args[1]
        assert "response_model" not in call_kwargs


class TestEvaluateSegmentsEdgeCases:
    """Task 2.2: コードフェンスおよびエラー系テスト"""

    def test_strips_code_fence_with_json_lang(self, client, mock_anthropic):
        """コードフェンス（```json ... ```）で囲まれた JSON が正しくパースされる"""
        mock_instance = mock_anthropic.return_value
        fenced = f"```json\n{_valid_json()}\n```"
        mock_instance.messages.create.return_value = _make_response_text(fenced)

        result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")
        assert len(result) == 2
        assert result[0].score == 8

    def test_strips_code_fence_without_lang(self, client, mock_anthropic):
        """言語指定なしのコードフェンスでも正しくパースされる"""
        mock_instance = mock_anthropic.return_value
        fenced = f"```\n{_valid_json()}\n```"
        mock_instance.messages.create.return_value = _make_response_text(fenced)

        result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")
        assert len(result) == 2

    def test_invalid_json_returns_empty(self, client, mock_anthropic, caplog):
        """不正な JSON レスポンス時に空リストが返却され、警告ログが出力される"""
        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.return_value = _make_response_text(
            "これはJSONではありません"
        )

        with caplog.at_level(logging.WARNING):
            result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")

        assert result == []
        assert any("JSON" in record.message for record in caplog.records)

    def test_validation_error_returns_empty(self, client, mock_anthropic, caplog):
        """スキーマ不一致（score が範囲外）時に空リストが返却される"""
        mock_instance = mock_anthropic.return_value
        invalid_data = json.dumps(
            {
                "evaluations": [
                    {
                        "segment_id": 1,
                        "score": 99,  # 範囲外
                        "summary": "test",
                        "appeal": "test",
                    }
                ]
            }
        )
        mock_instance.messages.create.return_value = _make_response_text(invalid_data)

        with caplog.at_level(logging.WARNING):
            result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")

        assert result == []


def _make_segments(n: int) -> list[dict]:
    """テスト用にn件のセグメントを生成する"""
    return [
        {"id": i, "start_ms": i * 60000, "end_ms": (i + 1) * 60000, "summary": f"話題{i}"}
        for i in range(1, n + 1)
    ]


def _make_eval_json(segment_ids: list[int]) -> str:
    """指定IDの評価結果JSONを生成する"""
    return json.dumps(
        {
            "evaluations": [
                {
                    "segment_id": sid,
                    "score": 5,
                    "summary": f"話題{sid}の要約",
                    "appeal": f"話題{sid}の魅力",
                }
                for sid in segment_ids
            ]
        }
    )


class TestBatchSplitting:
    """バッチ分割テスト"""

    def test_small_list_single_call(self, client, mock_anthropic):
        """50件以下のセグメントは1回のAPIコールで処理される"""
        mock_instance = mock_anthropic.return_value
        segments = _make_segments(10)
        mock_instance.messages.create.return_value = _make_response_text(
            _make_eval_json(list(range(1, 11)))
        )

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 1
        assert len(result) == 10

    def test_large_list_multiple_calls(self, client, mock_anthropic):
        """50件超のセグメントは複数回のAPIコールに分割される"""
        mock_instance = mock_anthropic.return_value
        segments = _make_segments(120)

        # 3バッチ: 各バッチ内で連番1始まり（_evaluate_batchが連番マッピングするため）
        mock_instance.messages.create.side_effect = [
            _make_response_text(_make_eval_json(list(range(1, 51)))),
            _make_response_text(_make_eval_json(list(range(1, 51)))),
            _make_response_text(_make_eval_json(list(range(1, 21)))),
        ]

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 3
        assert len(result) == 120


class TestTruncationDetection:
    """切り詰め検知テスト"""

    def test_max_tokens_returns_empty_with_warning(self, client, mock_anthropic, caplog):
        """stop_reason='max_tokens' で空リスト返却＋warningログ"""
        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.return_value = _make_response_text(
            '{"evaluations": [', stop_reason="max_tokens"
        )

        with caplog.at_level(logging.WARNING):
            result = client.evaluate_segments("video1", SAMPLE_SEGMENTS, "v1")

        assert result == []
        assert any("truncated" in record.message for record in caplog.records)


class TestPartialBatchFailure:
    """部分失敗テスト"""

    def test_failed_batch_skipped_others_succeed(self, client, mock_anthropic):
        """一方のバッチが失敗しても他方の結果が返る"""
        mock_instance = mock_anthropic.return_value
        segments = _make_segments(80)

        # バッチ1: 切り詰めで失敗、バッチ2: 成功（連番1始まり）
        mock_instance.messages.create.side_effect = [
            _make_response_text('{"evaluations": [', stop_reason="max_tokens"),
            _make_response_text(_make_eval_json(list(range(1, 31)))),
        ]

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 2
        assert len(result) == 30
        assert all(r.segment_id >= 51 for r in result)
