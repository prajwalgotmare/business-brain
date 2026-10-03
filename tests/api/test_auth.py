from fastapi.testclient import TestClient

from business_brain.api.dependencies import get_auth0_validator
from business_brain.core.config import Settings, get_settings
from business_brain.main import app
from business_brain.security.context import AuthContext, UserRole


class StubAuth0Validator:
    def __init__(self) -> None:
        self.tokens = []

    async def validate(self, token: str) -> AuthContext:
        self.tokens.append(token)
        return AuthContext(
            tenant_id="tenant_aura",
            user_id="auth0|demo-cfo",
            role=UserRole.FOUNDER_CFO,
        )


def auth0_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        auth_mode="auth0",
        auth0_domain="example.us.auth0.com",
        auth0_audience="https://api.aura-business-brain.demo",
        agent_checkpoint_backend="memory",
    )


def test_auth0_identity_comes_from_token_not_spoofable_headers() -> None:
    validator = StubAuth0Validator()
    app.dependency_overrides[get_settings] = auth0_settings
    app.dependency_overrides[get_auth0_validator] = lambda: validator
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/auth/me",
                headers={
                    "Authorization": "Bearer signed-token",
                    "X-Tenant-ID": "tenant_apex",
                    "X-User-ID": "attacker",
                    "X-Role": "support_intern",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "tenant_id": "tenant_aura",
        "user_id": "auth0|demo-cfo",
        "role": "founder_cfo",
    }
    assert validator.tokens == ["signed-token"]


def test_auth0_mode_requires_bearer_token() -> None:
    app.dependency_overrides[get_settings] = auth0_settings
    app.dependency_overrides[get_auth0_validator] = StubAuth0Validator
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "invalid_authentication"


def test_mock_mode_still_accepts_development_headers() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/auth/me",
            headers={
                "X-Tenant-ID": "tenant_aura",
                "X-User-ID": "demo-accountant",
                "X-Role": "staff_accountant",
            },
        )

    assert response.status_code == 200
    assert response.json()["role"] == "staff_accountant"
