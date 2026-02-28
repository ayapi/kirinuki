"""エンベディングプロバイダーのテスト（モック使用）"""

from unittest.mock import MagicMock, patch

import pytest

from kirinuki.infra.embedding_provider import OpenAIEmbeddingProvider
from kirinuki.models.config import AppConfig


@pytest.fixture
def provider(tmp_path):
    config = AppConfig(
        db_path=tmp_path / "data.db",
        openai_api_key="test-key",
    )
    return OpenAIEmbeddingProvider(config)


class TestEmbeddingProvider:
    def test_dimensions(self, provider):
        assert provider.dimensions == 1536

    @patch("kirinuki.infra.embedding_provider.openai.OpenAI")
    def test_embed(self, mock_openai_cls, provider):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_embedding1 = MagicMock()
        mock_embedding1.embedding = [0.1] * 1536
        mock_embedding2 = MagicMock()
        mock_embedding2.embedding = [0.2] * 1536

        mock_response = MagicMock()
        mock_response.data = [mock_embedding1, mock_embedding2]
        mock_client.embeddings.create.return_value = mock_response

        result = provider.embed(["テスト1", "テスト2"])
        assert len(result) == 2
        assert len(result[0]) == 1536

    @patch("kirinuki.infra.embedding_provider.openai.OpenAI")
    def test_embed_empty(self, mock_openai_cls, provider):
        result = provider.embed([])
        assert result == []
