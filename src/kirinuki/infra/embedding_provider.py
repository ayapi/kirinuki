"""エンベディングプロバイダー（OpenAI text-embedding-3-small）"""

import logging

import openai

from kirinuki.models.config import AppConfig

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    @property
    def dimensions(self) -> int:
        return self._config.embedding_dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        client = openai.OpenAI(api_key=self._config.openai_api_key)
        response = client.embeddings.create(
            model=self._config.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]
