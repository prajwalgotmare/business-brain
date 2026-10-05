import logging
from functools import lru_cache
from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langfuse import Langfuse
from langgraph.checkpoint.memory import InMemorySaver

from business_brain.agent.supervisor import GovernedSupervisor
from business_brain.analytics.repository import AnalyticsRepository
from business_brain.analytics.service import GovernedAnalyticsService
from business_brain.api.errors import (
    AnalyticsServiceUnavailableError,
    AuthenticationError,
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
from business_brain.security.auth0 import Auth0TokenValidator, TokenValidationError
from business_brain.security.context import AuthContext, UserRole
from business_brain.uploads.repository import UploadRepository
from business_brain.uploads.service import UploadService

_agent_checkpointer = None
_agent_checkpoint_pool = None
_bearer_scheme = HTTPBearer(auto_error=False)
_logger = logging.getLogger(__name__)


@lru_cache
def _build_auth0_validator(
    domain: str,
    audience: str,
    tenant_claim: str,
    role_claim: str,
    cache_seconds: int,
    clock_skew_seconds: int,
) -> Auth0TokenValidator:
    return Auth0TokenValidator(
        domain=domain,
        audience=audience,
        tenant_claim=tenant_claim,
        role_claim=role_claim,
        cache_seconds=cache_seconds,
        clock_skew_seconds=clock_skew_seconds,
    )


def get_auth0_validator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Auth0TokenValidator | None:
    if settings.auth_mode == "mock":
        return None
    if not settings.auth0_domain or not settings.auth0_audience:
        raise AuthenticationError("Auth0 authentication is not configured")
    return _build_auth0_validator(
        settings.auth0_domain,
        settings.auth0_audience,
        settings.auth0_tenant_claim,
        settings.auth0_role_claim,
        settings.auth0_jwks_cache_seconds,
        settings.auth0_clock_skew_seconds,
    )


async def get_auth_context(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
    validator: Annotated[Auth0TokenValidator | None, Depends(get_auth0_validator)],
    x_tenant_id: Annotated[
        str | None,
        Header(alias="X-Tenant-ID"),
    ] = None,
    x_user_id: Annotated[
        str | None,
        Header(alias="X-User-ID"),
    ] = None,
    x_role: Annotated[str | None, Header(alias="X-Role")] = None,
) -> AuthContext:
    if settings.auth_mode == "auth0":
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise AuthenticationError("A bearer token is required")
        if validator is None:
            raise AuthenticationError("Auth0 authentication is not configured")
        try:
            return await validator.validate(credentials.credentials)
        except TokenValidationError as exc:
            raise AuthenticationError("Bearer token is invalid") from exc

    if not x_tenant_id or not x_user_id or not x_role:
        raise AuthenticationError("Mock identity headers are required")
    try:
        role = UserRole(x_role)
        return AuthContext(tenant_id=x_tenant_id, user_id=x_user_id, role=role)
    except ValueError as exc:
        raise AuthenticationError("Mock identity headers are invalid") from exc


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
    try:
        retriever = _build_hybrid_retriever()
    except RetrievalServiceUnavailableError:
        # Serverless deployments may not be able to download the fastembed
        # models on the first request. Keep SQL/analytics routes available;
        # document questions will return a governed tool failure instead of a
        # generic HTTP 503 that the web client cannot explain.
        _logger.exception("Hybrid retrieval unavailable; continuing without document retrieval")
        retriever = None

    return GovernedSupervisor(
        gateway=_build_llm_gateway(),
        tracer=_build_generation_tracer(),
        primary_model=settings.groq_primary_model,
        analytics_service=_build_analytics_service(),
        retriever=retriever,
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

