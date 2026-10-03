from pathlib import Path

import pytest

from business_brain.core.config import Settings
from business_brain.db import ingestion


def test_all_fixture_tables_have_rows_and_tenant_ids() -> None:
    reference = ingestion._reference_rows()
    assert set(reference) == set(ingestion.REFERENCE_TABLES)
    for rows in reference.values():
        assert rows
        assert all(row["tenant_id"] for row in rows)

    for table in ingestion.CSV_TABLE_ORDER:
        rows = ingestion._csv_rows(table)
        assert rows, table
        assert {row["tenant_id"] for row in rows} == {"tenant_aura", "tenant_apex"}


def test_migrations_are_versioned_and_nonempty() -> None:
    files = ingestion._migration_files()
    assert [path.name for path in files] == ["001_initial.sql"]
    assert "CREATE TABLE tenants" in files[0].read_text(encoding="utf-8")


def test_direct_database_url_has_priority() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://pooled.example/test",
        database_url_direct="postgresql://direct.example/test",
    )
    assert ingestion.connection_url(settings) == "postgresql://direct.example/test"


def test_missing_database_url_fails_without_exposing_secrets() -> None:
    with pytest.raises(RuntimeError, match="must be configured"):
        ingestion.connection_url(Settings(_env_file=None))


def test_fixture_paths_are_inside_project() -> None:
    assert ingestion.REFERENCE_FILE.is_relative_to(ingestion.PROJECT_ROOT)
    assert Path(ingestion.GENERATED_DIR).is_relative_to(ingestion.PROJECT_ROOT)
