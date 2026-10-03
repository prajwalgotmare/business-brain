import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from business_brain.core.config import Settings
from business_brain.security.context import AuthContext, UserRole
from business_brain.uploads.schemas import UploadJob, UploadResourceType, UploadStatus
from business_brain.uploads.service import UploadAccessDeniedError, UploadService

ROOT = Path(__file__).resolve().parents[2]


class FakeRepository:
    def __init__(self) -> None:
        self.jobs = {}
        self.raw = {}

    def create_job(self, values):
        now = datetime.now(UTC)
        public = {
            key: value
            for key, value in values.items()
            if key not in {"raw_content", "normalized_records"}
        }
        public |= {"created_at": now, "committed_at": None}
        job = UploadJob.model_validate(public)
        self.jobs[job.upload_id] = job
        self.raw[job.upload_id] = values["raw_content"]
        return job

    def get_job(self, tenant_id, upload_id):
        job = self.jobs.get(upload_id)
        return job if job and job.tenant_id == tenant_id else None

    def get_raw_content(self, tenant_id, upload_id):
        assert self.jobs[upload_id].tenant_id == tenant_id
        return self.raw[upload_id]

    def set_status(self, tenant_id, upload_id, status, *, validation_errors=None):
        job = self.get_job(tenant_id, upload_id)
        assert job
        updates = {"status": status}
        if validation_errors is not None:
            updates["validation_errors"] = validation_errors
        if status == UploadStatus.COMMITTED:
            updates["committed_at"] = datetime.now(UTC)
        updated = job.model_copy(update=updates)
        self.jobs[upload_id] = updated
        return updated

    def commit_structured(self, tenant_id, upload_id):
        committed = self.set_status(tenant_id, upload_id, UploadStatus.COMMITTED)
        return committed, committed.record_count


def auth(role: UserRole, tenant_id: str = "tenant_aura") -> AuthContext:
    return AuthContext(tenant_id=tenant_id, user_id="upload-test", role=role)


def service() -> UploadService:
    return UploadService(
        settings=Settings(_env_file=None, upload_max_bytes=100_000),
        repository=FakeRepository(),
    )


def tracking_event_record() -> dict[str, str]:
    path = ROOT / "data/generated/aura_brands/tracking_events.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return next(csv.DictReader(handle))


def test_valid_json_is_tenant_tagged_and_previewed() -> None:
    upload_service = service()
    record = tracking_event_record()
    record.pop("tenant_id")

    job = upload_service.preview(
        auth=auth(UserRole.LOGISTICS_MANAGER),
        resource_type=UploadResourceType.TRACKING_EVENTS,
        filename="tracking.json",
        media_type="application/json",
        content=json.dumps([record]).encode(),
    )

    assert job.status == UploadStatus.VALIDATED
    assert job.record_count == 1
    assert job.preview[0]["tenant_id"] == "tenant_aura"
    assert "raw_content" not in job.model_dump()


def test_cross_tenant_csv_is_quarantined() -> None:
    upload_service = service()
    record = tracking_event_record() | {"tenant_id": "tenant_apex"}
    output = []
    headers = list(record)
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    writer.writerow(record)
    output.append(buffer.getvalue())

    job = upload_service.preview(
        auth=auth(UserRole.LOGISTICS_MANAGER),
        resource_type=UploadResourceType.TRACKING_EVENTS,
        filename="tracking.csv",
        media_type="text/csv",
        content="".join(output).encode(),
    )

    assert job.status == UploadStatus.QUARANTINED
    assert any("cross-tenant" in error for error in job.validation_errors)


def test_wrong_role_is_denied_before_upload_is_staged() -> None:
    upload_service = service()
    with pytest.raises(UploadAccessDeniedError):
        upload_service.preview(
            auth=auth(UserRole.SUPPORT_INTERN),
            resource_type=UploadResourceType.VENDOR_INVOICES,
            filename="invoices.json",
            media_type="application/json",
            content=b"[]",
        )
    assert upload_service.repository.jobs == {}


def test_genuine_text_pdf_is_validated_without_writing_to_disk() -> None:
    upload_service = service()
    content = (
        ROOT / "data/documents/aura_brands/doc_aur_return_shipping_policy.pdf"
    ).read_bytes()

    job = upload_service.preview(
        auth=auth(UserRole.FOUNDER_CFO),
        resource_type=UploadResourceType.DOCUMENT,
        filename="policy.pdf",
        media_type="application/pdf",
        content=content,
        sensitivity="public",
        title="Uploaded Customer Return Policy",
    )

    assert job.status == UploadStatus.VALIDATED
    assert job.preview["page_count"] == 1
    assert job.preview["extractable_characters"] >= 100
    assert job.document_id.startswith("doc_upload_")


def test_pdf_spoof_and_formula_like_csv_are_quarantined() -> None:
    upload_service = service()
    spoof = upload_service.preview(
        auth=auth(UserRole.FOUNDER_CFO),
        resource_type=UploadResourceType.DOCUMENT,
        filename="fake.pdf",
        media_type="application/pdf",
        content=b"This is not a PDF",
        sensitivity="public",
        title="Fake PDF Document",
    )
    assert spoof.status == UploadStatus.QUARANTINED

    record = tracking_event_record()
    record["location_code"] = "=HYPERLINK('malicious')"
    formula = upload_service.preview(
        auth=auth(UserRole.LOGISTICS_MANAGER),
        resource_type=UploadResourceType.TRACKING_EVENTS,
        filename="tracking.json",
        media_type="application/json",
        content=json.dumps([record]).encode(),
    )
    assert formula.status == UploadStatus.QUARANTINED
    assert any("formula-like" in error for error in formula.validation_errors)
