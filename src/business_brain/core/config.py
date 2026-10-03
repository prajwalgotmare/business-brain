from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, HttpUrl
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
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("LANGFUSE_BASE_URL", "LANGFUSE_HOST"),
    )
    langfuse_enabled: bool = True
    langfuse_capture_content: bool = True

    database_url: str | None = None
    database_url_direct: str | None = None
    database_statement_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    agent_checkpoint_backend: Literal["memory", "postgres"] = "postgres"
    agent_checkpoint_pool_size: int = Field(default=3, ge=1, le=10)
    upload_max_bytes: int = Field(default=5_242_880, ge=1_024, le=10_485_760)
    upload_max_rows: int = Field(default=500, ge=1, le=5_000)
    upload_max_pdf_pages: int = Field(default=25, ge=1, le=100)
    upload_retention_hours: int = Field(default=168, ge=1, le=720)
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    qdrant_collection: str = "business_brain_documents_v1"
    qdrant_dense_model: str = "BAAI/bge-small-en-v1.5"
    qdrant_sparse_model: str = "Qdrant/bm25"
    qdrant_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    retrieval_candidate_limit: int = Field(default=20, ge=5, le=100)
    retrieval_result_limit: int = Field(default=5, ge=1, le=20)

    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None

    auth0_domain: str | None = None
    auth0_audience: str | None = None
    auth0_client_id: str | None = None
    auth0_tenant_claim: str = "https://business-brain.demo/tenant_id"
    auth0_role_claim: str = "https://business-brain.demo/role"
    auth0_jwks_cache_seconds: int = Field(default=3600, ge=60, le=86_400)
    auth0_clock_skew_seconds: int = Field(default=30, ge=0, le=300)


@lru_cache
def get_settings() -> Settings:
    return Settings()
