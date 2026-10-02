from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Business Brain"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    auth_mode: Literal["mock", "auth0"] = "mock"

    groq_api_key: str | None = None
    groq_primary_model: str = "openai/gpt-oss-120b"
    groq_fallback_model: str = "qwen/qwen3.8-27b"
    groq_base_url: HttpUrl = HttpUrl("https://api.groq.com/openai/v1")
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_max_attempts: int = Field(default=3, ge=1, le=5)
    llm_backoff_base_seconds: float = Field(default=0.25, ge=0, le=10)
    llm_backoff_max_seconds: float = Field(default=4.0, ge=0, le=30)
    llm_backoff_jitter_ratio: float = Field(default=0.2, ge=0, le=1)
    llm_circuit_failure_threshold: int = Field(default=3, ge=1, le=20)
    llm_circuit_recovery_seconds: float = Field(default=30.0, gt=0, le=300)
    gemini_api_key: str | None = None

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    database_url: str | None = None
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None

    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None

    auth0_domain: str | None = None
    auth0_audience: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
