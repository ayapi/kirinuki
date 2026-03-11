"""LlmClient.evaluate_segments の並列バッチ評価テスト"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.llm_client import BATCH_SIZE, LlmClient
from kirinuki.models.config import AppConfig


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


def _make_response_text(text: str, stop_reason: str = "end_turn") -> MagicMock:
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=text)]
    mock_response.stop_reason = stop_reason
    return mock_response


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
        max_concurrent_api_calls=4,
    )
    return LlmClient(config)


class TestParallelBatchEvaluation:
    def test_multiple_batches_run_in_parallel(self, client, mock_anthropic):
        """複数バッチが並列で処理される"""
        import time as time_mod

        thread_ids: list[int] = []
        lock = threading.Lock()

        segments = _make_segments(120)  # 3バッチ

        def fake_create(**kwargs):
            with lock:
                thread_ids.append(threading.current_thread().ident)
            time_mod.sleep(0.01)  # 並列実行を促す
            prompt = kwargs["messages"][0]["content"]
            # バッチ内のセグメント数から連番を推定
            count = prompt.count("- ID:")
            return _make_response_text(
                _make_eval_json(list(range(1, count + 1)))
            )

        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.side_effect = fake_create

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 3
        assert len(result) == 120
        # 複数スレッドで実行された
        unique_threads = set(thread_ids)
        assert len(unique_threads) > 1

    def test_single_batch_skips_threading(self, client, mock_anthropic):
        """1バッチの場合はスレッドプールを使わない"""
        segments = _make_segments(10)
        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.return_value = _make_response_text(
            _make_eval_json(list(range(1, 11)))
        )

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 1
        assert len(result) == 10

    def test_partial_batch_failure_in_parallel(self, client, mock_anthropic):
        """並列実行中に一部バッチが失敗しても他のバッチの結果は返る"""
        segments = _make_segments(120)  # 3バッチ (50, 50, 20)

        def fake_create(**kwargs):
            prompt = kwargs["messages"][0]["content"]
            count = prompt.count("- ID:")
            # 20件のバッチ（3番目）を確定的に失敗させる
            if count == 20:
                return _make_response_text(
                    '{"evaluations": [', stop_reason="max_tokens"
                )
            return _make_response_text(
                _make_eval_json(list(range(1, count + 1)))
            )

        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.side_effect = fake_create

        result = client.evaluate_segments("video1", segments, "v1")

        assert mock_instance.messages.create.call_count == 3
        # 3番目のバッチ(20件)が失敗、残り100件
        assert len(result) == 100

    def test_max_workers_from_config(self, tmp_path, mock_anthropic):
        """max_concurrent_api_callsの設定がmax_workersに反映される"""
        config = AppConfig(
            db_path=tmp_path / "data.db",
            anthropic_api_key="test-key",
            max_concurrent_api_calls=2,
        )
        client = LlmClient(config)
        assert client._max_workers == 2

    def test_invalid_max_concurrent_rejected(self, tmp_path):
        """max_concurrent_api_calls=0はバリデーションエラー"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(
                db_path=tmp_path / "data.db",
                anthropic_api_key="test-key",
                max_concurrent_api_calls=0,
            )

    def test_result_order_preserved(self, client, mock_anthropic):
        """並列実行でも結果の順序が維持される"""
        segments = _make_segments(120)

        mock_instance = mock_anthropic.return_value
        mock_instance.messages.create.side_effect = [
            _make_response_text(_make_eval_json(list(range(1, 51)))),
            _make_response_text(_make_eval_json(list(range(1, 51)))),
            _make_response_text(_make_eval_json(list(range(1, 21)))),
        ]

        result = client.evaluate_segments("video1", segments, "v1")

        # segment_idが昇順であること（バッチの結合順序が正しい）
        segment_ids = [r.segment_id for r in result]
        assert segment_ids == sorted(segment_ids)
