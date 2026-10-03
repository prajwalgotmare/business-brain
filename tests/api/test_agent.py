from uuid import UUID

from fastapi.testclient import TestClient

from business_brain.agent.schemas import (
    AgentRoute,
    AgentRunResult,
    RiskLevel,
    SupervisorIntent,
    WorkflowStatus,
)
from business_brain.api.dependencies import get_governed_supervisor
from business_brain.llm.schemas import TokenUsage
from business_brain.main import app

HEADERS = {
    "X-Tenant-ID": "tenant_aura",
    "X-User-ID": "demo-logistics",
    "X-Role": "logistics_manager",
    "X-Request-ID": "79cb68c1-95ac-421b-8f16-6499b99bc744",
}


class StubSupervisor:
    def __init__(self) -> None:
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return AgentRunResult(
            request_id=kwargs["request_id"],
            thread_id=kwargs["thread_id"],
            answer="Authorized and routed.",
            route=AgentRoute.SQL_ANALYTICS,
            intent=SupervisorIntent.STOCKOUT_RISK,
            risk_level=RiskLevel.LOW,
            status=WorkflowStatus.ROUTED,
            rationale="Needs inventory analytics",
            model="openai/gpt-oss-120b",
            provider="groq",
            attempt_count=1,
            usage=TokenUsage(total_tokens=20),
        )


def test_agent_endpoint_preserves_authenticated_context() -> None:
    supervisor = StubSupervisor()
    app.dependency_overrides[get_governed_supervisor] = lambda: supervisor
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/agent/run",
                headers=HEADERS,
                json={"question": "Which SKUs may stock out this week?"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    UUID(payload["thread_id"])
    assert payload["request_id"] == HEADERS["X-Request-ID"]
    assert payload["route"] == "sql_analytics"
    assert payload["context"] == {
        "tenant_id": "tenant_aura",
        "role": "logistics_manager",
    }
    assert supervisor.calls[0]["auth"].tenant_id == "tenant_aura"
