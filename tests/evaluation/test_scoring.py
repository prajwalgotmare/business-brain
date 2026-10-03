from pathlib import Path

import pytest

from business_brain.agent.schemas import AgentRoute, SupervisorIntent, WorkflowStatus
from business_brain.evaluation.models import GoldenEvaluationManifest
from business_brain.evaluation.scoring import (
    EvaluationObservation,
    aggregate_metrics,
    score_case,
)
from business_brain.retrieval.schemas import DocumentCitation

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evaluation" / "golden_dataset.json"


def load_cases():
    return GoldenEvaluationManifest.model_validate_json(
        DATASET_PATH.read_text(encoding="utf-8")
    ).cases


def perfect_observation(case, *, latency_ms: float = 10.0) -> EvaluationObservation:
    action_draft = None
    approval = None
    if case.approval:
        action_draft = {
            "risk_level": case.approval.risk_level.value,
                "approval_required": True,
                "submission_allowed": False,
                "execution_status": "draft",
            "required_approver_roles": [
                role.value for role in case.approval.approver_roles
            ],
        }
        approval = {"status": "pending"}
    answer = " ".join(case.must_include) or case.expected_summary
    return EvaluationObservation(
        case_id=case.case_id,
        answer=answer,
        route=case.expected_route,
        intent=case.expected_intent,
        status=case.expected_status,
        tool_name=case.expected_tool,
        error_code=case.expected_error_code,
        citations=[
            DocumentCitation(
                document_id=item.document_id,
                title="Expected document",
                page_number=item.page_number,
                clause_id=item.clause_id,
                chunk_id=f"chunk_{item.document_id}",
            )
            for item in case.expected_citations
        ],
        action_draft=action_draft,
        approval=approval,
        structured_evidence={"expected": case.must_include},
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        latency_ms=latency_ms,
        ragas_faithfulness=0.9 if case.expected_citations else None,
        ragas_factual_correctness=0.8 if case.expected_citations else None,
    )


def test_perfect_observations_produce_complete_deterministic_scores() -> None:
    cases = load_cases()
    observations = [perfect_observation(case) for case in cases]

    metrics, scores = aggregate_metrics(cases, observations)

    assert len(scores) == 50
    assert metrics.routing_accuracy == 1.0
    assert metrics.workflow_accuracy == 1.0
    assert metrics.tool_accuracy == 1.0
    assert metrics.permission_accuracy == 1.0
    assert metrics.citation_exact_accuracy == 1.0
    assert metrics.citation_precision == 1.0
    assert metrics.citation_recall == 1.0
    assert metrics.action_policy_accuracy == 1.0
    assert metrics.task_success_rate == 1.0
    assert metrics.ragas_case_count == 10
    assert metrics.ragas_groundedness == 0.9
    assert metrics.ragas_factual_correctness == 0.8
    assert metrics.total_tokens == 750


def test_document_success_requires_expected_citation_but_allows_extra_context() -> None:
    case = next(item for item in load_cases() if item.expected_citations)
    observed = perfect_observation(case)
    observed.citations.append(
        DocumentCitation(
            document_id="doc_extra",
            title="Extra supporting document",
            page_number=1,
            chunk_id="chunk_extra",
        )
    )

    score = score_case(case, observed)

    assert score.citations_exact is False
    assert score.citation_recall == 1.0
    assert score.citation_precision == 0.5
    assert score.task_success is True


def test_action_policy_and_runtime_errors_fail_the_case() -> None:
    case = next(item for item in load_cases() if item.approval)
    observed = perfect_observation(case)
    observed.action_draft["submission_allowed"] = True
    observed.runtime_error = "evaluation runner failure"

    score = score_case(case, observed)

    assert score.action_policy_correct is False
    assert score.task_success is False


def test_refusal_must_fail_closed_without_a_tool() -> None:
    case = next(item for item in load_cases() if item.expected_error_code)
    observed = perfect_observation(case)
    observed.tool_name = "search_documents"

    score = score_case(case, observed)

    assert score.permission_correct is False
    assert score.task_success is False


def test_aggregate_rejects_missing_or_duplicate_observations() -> None:
    cases = load_cases()[:2]
    one = perfect_observation(cases[0])

    with pytest.raises(ValueError, match="cover every supplied"):
        aggregate_metrics(cases, [one])
    with pytest.raises(ValueError, match="must be unique"):
        aggregate_metrics(cases, [one, one])


def test_route_mismatch_is_detected() -> None:
    case = load_cases()[0]
    observed = perfect_observation(case)
    observed.route = AgentRoute.REFUSE
    observed.intent = SupervisorIntent.UNSUPPORTED
    observed.status = WorkflowStatus.REFUSED

    score = score_case(case, observed)

    assert score.routing_correct is False
    assert score.workflow_correct is False
    assert score.task_success is False
