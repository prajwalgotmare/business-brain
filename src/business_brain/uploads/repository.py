"""Neon-backed upload staging and atomic structured-record commits."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from business_brain.core.config import Settings
from business_brain.uploads.schemas import UploadJob, UploadStatus

STRUCTURED_TABLES = {"tracking_events", "vendor_invoices"}


class UploadRepository:
    def __init__(self, settings: Settings) -> None:
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL must be configured for uploads")
        self._database_url = settings.database_url

    def _connect(self):
        return psycopg.connect(self._database_url, row_factory=dict_row)

    def create_job(self, values: Mapping[str, Any]) -> UploadJob:
        statement = """
        INSERT INTO upload_jobs (
            upload_id, tenant_id, uploader_role, resource_type, file_format,
            original_filename, media_type, content_sha256, byte_count, status,
            sensitivity, title, document_id, record_count, preview,
            validation_errors, normalized_records, raw_content, expires_at
        ) VALUES (
            %(upload_id)s, %(tenant_id)s, %(uploader_role)s, %(resource_type)s,
            %(file_format)s, %(original_filename)s, %(media_type)s, %(content_sha256)s,
            %(byte_count)s, %(status)s, %(sensitivity)s, %(title)s, %(document_id)s,
            %(record_count)s, %(preview)s, %(validation_errors)s,
            %(normalized_records)s, %(raw_content)s, %(expires_at)s
        ) RETURNING *
        """
        parameters = dict(values)
        parameters["preview"] = Jsonb(values["preview"])
        parameters["validation_errors"] = Jsonb(values["validation_errors"])
        parameters["normalized_records"] = (
            Jsonb(values["normalized_records"])
            if values.get("normalized_records") is not None
            else None
        )
        with closing(self._connect()) as connection, connection.transaction():
            row = connection.execute(statement, parameters).fetchone()
        assert row is not None
        return self._to_job(row)

    def get_job(self, tenant_id: str, upload_id: str) -> UploadJob | None:
        with closing(self._connect()) as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            row = connection.execute(
                "SELECT * FROM upload_jobs WHERE tenant_id = %s AND upload_id = %s",
                (tenant_id, upload_id),
            ).fetchone()
        return self._to_job(row) if row else None

    def get_raw_content(self, tenant_id: str, upload_id: str) -> bytes:
        with closing(self._connect()) as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            row = connection.execute(
                "SELECT raw_content FROM upload_jobs WHERE tenant_id = %s AND upload_id = %s",
                (tenant_id, upload_id),
            ).fetchone()
        if not row:
            raise KeyError("Upload job not found")
        return bytes(row["raw_content"])

    def set_status(
        self,
        tenant_id: str,
        upload_id: str,
        status: UploadStatus,
        *,
        validation_errors: list[str] | None = None,
    ) -> UploadJob:
        committed_at: datetime | None | str = "now" if status == UploadStatus.COMMITTED else None
        statement = """
        UPDATE upload_jobs
        SET status = %(status)s,
            validation_errors = coalesce(%(validation_errors)s, validation_errors),
            committed_at = CASE WHEN %(committed_at)s = 'now' THEN now() ELSE committed_at END
        WHERE tenant_id = %(tenant_id)s AND upload_id = %(upload_id)s
        RETURNING *
        """
        with closing(self._connect()) as connection, connection.transaction():
            row = connection.execute(
                statement,
                {
                    "tenant_id": tenant_id,
                    "upload_id": upload_id,
                    "status": status.value,
                    "validation_errors": (
                        Jsonb(validation_errors) if validation_errors is not None else None
                    ),
                    "committed_at": committed_at,
                },
            ).fetchone()
        if not row:
            raise KeyError("Upload job not found")
        return self._to_job(row)

    def commit_structured(self, tenant_id: str, upload_id: str) -> tuple[UploadJob, int]:
        with closing(self._connect()) as connection, connection.transaction():
            job = connection.execute(
                """
                SELECT * FROM upload_jobs
                WHERE tenant_id = %s AND upload_id = %s
                FOR UPDATE
                """,
                (tenant_id, upload_id),
            ).fetchone()
            if not job:
                raise KeyError("Upload job not found")
            if job["status"] == UploadStatus.COMMITTED.value:
                return self._to_job(job), int(job["record_count"])
            if job["status"] != UploadStatus.VALIDATED.value:
                raise ValueError("Only validated uploads can be committed")
            table = str(job["resource_type"])
            if table not in STRUCTURED_TABLES:
                raise ValueError("Upload is not a structured resource")
            records = list(job["normalized_records"] or [])
            for record in records:
                values = dict(record)
                if values.get("tenant_id") != tenant_id:
                    raise ValueError("Normalized upload record crossed the tenant boundary")
                values["source_system"] = "user_upload"
                values["source_file"] = f"upload:{upload_id}/{job['original_filename']}"
                columns = list(values)
                statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    sql.Identifier(table),
                    sql.SQL(", ").join(map(sql.Identifier, columns)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in columns),
                )
                connection.execute(statement, [values[column] for column in columns])
            updated = connection.execute(
                """
                UPDATE upload_jobs SET status = 'committed', committed_at = now()
                WHERE tenant_id = %s AND upload_id = %s RETURNING *
                """,
                (tenant_id, upload_id),
            ).fetchone()
        assert updated is not None
        return self._to_job(updated), len(records)

    @staticmethod
    def _to_job(row: Mapping[str, Any]) -> UploadJob:
        private_fields = {"raw_content", "normalized_records"}
        public = {key: value for key, value in row.items() if key not in private_fields}
        return UploadJob.model_validate(public)
