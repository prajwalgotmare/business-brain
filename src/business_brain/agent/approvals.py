from enum import StrEnum
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from business_brain.agent.actions import ActionDraftArtifact
from business_brain.agent.schemas import RiskLevel, SupervisorIntent
from business_brain.data.models import Identifier, StrictModel
from business_brain.security.context import UserRole

ApprovalComment = Annotated[str, StringConstraints(min_length=2, max_length=500)]


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalRecord(StrictModel):
    approval_id: Identifier
    draft_id: Identifier
    tenant_id: Identifier
    action_type: SupervisorIntent
    risk_level: RiskLevel
    required_approver_roles: Annotated[list[UserRole], Field(min_length=1)]
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_by_user_id: str | None = None
    decided_by_role: UserRole | None = None
    decided_at: AwareDatetime | None = None
    comment: ApprovalComment | None = None

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "ApprovalRecord":
        decision_fields = (
            self.decided_by_user_id,
            self.decided_by_role,
            self.decided_at,
        )
        if self.status == ApprovalStatus.PENDING and any(
            value is not None for value in decision_fields
        ):
            raise ValueError("pending approval cannot contain a decision")
        if self.status != ApprovalStatus.PENDING and any(
            value is None for value in decision_fields
        ):
            raise ValueError("completed approval requires approver identity and time")
        return self


class ApprovalResumeCommand(StrictModel):
    decision: ApprovalDecision
    tenant_id: Identifier
    approver_user_id: Annotated[str, StringConstraints(min_length=2, max_length=100)]
    approver_role: UserRole
    decided_at: AwareDatetime
    comment: ApprovalComment | None = None


def pending_approval(artifact: ActionDraftArtifact) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=f"approval_{artifact.draft_id.removeprefix('draft_')}",
        draft_id=artifact.draft_id,
        tenant_id=artifact.tenant_id,
        action_type=artifact.action_type,
        risk_level=artifact.risk_level,
        required_approver_roles=artifact.required_approver_roles,
    )


def decide_approval(
    record: ApprovalRecord,
    command: ApprovalResumeCommand,
) -> ApprovalRecord:
    if record.status != ApprovalStatus.PENDING:
        raise ValueError("approval is no longer pending")
    if command.tenant_id != record.tenant_id:
        raise PermissionError("approval tenant does not match")
    if command.approver_role not in record.required_approver_roles:
        raise PermissionError("role cannot approve this action")
    status = (
        ApprovalStatus.APPROVED
        if command.decision == ApprovalDecision.APPROVE
        else ApprovalStatus.REJECTED
    )
    return record.model_copy(
        update={
            "status": status,
            "decided_by_user_id": command.approver_user_id,
            "decided_by_role": command.approver_role,
            "decided_at": command.decided_at,
            "comment": command.comment,
        }
    )


class ApprovalNotFoundError(LookupError):
    pass


class ApprovalForbiddenError(PermissionError):
    pass


class ApprovalConflictError(RuntimeError):
    pass
