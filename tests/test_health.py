from fastapi.testclient import TestClient

from business_brain.main import app


def test_health_returns_public_runtime_metadata() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Business Brain",
        "environment": "test",
        "auth_mode": "mock",
    }


def test_health_does_not_expose_secrets() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/v1/health").text.lower()

    assert "api_key" not in payload
    assert "secret" not in payload

