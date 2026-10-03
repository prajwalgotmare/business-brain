import json
from collections import Counter
from pathlib import Path

from business_brain.agent.actions import get_action_policy
from business_brain.agent.schemas import AgentRoute, SupervisorIntent, WorkflowStatus
from business_brain.evaluation.golden_generator import build_golden_manifest
from business_brain.evaluation.models import (
    EvaluationCategory,
    GoldenEvaluationManifest,
)
from business_brain.security.policy import Capability, role_has_capability

ROOT = Path(__file__).resolve().parents[2]
DATASET_PATH = ROOT / "data" / "evaluation" / "golden_dataset.json"
SCHEMA_PATH = ROOT / "data" / "schemas" / "golden_evaluation.schema.json"

INTENT_CAPABILITY = {
    SupervisorIntent.STOCKOUT_RISK: Capability.ANALYTICS_STOCKOUT,
    SupervisorIntent.FREIGHT_RECONCILIATION: Capability.ANALYTICS_FREIGHT,
    SupervisorIntent.SUPPLIER_TERMS: Capability.DOCUMENT_SUPPLIER_TERMS,
    SupervisorIntent.OVERDUE_INVOICES: Capability.ANALYTICS_OVERDUE_INVOICES,
    SupervisorIntent.MARGIN_ANALYSIS: Capability.ANALYTICS_MARGIN,
    SupervisorIntent.DRAFT_PURCHASE_ORDER: Capability.DRAFT_PURCHASE_ORDER,
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: Capability.DRAFT_CARRIER_DISPUTE,
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: Capability.DRAFT_PAYMENT_REMINDER,
    SupervisorIntent.DRAFT_DELAY_ADVISORY: Capability.DRAFT_DELAY_ADVISORY,
    SupervisorIntent.GENERAL_DOCUMENT_QUESTION: Capability.DOCUMENT_SEARCH,
    SupervisorIntent.GENERAL_CONVERSATION: Capability.BASIC_ASSISTANT,
}


def load_manifest() -> GoldenEvaluationManifest:
    return GoldenEvaluationManifest.model_validate_json(DATASET_PATH.read_text(encoding="utf-8"))


def test_golden_dataset_is_strict_deterministic_and_exactly_fifty_cases() -> None:
    saved = load_manifest()
    generated = build_golden_manifest()

    assert saved == generated
    assert saved.case_count == 50
    assert len(saved.cases) == 50
    assert [case.case_id for case in saved.cases] == [
        f"gold_{index:03d}" for index in range(1, 51)
    ]


def test_category_and_role_coverage_is_balanced_for_governance_evaluation() -> None:
    manifest = load_manifest()

    assert Counter(case.category for case in manifest.cases) == {
        EvaluationCategory.SQL_ANALYTICS: 16,
        EvaluationCategory.DOCUMENT_RETRIEVAL: 10,
        EvaluationCategory.ACTION_DRAFTING: 8,
        EvaluationCategory.AUTHORIZATION_REFUSAL: 12,
        EvaluationCategory.DIRECT_RESPONSE: 2,
        EvaluationCategory.UNSUPPORTED: 2,
    }
    roles = Counter(case.role.value for case in manifest.cases)
    assert set(roles) == {
        "founder_cfo",
        "logistics_manager",
        "staff_accountant",
        "support_intern",
    }
    assert all(count >= 5 for count in roles.values())
    assert any("cross_tenant" in case.tags for case in manifest.cases)


def test_answerable_and_refusal_cases_match_the_immutable_role_policy() -> None:
    for case in load_manifest().cases:
        capability = INTENT_CAPABILITY.get(case.expected_intent)
        if case.category == EvaluationCategory.UNSUPPORTED:
            assert capability is None
            assert case.expected_route == AgentRoute.REFUSE
            continue
        assert capability is not None
        allowed = role_has_capability(case.role, capability)
        if case.category == EvaluationCategory.AUTHORIZATION_REFUSAL:
            assert allowed is False
            assert case.expected_status == WorkflowStatus.REFUSED
            assert case.expected_error_code == "policy_denied"
        else:
            assert allowed is True
            assert case.expected_error_code is None


def test_document_expectations_reference_ingested_documents_and_real_clauses() -> None:
    document_manifest = json.loads(
        (ROOT / "data" / "documents" / "document_manifest.json").read_text(encoding="utf-8")
    )
    documents = {item["document_id"]: item for item in document_manifest["documents"]}

    for case in load_manifest().cases:
        for citation in case.expected_citations:
            document = documents[citation.document_id]
            assert document["ingest"] is True
            assert document["tenant_id"] == case.tenant_id
            assert citation.page_number <= document["page_count"]
            if citation.clause_id:
                assert citation.clause_id in document["clause_ids"]


def test_scenario_links_exist_and_shared_facts_do_not_drift() -> None:
    raw = json.loads(
        (ROOT / "data" / "evaluation" / "ground_truth_scenarios.json").read_text(
            encoding="utf-8"
        )
    )
    scenarios = {item["scenario_id"]: item for item in raw["scenarios"]}

    for case in load_manifest().cases:
        if case.source_scenario_id is None:
            continue
        source = scenarios[case.source_scenario_id]
        for key in case.expected_facts.keys() & source["expected_facts"].keys():
            assert case.expected_facts[key] == source["expected_facts"][key]


def test_action_expectations_are_derived_from_server_policy() -> None:
    action_cases = [
        case
        for case in load_manifest().cases
        if case.category == EvaluationCategory.ACTION_DRAFTING
    ]
    assert {case.expected_intent for case in action_cases} == {
        SupervisorIntent.DRAFT_PURCHASE_ORDER,
        SupervisorIntent.DRAFT_CARRIER_DISPUTE,
        SupervisorIntent.DRAFT_PAYMENT_REMINDER,
        SupervisorIntent.DRAFT_DELAY_ADVISORY,
    }

    for case in action_cases:
        policy = get_action_policy(case.expected_intent)
        assert case.approval is not None
        assert case.approval.risk_level == policy.risk_level
        assert tuple(case.approval.approver_roles) == policy.approver_roles
        assert case.approval.submission_allowed is False
        assert case.expected_status == WorkflowStatus.PENDING_APPROVAL


def test_schema_artifact_matches_current_contract() -> None:
    saved_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert saved_schema == GoldenEvaluationManifest.model_json_schema()
