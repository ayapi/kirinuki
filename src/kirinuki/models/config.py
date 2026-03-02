"""アプリケーション設定モデル"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

KIRINUKI_DIR = Path.home() / ".kirinuki"


class AppConfig(BaseSettings):
    model_config = {
        "env_prefix": "KIRINUKI_",
        "env_file": str(KIRINUKI_DIR / ".env"),
        "env_file_encoding": "utf-8",
    }

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    cookie_file_path: Path = Field(
        default_factory=lambda: KIRINUKI_DIR / "cookies.txt",
    )
    db_path: Path = Field(default_factory=lambda: KIRINUKI_DIR / "data.db")
    llm_model: str = "claude-haiku-4-5-20251001"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    output_dir: Path = Field(default_factory=lambda: KIRINUKI_DIR / "output")
