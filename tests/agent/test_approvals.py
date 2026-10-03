from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from business_brain.agent.approvals import (
    ApprovalDecision,
    ApprovalRecord,
    ApprovalResumeCommand,
    ApprovalStatus,
    decide_approval,
)
from business_brain.agent.schemas import RiskLevel, SupervisorIntent
from business_brain.security.context import UserRole


def pending() -> ApprovalRecord:
    return ApprovalRecord(
        approval_id="approval_0123456789abcdef",
        draft_id="draft_0123456789abcdef",
        tenant_id="tenant_aura",
        action_type=SupervisorIntent.DRAFT_CARRIER_DISPUTE,
        risk_level=RiskLevel.HIGH,
        required_approver_roles=[UserRole.FOUNDER_CFO],
    )


def command(
    *,
    decision: ApprovalDecision = ApprovalDecision.APPROVE,
    tenant_id: str = "tenant_aura",
    role: UserRole = UserRole.FOUNDER_CFO,
) -> ApprovalResumeCommand:
    return ApprovalResumeCommand(
        decision=decision,
        tenant_id=tenant_id,
        approver_user_id="demo-cfo",
        approver_role=role,
        decided_at=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
        comment="Evidence reviewed",
    )


@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        (ApprovalDecision.APPROVE, ApprovalStatus.APPROVED),
        (ApprovalDecision.REJECT, ApprovalStatus.REJECTED),
    ],
)
def test_authorized_human_can_decide_pending_approval(decision, expected) -> None:
    result = decide_approval(pending(), command(decision=decision))

    assert result.status == expected
    assert result.decided_by_user_id == "demo-cfo"
    assert result.decided_by_role == UserRole.FOUNDER_CFO
    assert result.decided_at is not None


def test_wrong_tenant_and_role_are_rejected() -> None:
    with pytest.raises(PermissionError, match="tenant"):
        decide_approval(pending(), command(tenant_id="tenant_apex"))
    with pytest.raises(PermissionError, match="role"):
        decide_approval(pending(), command(role=UserRole.LOGISTICS_MANAGER))


def test_pending_record_cannot_claim_a_decision_identity() -> None:
    with pytest.raises(ValidationError, match="pending approval"):
        ApprovalRecord(
            approval_id="approval_0123456789abcdef",
            draft_id="draft_0123456789abcdef",
            tenant_id="tenant_aura",
            action_type=SupervisorIntent.DRAFT_CARRIER_DISPUTE,
            risk_level=RiskLevel.HIGH,
            required_approver_roles=[UserRole.FOUNDER_CFO],
            decided_by_user_id="fake-approver",
        )


def test_decided_record_requires_complete_audit_identity() -> None:
    with pytest.raises(ValidationError, match="requires approver"):
        ApprovalRecord(
            approval_id="approval_0123456789abcdef",
            draft_id="draft_0123456789abcdef",
            tenant_id="tenant_aura",
            action_type=SupervisorIntent.DRAFT_CARRIER_DISPUTE,
            risk_level=RiskLevel.HIGH,
            required_approver_roles=[UserRole.FOUNDER_CFO],
            status=ApprovalStatus.APPROVED,
        )
