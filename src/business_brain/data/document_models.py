"""Contracts for the PDF corpus manifest used by document retrieval."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from business_brain.data.models import Identifier, Sensitivity, StrictModel

Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class DocumentKind(StrEnum):
    AGREEMENT = "agreement"
    INVOICE = "invoice"
    POLICY = "policy"
    CALENDAR = "calendar"
    PROCEDURE = "procedure"
    REFERENCE = "reference"


class DocumentSource(StrEnum):
    SYNTHETIC = "synthetic"
    PUBLIC_REFERENCE = "public_reference"


class DocumentRecord(StrictModel):
    document_id: Identifier
    title: Annotated[str, Field(min_length=5, max_length=180)]
    document_kind: DocumentKind
    source_type: DocumentSource
    relative_path: str
    document_date: date | None = None
    tenant_id: Identifier | None = None
    sensitivity: Sensitivity
    ingest: bool
    clause_ids: list[Identifier] = Field(default_factory=list)
    source_url: str | None = None
    license_name: str | None = None
    attribution: str | None = None
    byte_count: Annotated[int, Field(gt=0)]
    page_count: Annotated[int, Field(gt=0)]
    sha256: Sha256

    @model_validator(mode="after")
    def validate_source_metadata(self) -> DocumentRecord:
        if self.source_type == DocumentSource.SYNTHETIC:
            if self.tenant_id is None or self.source_url or self.license_name:
                raise ValueError("synthetic documents require a tenant and no source license")
        elif not self.source_url or not self.license_name or not self.attribution:
            raise ValueError("public references require source, license, and attribution")
        if self.ingest and self.tenant_id is None:
            raise ValueError("ingested documents require a tenant")
        return self


class DocumentManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    document_count: Annotated[int, Field(gt=0)]
    synthetic_count: Annotated[int, Field(gt=0)]
    public_reference_count: Annotated[int, Field(gt=0)]
    documents: list[DocumentRecord]

    @model_validator(mode="after")
    def validate_counts(self) -> DocumentManifest:
        if self.document_count != len(self.documents):
            raise ValueError("document_count does not match documents")
        synthetic_count = sum(
            item.source_type == DocumentSource.SYNTHETIC for item in self.documents
        )
        public_count = sum(
            item.source_type == DocumentSource.PUBLIC_REFERENCE for item in self.documents
        )
        if self.synthetic_count != synthetic_count:
            raise ValueError("synthetic_count does not match documents")
        if self.public_reference_count != public_count:
            raise ValueError("public_reference_count does not match documents")
        ids = [item.document_id for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("document IDs must be unique")
        paths = [item.relative_path for item in self.documents]
        if len(paths) != len(set(paths)):
            raise ValueError("document paths must be unique")
        return self

