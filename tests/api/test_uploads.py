from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from business_brain.api.dependencies import get_upload_service
from business_brain.core.config import Settings
from business_brain.main import app
from business_brain.uploads.schemas import UploadFormat, UploadJob, UploadStatus
from business_brain.uploads.service import UploadAccessDeniedError

HEADERS = {
    "X-Tenant-ID": "tenant_aura",
    "X-User-ID": "demo-logistics",
    "X-Role": "logistics_manager",
}


def upload_job() -> UploadJob:
    now = datetime.now(UTC)
    return UploadJob(
        upload_id="12345678-1234-1234-1234-123456789abc",
        tenant_id="tenant_aura",
        uploader_role="logistics_manager",
        resource_type="tracking_events",
        file_format=UploadFormat.JSON,
        original_filename="tracking.json",
        media_type="application/json",
        content_sha256="a" * 64,
        byte_count=2,
        status=UploadStatus.VALIDATED,
        record_count=1,
        preview=[{"tenant_id": "tenant_aura"}],
        validation_errors=[],
        created_at=now,
        expires_at=now + timedelta(days=7),
    )


class StubUploadService:
    settings = Settings(_env_file=None, upload_max_bytes=10_000)

    def __init__(self, error=None) -> None:
        self.error = error
        self.calls = []

    def preview(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return upload_job()


def test_preview_endpoint_reads_bounded_file_and_returns_job() -> None:
    service = StubUploadService()
    app.dependency_overrides[get_upload_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/preview",
                headers=HEADERS,
                data={"resource_type": "tracking_events"},
                files={"file": ("tracking.json", b"[]", "application/json")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["job"]["status"] == "validated"
    assert service.calls[0]["auth"].tenant_id == "tenant_aura"
    assert service.calls[0]["content"] == b"[]"


def test_upload_access_denial_is_sanitized() -> None:
    service = StubUploadService(UploadAccessDeniedError("internal policy detail"))
    app.dependency_overrides[get_upload_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/uploads/preview",
                headers=HEADERS,
                data={"resource_type": "tracking_events"},
                files={"file": ("tracking.json", b"[]", "application/json")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "upload_forbidden"
    assert "internal policy" not in response.text
