"""Upload workflow contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class UploadResourceType(StrEnum):
    TRACKING_EVENTS = "tracking_events"
    VENDOR_INVOICES = "vendor_invoices"
    DOCUMENT = "document"


class UploadFormat(StrEnum):
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"


class UploadStatus(StrEnum):
    VALIDATED = "validated"
    QUARANTINED = "quarantined"
    COMMITTING = "committing"
    COMMITTED = "committed"


class UploadJob(BaseModel):
    upload_id: str
    tenant_id: str
    uploader_role: str
    resource_type: UploadResourceType
    file_format: UploadFormat
    original_filename: str
    media_type: str
    content_sha256: str
    byte_count: int = Field(ge=0)
    status: UploadStatus
    sensitivity: str | None = None
    title: str | None = None
    document_id: str | None = None
    record_count: int = Field(ge=0)
    preview: dict[str, Any] | list[dict[str, Any]]
    validation_errors: list[str]
    created_at: datetime
    expires_at: datetime
    committed_at: datetime | None = None


class UploadPreviewResult(BaseModel):
    job: UploadJob


class UploadCommitResult(BaseModel):
    job: UploadJob
    ingested_records: int = Field(ge=0)
