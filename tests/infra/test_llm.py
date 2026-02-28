"""LLMクライアントのテスト（モック使用）"""

from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.llm_client import LlmClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def client(tmp_path):
    config = AppConfig(
        db_path=tmp_path / "data.db",
        anthropic_api_key="test-key",
    )
    return LlmClient(config)


class TestAnalyzeTopics:
    @patch("kirinuki.infra.llm_client.anthropic.Anthropic")
    def test_returns_segments(self, mock_anthropic_cls, client):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='[{"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"}, {"start_ms": 60000, "end_ms": 120000, "summary": "ゲーム開始"}]'
            )
        ]
        mock_client.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 2
        assert segments[0].summary == "自己紹介"
        assert segments[0].start_ms == 0
        assert segments[1].end_ms == 120000

    @patch("kirinuki.infra.llm_client.anthropic.Anthropic")
    def test_empty_response(self, mock_anthropic_cls, client):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="[]")]
        mock_client.messages.create.return_value = mock_response

        segments = client.analyze_topics("")
        assert segments == []
