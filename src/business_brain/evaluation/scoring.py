"""Deterministic and RAGAS-backed quality scoring for golden evaluation runs."""

from __future__ import annotations

import json
import re
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from business_brain.agent.schemas import (
    AgentRoute,
    SupervisorIntent,
    WorkflowStatus,
)
from business_brain.evaluation.models import (
    EvaluationCategory,
    GoldenEvaluationCase,
)
from business_brain.retrieval.schemas import DocumentCitation


class EvaluationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    answer: str
    route: AgentRoute
    intent: SupervisorIntent
    status: WorkflowStatus
    tool_name: str | None = None
    error_code: str | None = None
    citations: list[DocumentCitation] = Field(default_factory=list)
    action_draft: dict[str, Any] | None = None
    approval: dict[str, Any] | None = None
    structured_evidence: Any | None = None
    retrieved_contexts: list[str] = Field(default_factory=list)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(ge=0)
    model: str | None = None
    provider: str | None = None
    used_fallback: bool = False
    attempt_count: int = Field(default=0, ge=0)
    ragas_faithfulness: float | None = Field(default=None, ge=0, le=1)
    ragas_factual_correctness: float | None = Field(default=None, ge=0, le=1)
    runtime_error: str | None = None


class CaseScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    routing_correct: bool
    workflow_correct: bool
    tool_correct: bool
    content_constraints_correct: bool
    permission_correct: bool | None = None
    citations_exact: bool | None = None
    citation_precision: float | None = Field(default=None, ge=0, le=1)
    citation_recall: float | None = Field(default=None, ge=0, le=1)
    action_policy_correct: bool | None = None
    task_success: bool


class EvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(gt=0)
    routing_accuracy: float = Field(ge=0, le=1)
    workflow_accuracy: float = Field(ge=0, le=1)
    tool_accuracy: float = Field(ge=0, le=1)
    content_constraint_accuracy: float = Field(ge=0, le=1)
    permission_accuracy: float = Field(ge=0, le=1)
    citation_exact_accuracy: float = Field(ge=0, le=1)
    citation_precision: float = Field(ge=0, le=1)
    citation_recall: float = Field(ge=0, le=1)
    action_policy_accuracy: float = Field(ge=0, le=1)
    task_success_rate: float = Field(ge=0, le=1)
    ragas_case_count: int = Field(ge=0)
    ragas_groundedness: float | None = Field(default=None, ge=0, le=1)
    ragas_factual_correctness: float | None = Field(default=None, ge=0, le=1)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    mean_latency_ms: float = Field(ge=0)
    fallback_case_count: int = Field(ge=0)
    runtime_error_count: int = Field(ge=0)


def _text_key(value: str) -> str:
    normalized = value.casefold().replace(",", "").replace("$", "")
    normalized = normalized.translate(str.maketrans({"‑": "-", "–": "-", "—": "-"}))
    normalized = re.sub(r"\s+%", "%", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _citation_key(citation: Any) -> tuple[str, int, str | None]:
    return (citation.document_id, citation.page_number, citation.clause_id)


def _ratio(values: list[bool]) -> float:
    return round(sum(values) / len(values), 6) if values else 1.0


def score_case(case: GoldenEvaluationCase, observed: EvaluationObservation) -> CaseScore:
    if case.case_id != observed.case_id:
        raise ValueError("case and observation IDs do not match")
    routing_correct = (
        observed.route == case.expected_route and observed.intent == case.expected_intent
    )
    workflow_correct = (
        observed.status == case.expected_status
        and observed.error_code == case.expected_error_code
    )
    tool_correct = observed.tool_name == case.expected_tool

    evidence = (
        json.dumps(observed.structured_evidence, sort_keys=True, default=str)
        if observed.structured_evidence is not None
        else ""
    )
    answer = _text_key(f"{observed.answer} {evidence}")
    included = all(_text_key(value) in answer for value in case.must_include)
    excluded = all(_text_key(value) not in answer for value in case.must_not_include)
    if case.category == EvaluationCategory.ACTION_DRAFTING:
        # A safe draft may explicitly explain that it cannot be submitted/sent.
        # Enforce non-execution using the typed artifact instead of keyword absence.
        draft = observed.action_draft or {}
        excluded = (
            draft.get("execution_status") == "draft"
            and draft.get("submission_allowed") is False
        )
    content_correct = included and excluded

    permission_correct = None
    if case.category in {
        EvaluationCategory.AUTHORIZATION_REFUSAL,
        EvaluationCategory.UNSUPPORTED,
    }:
        permission_correct = (
            observed.status == WorkflowStatus.REFUSED
            and observed.tool_name is None
            and observed.error_code == case.expected_error_code
        )

    citations_exact = None
    citation_precision = None
    citation_recall = None
    if case.category == EvaluationCategory.DOCUMENT_RETRIEVAL:
        expected = {_citation_key(item) for item in case.expected_citations}
        actual = {_citation_key(item) for item in observed.citations}
        overlap = expected & actual
        citations_exact = actual == expected
        citation_precision = len(overlap) / len(actual) if actual else 0.0
        citation_recall = len(overlap) / len(expected) if expected else 1.0

    action_policy_correct = None
    if case.category == EvaluationCategory.ACTION_DRAFTING:
        draft = observed.action_draft or {}
        approval = observed.approval or {}
        expected = case.approval
        action_policy_correct = bool(
            expected
            and draft.get("risk_level") == expected.risk_level.value
            and draft.get("approval_required") is True
            and draft.get("submission_allowed") is False
            and draft.get("required_approver_roles")
            == [role.value for role in expected.approver_roles]
            and approval.get("status") == "pending"
        )

    checks = [routing_correct, workflow_correct, tool_correct, content_correct]
    checks.extend(
        value
        for value in (permission_correct, action_policy_correct)
        if value is not None
    )
    if citation_recall is not None:
        checks.append(citation_recall == 1.0)
    checks.append(observed.runtime_error is None)
    return CaseScore(
        case_id=case.case_id,
        routing_correct=routing_correct,
        workflow_correct=workflow_correct,
        tool_correct=tool_correct,
        content_constraints_correct=content_correct,
        permission_correct=permission_correct,
        citations_exact=citations_exact,
        citation_precision=(
            round(citation_precision, 6) if citation_precision is not None else None
        ),
        citation_recall=round(citation_recall, 6) if citation_recall is not None else None,
        action_policy_correct=action_policy_correct,
        task_success=all(checks),
    )


def aggregate_metrics(
    cases: list[GoldenEvaluationCase], observations: list[EvaluationObservation]
) -> tuple[EvaluationMetrics, list[CaseScore]]:
    by_id = {item.case_id: item for item in observations}
    if len(by_id) != len(observations):
        raise ValueError("observation IDs must be unique")
    if set(by_id) != {case.case_id for case in cases}:
        raise ValueError("observations must cover every supplied golden case exactly once")
    scores = [score_case(case, by_id[case.case_id]) for case in cases]

    permission = [item.permission_correct for item in scores if item.permission_correct is not None]
    citation_exact = [item.citations_exact for item in scores if item.citations_exact is not None]
    citation_precision = [
        item.citation_precision for item in scores if item.citation_precision is not None
    ]
    citation_recall = [
        item.citation_recall for item in scores if item.citation_recall is not None
    ]
    actions = [
        item.action_policy_correct
        for item in scores
        if item.action_policy_correct is not None
    ]
    ragas = [item for item in observations if item.ragas_faithfulness is not None]

    metrics = EvaluationMetrics(
        case_count=len(cases),
        routing_accuracy=_ratio([item.routing_correct for item in scores]),
        workflow_accuracy=_ratio([item.workflow_correct for item in scores]),
        tool_accuracy=_ratio([item.tool_correct for item in scores]),
        content_constraint_accuracy=_ratio(
            [item.content_constraints_correct for item in scores]
        ),
        permission_accuracy=_ratio(permission),
        citation_exact_accuracy=_ratio(citation_exact),
        citation_precision=round(mean(citation_precision), 6) if citation_precision else 1.0,
        citation_recall=round(mean(citation_recall), 6) if citation_recall else 1.0,
        action_policy_accuracy=_ratio(actions),
        task_success_rate=_ratio([item.task_success for item in scores]),
        ragas_case_count=len(ragas),
        ragas_groundedness=(
            round(mean(item.ragas_faithfulness for item in ragas), 6) if ragas else None
        ),
        ragas_factual_correctness=(
            round(
                mean(
                    item.ragas_factual_correctness
                    for item in ragas
                    if item.ragas_factual_correctness is not None
                ),
                6,
            )
            if ragas
            and all(item.ragas_factual_correctness is not None for item in ragas)
            else None
        ),
        prompt_tokens=sum(item.prompt_tokens for item in observations),
        completion_tokens=sum(item.completion_tokens for item in observations),
        total_tokens=sum(item.total_tokens for item in observations),
        mean_latency_ms=round(mean(item.latency_ms for item in observations), 2),
        fallback_case_count=sum(item.used_fallback for item in observations),
        runtime_error_count=sum(item.runtime_error is not None for item in observations),
    )
    return metrics, scores
