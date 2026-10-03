from uuid import UUID

from fastapi.testclient import TestClient

from business_brain.api.dependencies import get_generation_tracer, get_llm_gateway
from business_brain.llm.gateway import AllModelsFailedError
from business_brain.llm.schemas import GenerationRequest, GenerationResult, TokenUsage
from business_brain.main import app
from business_brain.observability.tracing import GenerationTraceContext


class StubGateway:
    def __init__(
        self,
        result: GenerationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[GenerationRequest] = []

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result


class RecordingTracer:
    def __init__(self) -> None:
        self.contexts: list[GenerationTraceContext] = []
        self.primary_models: list[str] = []

    async def trace_generation(self, *, context, request, primary_model, operation):
        self.contexts.append(context)
        self.primary_models.append(primary_model)
        return await operation()

    def flush(self) -> None:
        return None


AUTH_HEADERS = {
    "X-Tenant-ID": "aura-brands",
    "X-User-ID": "demo-cfo",
    "X-Role": "founder_cfo",
}


def successful_gateway() -> StubGateway:
    return StubGateway(
        result=GenerationResult(
            content="Business data is not connected yet.",
            model="openai/gpt-oss-120b",
            usage=TokenUsage(prompt_tokens=20, completion_tokens=8, total_tokens=28),
        )
    )


def test_ask_returns_typed_generation_and_context() -> None:
    gateway = successful_gateway()
    app.dependency_overrides[get_llm_gateway] = lambda: gateway

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                headers=AUTH_HEADERS,
                json={"question": "Which SKUs are at risk?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    UUID(body["request_id"])
    UUID(body["thread_id"])
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert body["answer"] == "Business data is not connected yet."
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["used_fallback"] is False
    assert body["usage"]["total_tokens"] == 28
    assert body["context"] == {"tenant_id": "aura-brands", "role": "founder_cfo"}

    sent_request = gateway.requests[0]
    assert sent_request.messages[1].content == "Which SKUs are at risk?"
    assert "aura-brands" in sent_request.messages[0].content
    assert "founder_cfo" in sent_request.messages[0].content
    assert "demo-cfo" not in sent_request.messages[0].content


def test_ask_preserves_valid_request_and_thread_ids() -> None:
    gateway = successful_gateway()
    app.dependency_overrides[get_llm_gateway] = lambda: gateway
    request_id = "d757cba8-39c0-4fca-a433-2b12a28b1d81"
    thread_id = "93854ae6-41ac-4586-96c2-65f0ad630225"

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                headers={**AUTH_HEADERS, "X-Request-ID": request_id},
                json={"question": "Summarize carrier risk", "thread_id": thread_id},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.json()["thread_id"] == thread_id


def test_ask_sends_safe_request_context_to_tracing() -> None:
    gateway = successful_gateway()
    tracer = RecordingTracer()
    app.dependency_overrides[get_llm_gateway] = lambda: gateway
    app.dependency_overrides[get_generation_tracer] = lambda: tracer

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                headers=AUTH_HEADERS,
                json={"question": "Summarize carrier risk"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    context = tracer.contexts[0]
    assert context.request_id == response.json()["request_id"]
    assert context.thread_id == response.json()["thread_id"]
    assert context.tenant_id == "aura-brands"
    assert context.role.value == "founder_cfo"
    assert not hasattr(context, "user_id")
    assert tracer.primary_models == ["openai/gpt-oss-120b"]


def test_missing_auth_headers_returns_sanitized_authentication_error() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"question": "Show inventory risk"})

    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "invalid_authentication"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    UUID(body["error"]["request_id"])
    assert "input" not in response.text.lower()
    assert "groq" not in response.text.lower()


def test_invalid_role_is_rejected_before_generation() -> None:
    gateway = successful_gateway()
    app.dependency_overrides[get_llm_gateway] = lambda: gateway

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                headers={**AUTH_HEADERS, "X-Role": "admin"},
                json={"question": "Show profit margins"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_authentication"
    assert gateway.requests == []


def test_provider_failure_returns_safe_service_error() -> None:
    gateway = StubGateway(error=AllModelsFailedError("internal provider details"))
    app.dependency_overrides[get_llm_gateway] = lambda: gateway

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ask",
                headers=AUTH_HEADERS,
                json={"question": "Show overdue invoices"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "llm_service_unavailable"
    assert "internal provider details" not in response.text
    assert "groq" not in response.text.lower()


def test_blank_question_is_rejected_without_echoing_input() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/ask",
            headers=AUTH_HEADERS,
            json={"question": "  "},
        )

    assert response.status_code == 422
    assert '"input"' not in response.text

