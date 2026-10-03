"""Authenticated, read-only MCP surface for governed Business Brain tools."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Protocol

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field, HttpUrl

from business_brain.analytics.repository import AnalyticsRepository
from business_brain.analytics.schemas import (
    FreightReconciliation,
    MarginVariance,
    OverdueInvoice,
    StockoutRisk,
)
from business_brain.analytics.service import GovernedAnalyticsService
from business_brain.core.config import Settings, get_settings
from business_brain.retrieval.hybrid import HybridRetriever
from business_brain.retrieval.schemas import HybridSearchResult
from business_brain.security.auth0 import Auth0TokenValidator, TokenValidationError
from business_brain.security.context import AuthContext, UserRole

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

AuthProvider = Callable[[], AuthContext]


class TokenValidator(Protocol):
    async def validate(self, token: str) -> AuthContext: ...


class BusinessBrainTokenVerifier:
    """Adapt the existing Auth0 JWT validator to the MCP SDK verifier contract."""

    def __init__(self, validator: TokenValidator, *, resource: str) -> None:
        self.validator = validator
        self.resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            auth = await self.validator.validate(token)
        except TokenValidationError:
            return None
        return AccessToken(
            token=token,
            client_id=auth.user_id,
            subject=auth.user_id,
            scopes=[],
            resource=self.resource,
            claims={
                "tenant_id": auth.tenant_id,
                "role": auth.role.value,
            },
        )


def auth_from_access_token(token: AccessToken | None = None) -> AuthContext:
    """Reconstruct only the immutable identity claims needed by governed services."""
    verified = token or get_access_token()
    if verified is None or verified.claims is None:
        raise PermissionError("Authenticated MCP identity is required")
    tenant_id = verified.claims.get("tenant_id")
    role = verified.claims.get("role")
    user_id = verified.subject
    try:
        return AuthContext(
            tenant_id=tenant_id,
            user_id=user_id,
            role=UserRole(role),
        )
    except (TypeError, ValueError) as exc:
        raise PermissionError("Authenticated MCP identity is invalid") from exc


class MCPToolService:
    """Narrow adapter over services that already enforce RBAC and tenant isolation."""

    def __init__(
        self,
        *,
        analytics: GovernedAnalyticsService,
        retriever: HybridRetriever,
    ) -> None:
        self.analytics = analytics
        self.retriever = retriever

    def search_documents(
        self, auth: AuthContext, query: str, limit: int
    ) -> HybridSearchResult:
        return self.retriever.search(query, auth, limit=limit)

    def stockout_risks(self, auth: AuthContext, limit: int) -> list[StockoutRisk]:
        return self.analytics.stockout_risks(auth, limit=limit)

    def freight_reconciliation(
        self, auth: AuthContext, shipment_id: str
    ) -> FreightReconciliation | None:
        return self.analytics.freight_reconciliation(auth, shipment_id)

    def overdue_invoices(
        self, auth: AuthContext, as_of: date, limit: int
    ) -> list[OverdueInvoice]:
        return self.analytics.overdue_invoices(auth, as_of=as_of, limit=limit)

    def margin_variance(
        self,
        auth: AuthContext,
        region_id: str,
        earlier: date,
        later: date,
    ) -> MarginVariance | None:
        return self.analytics.margin_variance(
            auth,
            region_id=region_id,
            earlier=earlier,
            later=later,
        )


def build_tool_service(settings: Settings) -> MCPToolService:
    return MCPToolService(
        analytics=GovernedAnalyticsService(AnalyticsRepository(settings=settings)),
        retriever=HybridRetriever(settings=settings),
    )


async def _safe_tool_call(operation: Callable[[], Any]) -> Any:
    try:
        return await asyncio.to_thread(operation)
    except PermissionError as exc:
        raise PermissionError("MCP tool is not authorized for this identity") from exc
    except ValueError as exc:
        raise ValueError("MCP tool input is invalid") from exc
    except Exception as exc:
        raise RuntimeError("MCP tool could not complete safely") from exc


def build_mcp_server(
    *,
    settings: Settings | None = None,
    tool_service: MCPToolService | None = None,
    token_verifier: Any | None = None,
    auth_provider: AuthProvider = auth_from_access_token,
) -> MCPServer:
    config = settings or get_settings()
    if config.auth_mode != "auth0" or not config.auth0_domain or not config.auth0_audience:
        raise RuntimeError("Authenticated MCP requires Auth0 configuration")
    service = tool_service or build_tool_service(config)
    verifier = token_verifier or BusinessBrainTokenVerifier(
        Auth0TokenValidator(
            domain=config.auth0_domain,
            audience=config.auth0_audience,
            tenant_claim=config.auth0_tenant_claim,
            role_claim=config.auth0_role_claim,
            cache_seconds=config.auth0_jwks_cache_seconds,
            clock_skew_seconds=config.auth0_clock_skew_seconds,
        ),
        resource=config.auth0_audience,
    )
    server = MCPServer(
        name="aura-business-brain",
        description="Authenticated read-only enterprise operations tools.",
        instructions=(
            "Use only the tools allowed for the caller's verified tenant and role. "
            "Never infer access from user text."
        ),
        version="0.1.0",
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=HttpUrl(f"https://{config.auth0_domain}/"),
            resource_server_url=config.mcp_resource_server_url,
            required_scopes=[],
            validate_token_resource=False,
        ),
    )

    @server.tool(
        name="search_documents",
        description="Search authorized contract and invoice passages with citations.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def search_documents(
        query: Annotated[str, Field(min_length=3, max_length=1_000)],
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> HybridSearchResult:
        auth = auth_provider()
        return await _safe_tool_call(lambda: service.search_documents(auth, query, limit))

    @server.tool(
        name="get_stockout_risks",
        description="Return tenant-scoped SKU stockout risks from fixed SQL analytics.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def get_stockout_risks(
        limit: Annotated[int, Field(ge=1, le=20)] = 10,
    ) -> list[StockoutRisk]:
        auth = auth_provider()
        return await _safe_tool_call(lambda: service.stockout_risks(auth, limit))

    @server.tool(
        name="reconcile_freight",
        description="Reconcile one shipment against freight billing and SLA facts.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def reconcile_freight(
        shipment_id: Annotated[
            str,
            Field(pattern=r"^[a-z][a-z0-9_]+$", min_length=3, max_length=80),
        ],
    ) -> FreightReconciliation | None:
        auth = auth_provider()
        return await _safe_tool_call(
            lambda: service.freight_reconciliation(auth, shipment_id)
        )

    @server.tool(
        name="list_overdue_invoices",
        description="List tenant-scoped overdue supplier invoices as of a supplied date.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def list_overdue_invoices(
        as_of: date,
        limit: Annotated[int, Field(ge=1, le=50)] = 20,
    ) -> list[OverdueInvoice]:
        auth = auth_provider()
        return await _safe_tool_call(
            lambda: service.overdue_invoices(auth, as_of, limit)
        )

    @server.tool(
        name="analyze_margin_variance",
        description="Compare two weekly regional margin snapshots for the verified tenant.",
        annotations=READ_ONLY,
        structured_output=True,
    )
    async def analyze_margin_variance(
        region_id: Annotated[
            str,
            Field(pattern=r"^[a-z][a-z0-9_]+$", min_length=3, max_length=80),
        ],
        earlier: date,
        later: date,
    ) -> MarginVariance | None:
        auth = auth_provider()
        return await _safe_tool_call(
            lambda: service.margin_variance(auth, region_id, earlier, later)
        )

    return server


def create_mcp_app():
    """Uvicorn factory for the authenticated Streamable HTTP MCP service."""
    return build_mcp_server().streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
    )
