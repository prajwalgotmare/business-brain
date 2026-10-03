"""Verify staged preview, quarantine, commit, status, and tenant isolation."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from business_brain.core.config import Settings
from business_brain.security.context import AuthContext, UserRole
from business_brain.uploads.repository import UploadRepository
from business_brain.uploads.schemas import UploadResourceType, UploadStatus
from business_brain.uploads.service import UploadNotFoundError, UploadService

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "quality" / "upload_workflow_smoke.json"


def _auth(tenant_id: str, role: UserRole) -> AuthContext:
    return AuthContext(tenant_id=tenant_id, user_id="upload-smoke", role=role)


def _tracking_record() -> dict[str, str]:
    path = ROOT / "data/generated/aura_brands/tracking_events.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        record = next(csv.DictReader(handle))
    record.pop("tenant_id")
    return record


def main() -> None:
    settings = Settings()
    service = UploadService(settings=settings, repository=UploadRepository(settings))
    cfo = _auth("tenant_aura", UserRole.FOUNDER_CFO)
    logistics = _auth("tenant_aura", UserRole.LOGISTICS_MANAGER)

    pdf_content = (
        ROOT / "data/documents/aura_brands/doc_aur_return_shipping_policy.pdf"
    ).read_bytes()
    pdf_job = service.preview(
        auth=cfo,
        resource_type=UploadResourceType.DOCUMENT,
        filename="uploaded-return-policy.pdf",
        media_type="application/pdf",
        content=pdf_content,
        sensitivity="public",
        title="Uploaded Customer Return and Shipping Delay Policy",
    )
    assert pdf_job.status == UploadStatus.VALIDATED
    committed = service.commit(cfo, pdf_job.upload_id)
    assert committed.job.status == UploadStatus.COMMITTED
    assert committed.ingested_records == 1
    assert service.get(cfo, pdf_job.upload_id).status == UploadStatus.COMMITTED

    valid_json = service.preview(
        auth=logistics,
        resource_type=UploadResourceType.TRACKING_EVENTS,
        filename="tracking-events.json",
        media_type="application/json",
        content=json.dumps([_tracking_record()]).encode(),
    )
    assert valid_json.status == UploadStatus.VALIDATED
    assert valid_json.preview[0]["tenant_id"] == "tenant_aura"

    cross_tenant = _tracking_record() | {"tenant_id": "tenant_apex"}
    quarantined = service.preview(
        auth=logistics,
        resource_type=UploadResourceType.TRACKING_EVENTS,
        filename="cross-tenant.json",
        media_type="application/json",
        content=json.dumps([cross_tenant]).encode(),
    )
    assert quarantined.status == UploadStatus.QUARANTINED
    assert any("cross-tenant" in error for error in quarantined.validation_errors)

    hidden_from_apex = False
    try:
        service.get(_auth("tenant_apex", UserRole.FOUNDER_CFO), pdf_job.upload_id)
    except UploadNotFoundError:
        hidden_from_apex = True
    assert hidden_from_apex

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "committed_pdf_upload_id": pdf_job.upload_id,
        "committed_document_id": pdf_job.document_id,
        "validated_json_upload_id": valid_json.upload_id,
        "quarantined_upload_id": quarantined.upload_id,
        "checks": {
            "pdf_preview_commit_status": "passed",
            "json_tenant_tagging": "passed",
            "cross_tenant_quarantine": "passed",
            "cross_tenant_status_isolation": "passed",
        },
        "cross_tenant_leak_count": 0,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Verified upload workflow checks: 4")
    print("Cross-tenant leaks: 0")


if __name__ == "__main__":
    main()
