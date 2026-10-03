from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from business_brain.agent.approvals import (
    ApprovalConflictError,
    ApprovalDecision,
    ApprovalForbiddenError,
    ApprovalNotFoundError,
    ApprovalRecord,
    ApprovalStatus,
)
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
    def __init__(self, approval_error=None) -> None:
        self.calls = []
        self.approval_error = approval_error

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

    async def resume_approval(self, **kwargs):
        self.calls.append(kwargs)
        if self.approval_error:
            raise self.approval_error
        return AgentRunResult(
            request_id=kwargs["request_id"],
            thread_id=kwargs["thread_id"],
            answer="Approved and unexecuted.",
            route=AgentRoute.ACTION_DRAFTING,
            intent=SupervisorIntent.DRAFT_PURCHASE_ORDER,
            risk_level=RiskLevel.HIGH,
            status=WorkflowStatus.APPROVED,
            rationale="Requested purchase-order draft",
            approval=ApprovalRecord(
                approval_id="approval_0123456789abcdef",
                draft_id="draft_0123456789abcdef",
                tenant_id="tenant_aura",
                action_type=SupervisorIntent.DRAFT_PURCHASE_ORDER,
                risk_level=RiskLevel.HIGH,
                required_approver_roles=["founder_cfo"],
                status=ApprovalStatus.APPROVED,
                decided_by_user_id=kwargs["auth"].user_id,
                decided_by_role=kwargs["auth"].role,
                decided_at=datetime.now(UTC),
                comment=kwargs["comment"],
            ),
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


def test_approval_endpoint_uses_authenticated_approver() -> None:
    supervisor = StubSupervisor()
    app.dependency_overrides[get_governed_supervisor] = lambda: supervisor
    thread_id = "9c825d3b-b21c-4425-87f4-416597203a3b"
    headers = HEADERS | {"X-Role": "founder_cfo", "X-User-ID": "demo-cfo"}
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/agent/threads/{thread_id}/approval",
                headers=headers,
                json={"decision": "approve", "comment": "Reviewed and approved"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "approved"
    assert payload["approval"]["decided_by_user_id"] == "demo-cfo"
    assert supervisor.calls[0]["decision"] == ApprovalDecision.APPROVE
    assert supervisor.calls[0]["auth"].role.value == "founder_cfo"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (ApprovalNotFoundError("missing"), 404, "approval_not_found"),
        (ApprovalForbiddenError("denied"), 403, "approval_forbidden"),
        (ApprovalConflictError("decided"), 409, "approval_conflict"),
    ],
)
def test_approval_endpoint_returns_sanitized_errors(error, status_code, code) -> None:
    supervisor = StubSupervisor(approval_error=error)
    app.dependency_overrides[get_governed_supervisor] = lambda: supervisor
    thread_id = "9c825d3b-b21c-4425-87f4-416597203a3b"
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/agent/threads/{thread_id}/approval",
                headers=HEADERS,
                json={"decision": "reject"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert str(error) not in response.text
