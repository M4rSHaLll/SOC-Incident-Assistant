"""Settings loaded from environment variables and an optional .env file."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIMENSION = 384


class Settings(BaseSettings):
    app_name: str = "SOC Incident Assistant"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@127.0.0.1:55432/soc_assistant"
    )
    test_database_url: str | None = None
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = EMBEDDING_DIMENSION
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str = "gpt-4.1-mini"
    llm_timeout_seconds: float = Field(default=30, gt=0, allow_inf_nan=False)
    rag_max_context_chars: int = Field(default=12000, ge=1)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
