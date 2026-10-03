from datetime import date
from enum import StrEnum
from typing import Any, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from business_brain.llm.schemas import TokenUsage
from business_brain.retrieval.schemas import DocumentCitation


class AgentRoute(StrEnum):
    SQL_ANALYTICS = "sql_analytics"
    DOCUMENT_RETRIEVAL = "document_retrieval"
    ACTION_DRAFTING = "action_drafting"
    DIRECT_RESPONSE = "direct_response"
    REFUSE = "refuse"


class SupervisorIntent(StrEnum):
    STOCKOUT_RISK = "stockout_risk"
    FREIGHT_RECONCILIATION = "freight_reconciliation"
    SUPPLIER_TERMS = "supplier_terms"
    OVERDUE_INVOICES = "overdue_invoices"
    MARGIN_ANALYSIS = "margin_analysis"
    DRAFT_PURCHASE_ORDER = "draft_purchase_order"
    DRAFT_CARRIER_DISPUTE = "draft_carrier_dispute"
    DRAFT_PAYMENT_REMINDER = "draft_payment_reminder"
    DRAFT_DELAY_ADVISORY = "draft_delay_advisory"
    GENERAL_DOCUMENT_QUESTION = "general_document_question"
    GENERAL_CONVERSATION = "general_conversation"
    UNSUPPORTED = "unsupported"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WorkflowStatus(StrEnum):
    COMPLETED = "completed"
    ROUTED = "routed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REFUSED = "refused"
    FAILED = "failed"


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shipment_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]+$",
        max_length=80,
    )
    as_of: date | None = None
    region_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]+$",
        max_length=80,
    )
    earlier: date | None = None
    later: date | None = None
    limit: int | None = Field(default=None, ge=1, le=20)


class SupervisorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: AgentRoute
    intent: SupervisorIntent
    risk_level: RiskLevel
    rationale: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    arguments: ToolArguments = Field(default_factory=ToolArguments)


class AgentState(TypedDict, total=False):
    request_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    role: str
    question: str
    max_tokens: int
    route: str
    intent: str
    risk_level: str
    rationale: str
    confidence: float
    arguments: dict[str, Any]
    status: str
    answer: str
    error_code: str
    model: str
    provider: str
    used_fallback: bool
    attempt_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    supervisor_attempts: int
    tool_name: str
    tool_result: Any
    citations: list[dict[str, Any]]
    action_draft: dict[str, Any]
    approval: dict[str, Any]


class AgentRunResult(BaseModel):
    request_id: str
    thread_id: str
    answer: str
    route: AgentRoute
    intent: SupervisorIntent
    risk_level: RiskLevel
    status: WorkflowStatus
    rationale: str
    error_code: str | None = None
    model: str | None = None
    provider: str | None = None
    used_fallback: bool = False
    attempt_count: int = 0
    supervisor_attempts: int = 1
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_name: str | None = None
    tool_result: Any | None = None
    citations: list[DocumentCitation] = Field(default_factory=list)
    action_draft: Any | None = None
    approval: Any | None = None
