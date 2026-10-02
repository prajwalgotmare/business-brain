from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Header
from langfuse import Langfuse

from business_brain.api.errors import LLMServiceUnavailableError
from business_brain.core.config import Settings, get_settings
from business_brain.llm.gateway import LLMGateway
from business_brain.llm.groq_client import HttpGroqChatClient
from business_brain.llm.reliability import CircuitBreaker, RetryPolicy
from business_brain.observability.tracing import (
    GenerationTracer,
    LangfuseGenerationTracer,
    NoOpGenerationTracer,
)
from business_brain.security.context import AuthContext, UserRole


def get_auth_context(
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-ID",
            min_length=2,
            max_length=63,
            pattern=r"^[a-z0-9][a-z0-9-]*$",
        ),
    ],
    x_user_id: Annotated[
        str,
        Header(
            alias="X-User-ID",
            min_length=2,
            max_length=100,
            pattern=r"^[A-Za-z0-9][A-Za-z0-9._@-]*$",
        ),
    ],
    x_role: Annotated[UserRole, Header(alias="X-Role")],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    if settings.auth_mode != "mock":
        raise LLMServiceUnavailableError("Mock authentication is disabled")
    return AuthContext(tenant_id=x_tenant_id, user_id=x_user_id, role=x_role)


@lru_cache
def _build_llm_gateway() -> LLMGateway:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMServiceUnavailableError("LLM service is not configured")

    client = HttpGroqChatClient(
        api_key=settings.groq_api_key,
        base_url=str(settings.groq_base_url),
        timeout_seconds=settings.llm_timeout_seconds,
    )
    retry_policy = RetryPolicy(
        max_attempts=settings.llm_max_attempts,
        base_delay_seconds=settings.llm_backoff_base_seconds,
        max_delay_seconds=settings.llm_backoff_max_seconds,
        jitter_ratio=settings.llm_backoff_jitter_ratio,
    )
    circuit = CircuitBreaker(
        failure_threshold=settings.llm_circuit_failure_threshold,
        recovery_seconds=settings.llm_circuit_recovery_seconds,
    )
    return LLMGateway(
        client=client,
        primary_model=settings.groq_primary_model,
        fallback_model=settings.groq_fallback_model,
        retry_policy=retry_policy,
        primary_circuit=circuit,
    )


def get_llm_gateway() -> LLMGateway:
    return _build_llm_gateway()


@lru_cache
def _build_generation_tracer() -> GenerationTracer:
    settings = get_settings()
    if (
        not settings.langfuse_enabled
        or not settings.langfuse_public_key
        or not settings.langfuse_secret_key
        or not settings.langfuse_public_key.startswith("pk-lf-")
        or not settings.langfuse_secret_key.startswith("sk-lf-")
    ):
        return NoOpGenerationTracer()

    parsed_url = urlparse(settings.langfuse_base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return NoOpGenerationTracer()

    try:
        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_base_url,
            environment=settings.app_env,
            tracing_enabled=True,
        )
    except Exception:
        return NoOpGenerationTracer()

    return LangfuseGenerationTracer(
        client=client,
        capture_content=settings.langfuse_capture_content,
    )


def get_generation_tracer() -> GenerationTracer:
    return _build_generation_tracer()

