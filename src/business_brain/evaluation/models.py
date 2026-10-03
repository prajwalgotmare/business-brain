"""Strict contracts for the versioned golden evaluation dataset."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from business_brain.agent.schemas import (
    AgentRoute,
    RiskLevel,
    SupervisorIntent,
    WorkflowStatus,
)
from business_brain.data.models import Identifier, StrictModel
from business_brain.security.context import UserRole


class EvaluationCategory(StrEnum):
    SQL_ANALYTICS = "sql_analytics"
    DOCUMENT_RETRIEVAL = "document_retrieval"
    ACTION_DRAFTING = "action_drafting"
    AUTHORIZATION_REFUSAL = "authorization_refusal"
    DIRECT_RESPONSE = "direct_response"
    UNSUPPORTED = "unsupported"


class CitationExpectation(StrictModel):
    document_id: Identifier
    page_number: int = Field(ge=1)
    clause_id: Identifier | None = None


class ApprovalExpectation(StrictModel):
    required: Literal[True] = True
    risk_level: RiskLevel
    approver_roles: Annotated[list[UserRole], Field(min_length=1)]
    submission_allowed: Literal[False] = False


class GoldenEvaluationCase(StrictModel):
    case_id: Annotated[str, Field(pattern=r"^gold_\d{3}$")]
    tenant_id: Literal["tenant_aura"] = "tenant_aura"
    role: UserRole
    category: EvaluationCategory
    question: Annotated[str, Field(min_length=3, max_length=500)]
    expected_route: AgentRoute
    expected_intent: SupervisorIntent
    expected_status: WorkflowStatus
    expected_tool: str | None = None
    expected_error_code: str | None = None
    expected_summary: Annotated[str, Field(min_length=3, max_length=600)]
    expected_facts: dict[Identifier, str] = Field(default_factory=dict)
    expected_citations: list[CitationExpectation] = Field(default_factory=list)
    approval: ApprovalExpectation | None = None
    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    source_scenario_id: Identifier | None = None
    tags: Annotated[list[str], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_expected_behavior(self) -> GoldenEvaluationCase:
        if self.category == EvaluationCategory.DOCUMENT_RETRIEVAL:
            if not self.expected_citations:
                raise ValueError("document retrieval cases require a citation")
        elif self.expected_citations:
            raise ValueError("only document retrieval cases may require citations")
        if self.category == EvaluationCategory.ACTION_DRAFTING:
            if self.approval is None or self.expected_status != WorkflowStatus.PENDING_APPROVAL:
                raise ValueError("action cases require a pending approval expectation")
        elif self.approval is not None:
            raise ValueError("only action cases may define approval expectations")
        if self.category in {
            EvaluationCategory.AUTHORIZATION_REFUSAL,
            EvaluationCategory.UNSUPPORTED,
        }:
            if self.expected_status != WorkflowStatus.REFUSED or not self.expected_error_code:
                raise ValueError("refusal cases require a refusal status and error code")
        elif self.expected_error_code is not None:
            raise ValueError("answerable cases cannot define an error code")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("case tags must be unique")
        return self


class GoldenEvaluationManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    dataset_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    case_count: Literal[50] = 50
    cases: Annotated[list[GoldenEvaluationCase], Field(min_length=50, max_length=50)]

    @model_validator(mode="after")
    def validate_dataset(self) -> GoldenEvaluationManifest:
        ids = [case.case_id for case in self.cases]
        questions = [case.question.casefold() for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("golden case IDs must be unique")
        if len(questions) != len(set(questions)):
            raise ValueError("golden questions must be unique")
        expected_counts = {
            EvaluationCategory.SQL_ANALYTICS: 16,
            EvaluationCategory.DOCUMENT_RETRIEVAL: 10,
            EvaluationCategory.ACTION_DRAFTING: 8,
            EvaluationCategory.AUTHORIZATION_REFUSAL: 12,
            EvaluationCategory.DIRECT_RESPONSE: 2,
            EvaluationCategory.UNSUPPORTED: 2,
        }
        actual = {
            category: sum(case.category == category for case in self.cases)
            for category in EvaluationCategory
        }
        if actual != expected_counts:
            raise ValueError("golden dataset category distribution is invalid")
        return self
