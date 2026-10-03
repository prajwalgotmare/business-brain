from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Header
from langfuse import Langfuse
from langgraph.checkpoint.memory import InMemorySaver

from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.analytics.repository import AnalyticsRepository
from business_brain.analytics.service import GovernedAnalyticsService
from business_brain.api.errors import (
    AnalyticsServiceUnavailableError,
    LLMServiceUnavailableError,
    RetrievalServiceUnavailableError,
    UploadServiceUnavailableError,
)
from business_brain.core.config import Settings, get_settings
from business_brain.llm.gateway import LLMGateway
from business_brain.llm.groq_client import HttpGroqChatClient
from business_brain.llm.reliability import CircuitBreaker, RetryPolicy
from business_brain.observability.tracing import (
    GenerationTracer,
    LangfuseGenerationTracer,
    NoOpGenerationTracer,
)
from business_brain.retrieval.hybrid import HybridRetriever
from business_brain.security.context import AuthContext, UserRole
from business_brain.uploads.repository import UploadRepository
from business_brain.uploads.service import UploadService

_agent_checkpointer = None
_agent_checkpoint_pool = None


def get_auth_context(
    x_tenant_id: Annotated[
        str,
        Header(
            alias="X-Tenant-ID",
            min_length=2,
            max_length=63,
            pattern=r"^[a-z0-9][a-z0-9_-]*$",
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


@lru_cache
def _build_governed_supervisor() -> GovernedSupervisor:
    settings = get_settings()
    checkpointer = _agent_checkpointer
    if checkpointer is None:
        if settings.agent_checkpoint_backend != "memory":
            raise LLMServiceUnavailableError("Agent checkpoint runtime is not initialized")
        checkpointer = InMemorySaver()
    return GovernedSupervisor(
        gateway=_build_llm_gateway(),
        tracer=_build_generation_tracer(),
        primary_model=settings.groq_primary_model,
        analytics_service=_build_analytics_service(),
        retriever=_build_hybrid_retriever(),
        checkpointer=checkpointer,
    )


def get_governed_supervisor() -> GovernedSupervisor:
    return _build_governed_supervisor()


async def start_agent_checkpoint_runtime() -> None:
    global _agent_checkpointer, _agent_checkpoint_pool
    if _agent_checkpointer is not None:
        return
    settings = get_settings()
    if settings.agent_checkpoint_backend == "memory":
        _agent_checkpointer = InMemorySaver()
    else:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        url = settings.database_url or settings.database_url_direct
        if not url:
            raise RuntimeError("DATABASE_URL or DATABASE_URL_DIRECT is required for checkpoints")
        pool = AsyncConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=settings.agent_checkpoint_pool_size,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            },
        )
        await pool.open(wait=True)
        saver = AsyncPostgresSaver(pool)
        try:
            await saver.setup()
        except Exception:
            await pool.close()
            raise
        _agent_checkpoint_pool = pool
        _agent_checkpointer = saver
    _build_governed_supervisor.cache_clear()


async def stop_agent_checkpoint_runtime() -> None:
    global _agent_checkpointer, _agent_checkpoint_pool
    _build_governed_supervisor.cache_clear()
    pool = _agent_checkpoint_pool
    _agent_checkpointer = None
    _agent_checkpoint_pool = None
    if pool is not None:
        await pool.close()


@lru_cache
def _build_hybrid_retriever() -> HybridRetriever:
    try:
        return HybridRetriever(settings=get_settings())
    except Exception as exc:
        raise RetrievalServiceUnavailableError("Retrieval service is not configured") from exc


def get_hybrid_retriever() -> HybridRetriever:
    return _build_hybrid_retriever()


@lru_cache
def _build_analytics_service() -> GovernedAnalyticsService:
    try:
        return GovernedAnalyticsService(AnalyticsRepository(settings=get_settings()))
    except Exception as exc:
        raise AnalyticsServiceUnavailableError("Analytics service is not configured") from exc


def get_analytics_service() -> GovernedAnalyticsService:
    return _build_analytics_service()


@lru_cache
def _build_upload_service() -> UploadService:
    settings = get_settings()
    try:
        return UploadService(
            settings=settings,
            repository=UploadRepository(settings),
        )
    except Exception as exc:
        raise UploadServiceUnavailableError("Upload service is not configured") from exc


def get_upload_service() -> UploadService:
    return _build_upload_service()

