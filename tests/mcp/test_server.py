from datetime import date

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.auth.provider import AccessToken

from business_brain.analytics.service import GovernedAnalyticsService
from business_brain.core.config import Settings
from business_brain.mcp.server import (
    BusinessBrainTokenVerifier,
    MCPToolService,
    auth_from_access_token,
    build_mcp_server,
)
from business_brain.security.auth0 import TokenValidationError
from business_brain.security.context import AuthContext, UserRole


def auth(role: UserRole = UserRole.FOUNDER_CFO) -> AuthContext:
    return AuthContext(tenant_id="tenant_aura", user_id="mcp-user", role=role)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        auth_mode="auth0",
        auth0_domain="aura.example.auth0.com",
        auth0_audience="https://api.aura-business-brain.demo",
        mcp_resource_server_url="http://127.0.0.1:8001/mcp",
        agent_checkpoint_backend="memory",
    )


class FakeTokenValidator:
    def __init__(self, result: AuthContext | Exception) -> None:
        self.result = result
        self.tokens = []

    async def validate(self, token: str) -> AuthContext:
        self.tokens.append(token)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class AcceptingVerifier:
    async def verify_token(self, token: str) -> AccessToken | None:
        return AccessToken(token=token, client_id="test", scopes=[])


class RecordingAnalytics:
    def __init__(self) -> None:
        self.calls = []

    def stockout_risks(self, caller: AuthContext, *, limit: int):
        self.calls.append(("stockout", caller, limit))
        return []

    def freight_reconciliation(self, caller: AuthContext, shipment_id: str):
        self.calls.append(("freight", caller, shipment_id))
        return None

    def overdue_invoices(self, caller: AuthContext, *, as_of: date, limit: int):
        self.calls.append(("overdue", caller, as_of, limit))
        return []

    def margin_variance(
        self,
        caller: AuthContext,
        *,
        region_id: str,
        earlier: date,
        later: date,
    ):
        self.calls.append(("margin", caller, region_id, earlier, later))
        return None


class RecordingRetriever:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query: str, caller: AuthContext, *, limit: int):
        self.calls.append((query, caller, limit))
        from business_brain.retrieval.schemas import HybridSearchResult

        return HybridSearchResult(
            query=query,
            tenant_id=caller.tenant_id,
            role=caller.role.value,
            candidate_count=0,
            hits=[],
        )


class EmptyRepository:
    def __init__(self) -> None:
        self.calls = []

    def stockout_risks(self, tenant_id: str, limit: int):
        self.calls.append((tenant_id, limit))
        return []


def tool_service(analytics=None, retriever=None) -> MCPToolService:
    return MCPToolService(
        analytics=analytics or RecordingAnalytics(),
        retriever=retriever or RecordingRetriever(),
    )


@pytest.mark.asyncio
async def test_auth0_verifier_maps_only_governance_claims() -> None:
    validator = FakeTokenValidator(auth(UserRole.STAFF_ACCOUNTANT))
    verifier = BusinessBrainTokenVerifier(
        validator,
        resource="https://api.aura-business-brain.demo",
    )

    token = await verifier.verify_token("signed-token")

    assert token is not None
    assert validator.tokens == ["signed-token"]
    assert token.subject == "mcp-user"
    assert token.claims == {"tenant_id": "tenant_aura", "role": "staff_accountant"}
    assert token.scopes == []


@pytest.mark.asyncio
async def test_auth0_verifier_rejects_invalid_token_without_claims() -> None:
    verifier = BusinessBrainTokenVerifier(
        FakeTokenValidator(TokenValidationError("bad token")),
        resource="https://api.aura-business-brain.demo",
    )

    assert await verifier.verify_token("invalid") is None


def test_access_token_claims_must_form_a_valid_auth_context() -> None:
    valid = AccessToken(
        token="opaque",
        client_id="client",
        subject="auth0|user",
        scopes=[],
        claims={"tenant_id": "tenant_aura", "role": "logistics_manager"},
    )
    assert auth_from_access_token(valid).role == UserRole.LOGISTICS_MANAGER

    invalid = valid.model_copy(update={"claims": {"tenant_id": "../apex", "role": "founder_cfo"}})
    with pytest.raises(PermissionError, match="identity is invalid"):
        auth_from_access_token(invalid)


@pytest.mark.asyncio
async def test_server_advertises_only_five_read_only_tenant_implicit_tools() -> None:
    server = build_mcp_server(
        settings=settings(),
        tool_service=tool_service(),
        token_verifier=AcceptingVerifier(),
        auth_provider=auth,
    )

    async with Client(server) as client:
        result = await client.list_tools()

    assert {tool.name for tool in result.tools} == {
        "search_documents",
        "get_stockout_risks",
        "reconcile_freight",
        "list_overdue_invoices",
        "analyze_margin_variance",
    }
    for tool in result.tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert "tenant_id" not in tool.input_schema.get("properties", {})


@pytest.mark.asyncio
async def test_tool_call_injects_verified_tenant_and_role() -> None:
    analytics = RecordingAnalytics()
    caller = auth(UserRole.LOGISTICS_MANAGER)
    server = build_mcp_server(
        settings=settings(),
        tool_service=tool_service(analytics=analytics),
        token_verifier=AcceptingVerifier(),
        auth_provider=lambda: caller,
    )

    async with Client(server) as client:
        result = await client.call_tool("get_stockout_risks", {"limit": 3})

    assert result.is_error is False
    assert analytics.calls == [("stockout", caller, 3)]


@pytest.mark.asyncio
async def test_mcp_cannot_bypass_existing_role_policy() -> None:
    repository = EmptyRepository()
    analytics = GovernedAnalyticsService(repository)
    server = build_mcp_server(
        settings=settings(),
        tool_service=tool_service(analytics=analytics),
        token_verifier=AcceptingVerifier(),
        auth_provider=lambda: auth(UserRole.SUPPORT_INTERN),
    )

    async with Client(server) as client:
        result = await client.call_tool("get_stockout_risks", {"limit": 3})

    assert result.is_error is True
    assert repository.calls == []


@pytest.mark.asyncio
async def test_invalid_identifier_is_rejected_before_tool_service() -> None:
    analytics = RecordingAnalytics()
    server = build_mcp_server(
        settings=settings(),
        tool_service=tool_service(analytics=analytics),
        token_verifier=AcceptingVerifier(),
        auth_provider=auth,
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "reconcile_freight",
            {"shipment_id": "x' OR '1'='1"},
        )

    assert result.is_error is True
    assert analytics.calls == []


def test_mcp_fails_closed_without_auth0_configuration() -> None:
    with pytest.raises(RuntimeError, match="requires Auth0"):
        build_mcp_server(
            settings=Settings(_env_file=None, auth_mode="mock"),
            tool_service=tool_service(),
        )


def test_streamable_http_rejects_requests_without_bearer_token() -> None:
    server = build_mcp_server(
        settings=settings(),
        tool_service=tool_service(),
        token_verifier=AcceptingVerifier(),
        auth_provider=auth,
    )
    app = server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"
    assert "resource_metadata=" in response.headers["WWW-Authenticate"]
