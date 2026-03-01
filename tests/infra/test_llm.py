"""LLMクライアントのテスト（モック使用）"""

from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.llm_client import (
    SEGMENTS_JSON_SCHEMA,
    LlmClient,
    _parse_timestamp,
    _salvage_truncated_json,
)
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
                text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "自己紹介"}, {"start": "01:00", "end": "02:00", "summary": "ゲーム開始"}]}'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 2
        assert segments[0].summary == "自己紹介"
        assert segments[0].start_ms == 0
        assert segments[1].end_ms == 120000

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

    def test_output_config_passed_to_api(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "test"}]}')
        ]
        mock_instance.messages.create.return_value = mock_response

        client.analyze_topics("テスト")
        call_args = mock_instance.messages.create.call_args
        assert "output_config" in call_args[1]
        output_config = call_args[1]["output_config"]
        assert output_config["format"]["type"] == "json_schema"
        assert output_config["format"]["schema"] is SEGMENTS_JSON_SCHEMA


class TestAnalyzeTopicsResplit:
    def test_returns_resplit_segments(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"segments": [{"start": "00:00", "end": "00:30", "summary": "【雑談】挨拶"}, {"start": "00:30", "end": "01:00", "summary": "【雑談】近況報告"}]}'
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
            MagicMock(
                text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "test"}]}'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        client.analyze_topics_resplit("テスト", "ゲーム実況")
        call_args = mock_instance.messages.create.call_args
        system_prompt = call_args[1]["system"]
        assert "参考情報" in system_prompt
        assert "【大分類】" in system_prompt
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

    def test_output_config_passed_to_resplit_api(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "test"}]}'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        client.analyze_topics_resplit("テスト", "親要約")
        call_args = mock_instance.messages.create.call_args
        assert "output_config" in call_args[1]
        output_config = call_args[1]["output_config"]
        assert output_config["format"]["type"] == "json_schema"
        assert output_config["format"]["schema"] is SEGMENTS_JSON_SCHEMA


class TestParseTimestamp:
    def test_mm_ss(self):
        assert _parse_timestamp("01:30") == 90_000

    def test_zero(self):
        assert _parse_timestamp("00:00") == 0

    def test_brackets(self):
        assert _parse_timestamp("[01:30]") == 90_000

    def test_minutes_over_59(self):
        assert _parse_timestamp("120:00") == 7_200_000

    def test_hh_mm_ss(self):
        assert _parse_timestamp("02:00:00") == 7_200_000

    def test_hh_mm_ss_with_seconds(self):
        assert _parse_timestamp("01:30:45") == 5_445_000

    def test_whitespace(self):
        assert _parse_timestamp("  01:30  ") == 90_000

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_timestamp("invalid")

    def test_single_part_raises(self):
        with pytest.raises(ValueError):
            _parse_timestamp("90")


class TestSalvageTruncatedJson:
    def test_salvages_truncated_segments(self):
        raw = '{"segments": [{"start": "00:00", "end": "01:00", "summary": "OK"}, {"start": "01:00", "end": "02:'
        result = _salvage_truncated_json(raw)
        assert result is not None
        assert len(result) == 1
        assert result[0]["summary"] == "OK"

    def test_salvages_with_trailing_comma(self):
        raw = '{"segments": [{"start": "00:00", "end": "01:00", "summary": "A"}, {"start": "01:00", "end": "02:00", "summary": "B"},'
        result = _salvage_truncated_json(raw)
        assert result is not None
        assert len(result) == 2

    def test_returns_none_for_no_braces(self):
        assert _salvage_truncated_json("not json at all") is None

    def test_returns_none_for_empty_array(self):
        assert _salvage_truncated_json('{"segments": [') is None

    def test_truncated_response_salvages_segments(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "挨拶"}, {"start": "01:00", "end": "02:00", "s'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト字幕テキスト")
        assert len(segments) == 1
        assert segments[0].summary == "挨拶"


class TestSkipsInvalidTimestamp:
    def test_skips_bad_segment(self, client, mock_anthropic):
        mock_instance = mock_anthropic.return_value
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='{"segments": [{"start": "00:00", "end": "01:00", "summary": "OK"}, {"start": "bad", "end": "01:00", "summary": "BAD"}]}'
            )
        ]
        mock_instance.messages.create.return_value = mock_response

        segments = client.analyze_topics("テスト")
        assert len(segments) == 1
        assert segments[0].summary == "OK"
