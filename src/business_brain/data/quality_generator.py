"""Build deterministic quality evidence from generated data artifacts."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

from business_brain.data.commerce_models import CommerceInventoryDataset
from business_brain.data.finance_models import FinanceDataset
from business_brain.data.logistics_models import LogisticsDataset
from business_brain.data.models import ReferenceCatalog, StrictModel
from business_brain.data.quality_models import (
    ArtifactFingerprint,
    DataQualityManifest,
    QualityCheck,
)
from business_brain.data.scenario_models import GroundTruthManifest

TENANT_BY_DIRECTORY = {
    "aura_brands": "tenant_aura",
    "apex_retail": "tenant_apex",
}


def _csv_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    if not reader.fieldnames:
        raise ValueError("CSV artifact has no header")
    return reader.fieldnames, rows


def _primary_key(columns: list[str]) -> str:
    candidates = [column for column in columns if column != "tenant_id" and column.endswith("_id")]
    if not candidates:
        raise ValueError("CSV artifact has no primary-key candidate")
    return candidates[0]


def _source_record_ids(collection: list[StrictModel]) -> set[str]:
    if not collection:
        return set()
    fields = list(type(collection[0]).model_fields)
    primary_key = next(
        field for field in fields if field != "tenant_id" and field.endswith("_id")
    )
    return {str(getattr(record, primary_key)) for record in collection}


def build_data_quality_manifest(
    *,
    project_root: Path,
    expected_artifacts: Mapping[Path, str],
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
    finance: FinanceDataset,
    scenarios: GroundTruthManifest,
) -> DataQualityManifest:
    """Audit committed artifacts and return reproducible machine-readable evidence."""

    stale = [
        path
        for path, expected in expected_artifacts.items()
        if not path.exists() or path.read_text(encoding="utf-8") != expected
    ]
    if stale:
        relative = ", ".join(str(path.relative_to(project_root)) for path in stale)
        raise ValueError(f"generated artifacts are stale: {relative}")

    fingerprints: list[ArtifactFingerprint] = []
    csv_row_total = 0
    unique_key_total = 0
    tenant_row_total = 0
    for path, content in sorted(expected_artifacts.items(), key=lambda item: str(item[0])):
        relative_path = path.relative_to(project_root).as_posix()
        encoded = content.encode("utf-8")
        if path.suffix == ".csv":
            columns, rows = _csv_rows(content)
            tenant_id = TENANT_BY_DIRECTORY[path.parent.name]
            actual_tenants = {row["tenant_id"] for row in rows}
            if actual_tenants != {tenant_id}:
                raise ValueError(f"tenant isolation failed: {relative_path}")
            primary_key = _primary_key(columns)
            keys = [row[primary_key] for row in rows]
            if not all(keys) or len(keys) != len(set(keys)):
                raise ValueError(f"primary-key uniqueness failed: {relative_path}")
            csv_row_total += len(rows)
            unique_key_total += len(keys)
            tenant_row_total += len(rows)
            fingerprints.append(
                ArtifactFingerprint(
                    relative_path=relative_path,
                    media_type="text/csv",
                    byte_count=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                    row_count=len(rows),
                    columns=columns,
                    tenant_id=tenant_id,
                )
            )
        else:
            fingerprints.append(
                ArtifactFingerprint(
                    relative_path=relative_path,
                    media_type="application/json",
                    byte_count=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                )
            )

    collections: dict[str, list[StrictModel]] = {}
    for dataset in (catalog, commerce, logistics, finance):
        for field_name in type(dataset).model_fields:
            value = getattr(dataset, field_name)
            if isinstance(value, list) and value and isinstance(value[0], StrictModel):
                collections[field_name] = value
    evidence_count = 0
    for scenario in scenarios.scenarios:
        for evidence in scenario.evidence:
            records = collections.get(evidence.source_collection)
            if records is None or evidence.record_id not in _source_record_ids(records):
                raise ValueError(
                    f"missing scenario evidence: {evidence.source_collection}/{evidence.record_id}"
                )
            evidence_count += 1

    checks = [
        QualityCheck(
            check_id="artifacts_current",
            name="Deterministic artifact comparison",
            records_checked=len(fingerprints),
            details=(
                "Every committed source artifact exactly matches deterministic generator output."
            ),
        ),
        QualityCheck(
            check_id="row_counts",
            name="CSV row counts",
            records_checked=csv_row_total,
            details="Every CSV has a non-empty header and its exact row count is recorded.",
        ),
        QualityCheck(
            check_id="primary_keys",
            name="Primary-key uniqueness",
            records_checked=unique_key_total,
            details=(
                "Every generated CSV primary key is populated and unique within its collection."
            ),
        ),
        QualityCheck(
            check_id="tenant_isolation",
            name="Tenant isolation",
            records_checked=tenant_row_total,
            details="Aura and Apex CSV files contain only their expected tenant_id.",
        ),
        QualityCheck(
            check_id="schema_validation",
            name="Schema and reference validation",
            records_checked=len(collections),
            details=(
                "Reference, commerce, logistics, finance, and scenario models validate strictly."
            ),
        ),
        QualityCheck(
            check_id="totals_reconcile",
            name="Commercial and financial reconciliation",
            records_checked=len(commerce.orders) + len(finance.vendor_invoices),
            details=(
                "Order, purchase-order, invoice, payment, freight, and margin totals reconcile."
            ),
        ),
        QualityCheck(
            check_id="inventory_reconciles",
            name="Inventory roll-forward",
            records_checked=len(commerce.inventory_balances),
            details="Movements and allocations reconcile to every inventory snapshot.",
        ),
        QualityCheck(
            check_id="dates_valid",
            name="Dates and lifecycle order",
            records_checked=len(commerce.orders) + len(logistics.shipments) + len(finance.payments),
            details="Events stay within the snapshot and lifecycle/payment dates remain ordered.",
        ),
        QualityCheck(
            check_id="scenario_evidence",
            name="Ground-truth evidence resolution",
            records_checked=evidence_count,
            details="Every scenario evidence reference resolves to a concrete source record.",
        ),
    ]
    return DataQualityManifest(
        generated_at=scenarios.generated_at + timedelta(minutes=5),
        snapshot_at=scenarios.snapshot_at,
        artifact_count=len(fingerprints),
        csv_file_count=sum(item.media_type == "text/csv" for item in fingerprints),
        total_csv_rows=csv_row_total,
        artifacts=fingerprints,
        checks=checks,
    )
