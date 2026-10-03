"""Contracts for deterministic evaluation scenarios and their answer keys."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from business_brain.data.models import Identifier, StrictModel


class ScenarioType(StrEnum):
    STOCKOUT_RISK = "stockout_risk"
    CARRIER_OVERBILLING = "carrier_overbilling"
    SUPPLIER_TERMS = "supplier_terms"
    OVERDUE_INVOICE = "overdue_invoice"
    MARGIN_DECLINE = "margin_decline"
    PURCHASE_ORDER_APPROVAL = "purchase_order_approval"


class EvidenceReference(StrictModel):
    source_collection: Identifier
    record_id: Identifier
    purpose: Annotated[str, Field(min_length=3, max_length=160)]


class DocumentDependency(StrictModel):
    document_id: Identifier
    clause_id: Identifier
    status: Literal["available"] = "available"


class GroundTruthScenario(StrictModel):
    scenario_id: Identifier
    tenant_id: Literal["tenant_aura"] = "tenant_aura"
    scenario_type: ScenarioType
    question: Annotated[str, Field(min_length=10, max_length=300)]
    expected_summary: Annotated[str, Field(min_length=10, max_length=500)]
    expected_facts: dict[Identifier, str]
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]
    document_dependencies: list[DocumentDependency] = Field(default_factory=list)
    required_role: Literal["founder_cfo", "logistics_manager", "staff_accountant"]
    approval_required: bool = False


class GroundTruthManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    scenarios: Annotated[list[GroundTruthScenario], Field(min_length=6, max_length=6)]

    @model_validator(mode="after")
    def validate_scenario_set(self) -> GroundTruthManifest:
        expected = {item.value for item in ScenarioType}
        actual = {item.scenario_type.value for item in self.scenarios}
        if actual != expected:
            raise ValueError("manifest must contain every required scenario exactly once")
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("scenario IDs must be unique")
        return self
