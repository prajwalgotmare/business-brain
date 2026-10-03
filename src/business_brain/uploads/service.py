"""Validation, preview, quarantine, and explicit upload commit workflow."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from business_brain.core.config import Settings
from business_brain.data.finance_models import VendorInvoice
from business_brain.data.logistics_models import TrackingEvent
from business_brain.retrieval.documents import extract_uploaded_pdf_chunks
from business_brain.retrieval.qdrant_ingestion import ingest_uploaded_chunks
from business_brain.security.context import AuthContext, UserRole
from business_brain.security.policy import (
    AuthorizationDeniedError,
    Capability,
    require_capability,
    sensitivities_for,
)
from business_brain.uploads.repository import UploadRepository
from business_brain.uploads.schemas import (
    UploadCommitResult,
    UploadFormat,
    UploadJob,
    UploadResourceType,
    UploadStatus,
)

SENSITIVITIES = {"public", "support", "operations", "accounting", "executive"}
ACTIVE_PDF_MARKERS = (b"/JavaScript", b"/JS", b"/OpenAction", b"/EmbeddedFile", b"/Launch")
FORMULA_PREFIXES = ("=", "+", "@")

RESOURCE_MODELS: dict[UploadResourceType, type[BaseModel]] = {
    UploadResourceType.TRACKING_EVENTS: TrackingEvent,
    UploadResourceType.VENDOR_INVOICES: VendorInvoice,
}

RESOURCE_CAPABILITIES: dict[UploadResourceType, Capability] = {
    UploadResourceType.TRACKING_EVENTS: Capability.UPLOAD_TRACKING_EVENTS,
    UploadResourceType.VENDOR_INVOICES: Capability.UPLOAD_VENDOR_INVOICES,
    UploadResourceType.DOCUMENT: Capability.UPLOAD_DOCUMENT,
}

DOCUMENT_UPLOAD_SENSITIVITIES: dict[UserRole, frozenset[str]] = {
    UserRole.FOUNDER_CFO: sensitivities_for(UserRole.FOUNDER_CFO),
    UserRole.LOGISTICS_MANAGER: frozenset({"public", "operations"}),
    UserRole.STAFF_ACCOUNTANT: frozenset({"public", "accounting"}),
    UserRole.SUPPORT_INTERN: frozenset(),
}


class UploadAccessDeniedError(PermissionError):
    pass


class UploadConflictError(RuntimeError):
    pass


class UploadNotFoundError(KeyError):
    pass


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _safe_validation_errors(error: ValidationError, row_number: int) -> list[str]:
    messages = []
    for item in error.errors(include_url=False, include_input=False)[:10]:
        field = ".".join(str(part) for part in item["loc"])
        messages.append(f"Row {row_number}, {field}: {item['msg']}")
    return messages


class UploadService:
    def __init__(self, *, settings: Settings, repository: UploadRepository) -> None:
        self.settings = settings
        self.repository = repository

    def preview(
        self,
        *,
        auth: AuthContext,
        resource_type: UploadResourceType,
        filename: str,
        media_type: str | None,
        content: bytes,
        sensitivity: str | None = None,
        title: str | None = None,
    ) -> UploadJob:
        self._authorize(auth, resource_type, sensitivity)
        upload_id = str(uuid4())
        safe_filename = PurePath(filename).name
        errors: list[str] = []
        if safe_filename != filename or not safe_filename or "\x00" in filename:
            errors.append("Filename is invalid")
            safe_filename = f"upload-{upload_id}"
        if not content:
            errors.append("File is empty")
        if len(content) > self.settings.upload_max_bytes:
            errors.append(f"File exceeds the {self.settings.upload_max_bytes}-byte limit")

        file_format = self._detect_format(resource_type, safe_filename, content, errors)
        normalized: list[dict[str, Any]] | None = None
        preview: dict[str, Any] | list[dict[str, Any]] = {}
        document_id: str | None = None
        record_count = 0

        if not errors:
            if resource_type == UploadResourceType.DOCUMENT:
                document_id = f"doc_upload_{upload_id.replace('-', '')}"
                preview, record_count, pdf_errors = self._validate_pdf(content, title)
                errors.extend(pdf_errors)
            else:
                normalized, structured_errors = self._validate_structured(
                    content=content,
                    file_format=file_format,
                    resource_type=resource_type,
                    tenant_id=auth.tenant_id,
                )
                errors.extend(structured_errors)
                record_count = len(normalized or [])
                preview = (normalized or [])[:5]

        status = UploadStatus.QUARANTINED if errors else UploadStatus.VALIDATED
        now = datetime.now(UTC)
        return self.repository.create_job(
            {
                "upload_id": upload_id,
                "tenant_id": auth.tenant_id,
                "uploader_role": auth.role.value,
                "resource_type": resource_type.value,
                "file_format": file_format.value,
                "original_filename": safe_filename,
                "media_type": media_type or "application/octet-stream",
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "byte_count": len(content),
                "status": status.value,
                "sensitivity": sensitivity,
                "title": title.strip() if title else None,
                "document_id": document_id,
                "record_count": record_count,
                "preview": preview,
                "validation_errors": errors[:20],
                "normalized_records": normalized if not errors else None,
                "raw_content": content,
                "expires_at": now + timedelta(hours=self.settings.upload_retention_hours),
            }
        )

    def get(self, auth: AuthContext, upload_id: str) -> UploadJob:
        job = self.repository.get_job(auth.tenant_id, upload_id)
        if not job:
            raise UploadNotFoundError("Upload job not found")
        self._authorize(auth, job.resource_type, job.sensitivity)
        return job

    def commit(self, auth: AuthContext, upload_id: str) -> UploadCommitResult:
        job = self.get(auth, upload_id)
        if job.status == UploadStatus.COMMITTED:
            return UploadCommitResult(job=job, ingested_records=job.record_count)
        if job.status != UploadStatus.VALIDATED:
            raise UploadConflictError("Only validated uploads can be committed")
        try:
            if job.resource_type != UploadResourceType.DOCUMENT:
                committed, count = self.repository.commit_structured(auth.tenant_id, upload_id)
                return UploadCommitResult(job=committed, ingested_records=count)

            self.repository.set_status(
                auth.tenant_id,
                upload_id,
                UploadStatus.COMMITTING,
            )
            content = self.repository.get_raw_content(auth.tenant_id, upload_id)
            assert job.document_id and job.title and job.sensitivity
            chunks = extract_uploaded_pdf_chunks(
                content=content,
                tenant_id=auth.tenant_id,
                document_id=job.document_id,
                title=job.title,
                sensitivity=job.sensitivity,
            )
            ingest_uploaded_chunks(chunks, self.settings)
            committed = self.repository.set_status(
                auth.tenant_id,
                upload_id,
                UploadStatus.COMMITTED,
            )
            return UploadCommitResult(job=committed, ingested_records=1)
        except (UploadConflictError, UploadAccessDeniedError):
            raise
        except Exception as exc:
            self.repository.set_status(
                auth.tenant_id,
                upload_id,
                UploadStatus.QUARANTINED,
                validation_errors=["Commit failed integrity or storage validation"],
            )
            raise UploadConflictError("Upload commit failed validation") from exc

    def _authorize(
        self,
        auth: AuthContext,
        resource_type: UploadResourceType,
        sensitivity: str | None,
    ) -> None:
        try:
            require_capability(auth, RESOURCE_CAPABILITIES[resource_type])
        except AuthorizationDeniedError as exc:
            raise UploadAccessDeniedError("Role cannot upload this resource type") from exc
        if resource_type == UploadResourceType.DOCUMENT:
            if sensitivity not in SENSITIVITIES:
                raise UploadAccessDeniedError("A valid document sensitivity is required")
            if sensitivity not in DOCUMENT_UPLOAD_SENSITIVITIES[auth.role]:
                raise UploadAccessDeniedError("Role cannot upload this document sensitivity")

    @staticmethod
    def _detect_format(
        resource_type: UploadResourceType,
        filename: str,
        content: bytes,
        errors: list[str],
    ) -> UploadFormat:
        suffix = PurePath(filename).suffix.lower()
        if resource_type == UploadResourceType.DOCUMENT:
            if suffix != ".pdf" or not content.startswith(b"%PDF-"):
                errors.append("Document uploads must be genuine PDF files")
            return UploadFormat.PDF
        if suffix == ".json":
            return UploadFormat.JSON
        if suffix == ".csv":
            return UploadFormat.CSV
        errors.append("Structured uploads must use a .csv or .json extension")
        return UploadFormat.JSON if content.lstrip().startswith((b"{", b"[")) else UploadFormat.CSV

    def _validate_structured(
        self,
        *,
        content: bytes,
        file_format: UploadFormat,
        resource_type: UploadResourceType,
        tenant_id: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        errors: list[str] = []
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [], ["Structured files must be UTF-8 encoded"]
        try:
            if file_format == UploadFormat.JSON:
                parsed = json.loads(text, object_pairs_hook=_duplicate_safe_object)
                if isinstance(parsed, dict) and "records" in parsed:
                    parsed = parsed["records"]
                records = parsed if isinstance(parsed, list) else [parsed]
            else:
                reader = csv.DictReader(StringIO(text, newline=""))
                if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                    return [], ["CSV headers must be present and unique"]
                records = list(reader)
        except (csv.Error, json.JSONDecodeError, ValueError) as exc:
            return [], [f"File parsing failed: {type(exc).__name__}"]
        if not records:
            return [], ["File contains no records"]
        if len(records) > self.settings.upload_max_rows:
            return [], [f"File exceeds the {self.settings.upload_max_rows}-row limit"]

        model = RESOURCE_MODELS[resource_type]
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(records, start=1):
            if not isinstance(raw, dict):
                errors.append(f"Row {index} must be an object")
                continue
            supplied_tenant = raw.get("tenant_id")
            if supplied_tenant not in {None, "", tenant_id}:
                errors.append(f"Row {index} contains a cross-tenant tenant_id")
                continue
            if any(
                isinstance(value, str) and value.lstrip().startswith(FORMULA_PREFIXES)
                for value in raw.values()
            ):
                errors.append(f"Row {index} contains a spreadsheet formula-like value")
                continue
            candidate = {key: (None if value == "" else value) for key, value in raw.items()}
            candidate["tenant_id"] = tenant_id
            try:
                validated = model.model_validate(candidate)
            except ValidationError as exc:
                errors.extend(_safe_validation_errors(exc, index))
                continue
            normalized.append(validated.model_dump(mode="json"))
        if errors:
            return [], errors[:20]
        return normalized, []

    def _validate_pdf(
        self, content: bytes, title: str | None
    ) -> tuple[dict[str, Any], int, list[str]]:
        errors: list[str] = []
        clean_title = title.strip() if title else ""
        if not 5 <= len(clean_title) <= 180:
            errors.append("PDF title must contain 5 to 180 characters")
        if any(marker in content for marker in ACTIVE_PDF_MARKERS):
            errors.append("PDF contains active or embedded content")
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted:
                errors.append("Encrypted PDFs are not accepted")
                return {}, 0, errors
            page_count = len(reader.pages)
            if not 1 <= page_count <= self.settings.upload_max_pdf_pages:
                errors.append(
                    f"PDF must contain 1 to {self.settings.upload_max_pdf_pages} pages"
                )
            page_text = [(page.extract_text() or "").strip() for page in reader.pages]
            full_text = "\n".join(page_text).strip()
            if len(full_text) < 100:
                errors.append("PDF must contain at least 100 extractable text characters")
            preview = {
                "page_count": page_count,
                "extractable_characters": len(full_text),
                "text_excerpt": full_text[:500],
            }
            return preview, 1, errors
        except Exception as exc:
            return {}, 0, [*errors, f"PDF parsing failed: {type(exc).__name__}"]
