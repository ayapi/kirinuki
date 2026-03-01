"""LLMクライアントのテスト（モック使用）"""

from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.llm_client import LlmClient
from kirinuki.models.config import AppConfig


@pytest.fixture
def mock_anthropic():
    with patch("kirinuki.infra.llm_client.anthropic.Anthropic") as mock_cls:
        yield mock_cls


@pytest.fixture
def client(tmp_path, mock_anthropic):
    config = AppConfig(
        db_path=tmp_path / "data.db",
        anthropic_api_key="test-key",
    )
    return LlmClient(config)


class TestAnalyzeTopics:
    def test_returns_segments(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='[{"start_ms": 0, "end_ms": 60000, "summary": "自己紹介"}, {"start_ms": 60000, "end_ms": 120000, "summary": "ゲーム開始"}]'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 2
        assert segments[0].summary == "自己紹介"
        assert segments[0].start_ms == 0
        assert segments[1].end_ms == 120000

    def test_strips_markdown_code_fence(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```json\n[{"start_ms": 0, "end_ms": 60000, "summary": "挨拶"}]\n```'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 1
        assert segments[0].summary == "挨拶"

    def test_strips_code_fence_without_lang(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='```\n[{"start_ms": 0, "end_ms": 60000, "summary": "挨拶"}]\n```'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 1
        assert segments[0].summary == "挨拶"

    def test_empty_response(self, client):
        segments = client.analyze_topics("")
        assert segments == []

    def test_client_created_with_max_retries(self, mock_anthropic, tmp_path):
        config = AppConfig(
            db_path=tmp_path / "data.db",
            anthropic_api_key="test-key",
        )
        LlmClient(config)
        mock_anthropic.assert_called_once_with(
            api_key="test-key",
            max_retries=10,
        )


class TestAnalyzeTopicsResplit:
    def test_returns_resplit_segments(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='[{"start_ms": 0, "end_ms": 30000, "summary": "【雑談】挨拶"}, {"start_ms": 30000, "end_ms": 60000, "summary": "【雑談】近況報告"}]'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics_resplit("テスト字幕テキスト", "雑談")
        assert len(segments) == 2
        assert segments[0].summary == "【雑談】挨拶"
        assert segments[1].summary == "【雑談】近況報告"

    def test_uses_resplit_system_prompt(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='[{"start_ms": 0, "end_ms": 60000, "summary": "test"}]')
        ]
        mock_instance.messages.create.return_value = mock_response

        client.analyze_topics_resplit("テスト", "ゲーム実況")
        call_args = mock_instance.messages.create.call_args
        system_prompt = call_args[1]["system"]
        assert "ゲーム実況" in system_prompt

    def test_empty_input(self, client):
        segments = client.analyze_topics_resplit("", "test")
        assert segments == []

    def test_invalid_json_returns_empty(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics_resplit("テスト", "test")
        assert segments == []
