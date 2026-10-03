"""Contracts for the deterministic data-quality evidence manifest."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from business_brain.data.models import Identifier, StrictModel

Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class QualityStatus(StrEnum):
    PASS = "pass"


class ArtifactFingerprint(StrictModel):
    relative_path: str
    media_type: Literal["text/csv", "application/json"]
    byte_count: Annotated[int, Field(gt=0)]
    sha256: Sha256
    row_count: Annotated[int, Field(ge=0)] | None = None
    columns: list[str] = Field(default_factory=list)
    tenant_id: Identifier | None = None

    @model_validator(mode="after")
    def validate_csv_metadata(self) -> ArtifactFingerprint:
        if self.media_type == "text/csv":
            if self.row_count is None or not self.columns or self.tenant_id is None:
                raise ValueError("CSV fingerprints require rows, columns, and tenant_id")
        elif self.row_count is not None or self.columns or self.tenant_id is not None:
            raise ValueError("JSON fingerprints cannot contain CSV metadata")
        return self


class QualityCheck(StrictModel):
    check_id: Identifier
    name: str
    status: Literal[QualityStatus.PASS] = QualityStatus.PASS
    records_checked: Annotated[int, Field(ge=0)]
    details: str


class DataQualityManifest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    status: Literal[QualityStatus.PASS] = QualityStatus.PASS
    artifact_count: Annotated[int, Field(gt=0)]
    csv_file_count: Annotated[int, Field(gt=0)]
    total_csv_rows: Annotated[int, Field(gt=0)]
    artifacts: list[ArtifactFingerprint]
    checks: list[QualityCheck]

    @model_validator(mode="after")
    def validate_summary(self) -> DataQualityManifest:
        if self.generated_at < self.snapshot_at:
            raise ValueError("generated_at cannot precede snapshot_at")
        if self.artifact_count != len(self.artifacts):
            raise ValueError("artifact_count does not match artifacts")
        csv_artifacts = [item for item in self.artifacts if item.media_type == "text/csv"]
        if self.csv_file_count != len(csv_artifacts):
            raise ValueError("csv_file_count does not match artifacts")
        if self.total_csv_rows != sum(item.row_count or 0 for item in csv_artifacts):
            raise ValueError("total_csv_rows does not reconcile")
        if not self.checks:
            raise ValueError("at least one quality check is required")
        check_ids = [item.check_id for item in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("duplicate quality check_id")
        return self
