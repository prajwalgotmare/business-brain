"""Versioned PostgreSQL migrations and idempotent fixture ingestion."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg import sql

from business_brain.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = Path(__file__).with_name("migrations")
REFERENCE_FILE = PROJECT_ROOT / "data" / "seeds" / "reference_catalog.json"
GENERATED_DIR = PROJECT_ROOT / "data" / "generated"

REFERENCE_TABLES = ("tenants", "regions", "products", "warehouses", "suppliers", "carriers")
CSV_TABLE_ORDER = (
    "customers",
    "orders",
    "purchase_orders",
    "shipments",
    "order_lines",
    "inventory_balances",
    "purchase_order_lines",
    "inventory_movements",
    "tracking_events",
    "delivery_exceptions",
    "shipment_items",
    "carrier_sla_facts",
    "carrier_manifest_entries",
    "vendor_invoices",
    "vendor_invoice_lines",
    "payments",
    "regional_margin_snapshots",
)


@dataclass(frozen=True)
class IngestionReport:
    migration_count: int
    table_counts: dict[str, int]

    @property
    def total_rows(self) -> int:
        return sum(self.table_counts.values())


def connection_url(settings: Settings | None = None) -> str:
    """Return the direct URL for administrative jobs without logging its value."""
    current = settings or Settings()
    url = current.database_url_direct or current.database_url
    if not url:
        raise RuntimeError("DATABASE_URL_DIRECT or DATABASE_URL must be configured")
    return url


def _migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def apply_migrations(conn: psycopg.Connection[tuple[object, ...]]) -> int:
    """Apply immutable SQL migrations once, guarded by their SHA-256 checksums."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY,
            checksum char(64) NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    applied = 0
    for path in _migration_files():
        content = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(content.encode()).hexdigest()
        existing = conn.execute(
            "SELECT checksum FROM schema_migrations WHERE version = %s", (path.name,)
        ).fetchone()
        if existing:
            if existing[0] != checksum:
                raise RuntimeError(f"Applied migration was modified: {path.name}")
            continue
        conn.execute(content)
        conn.execute(
            "INSERT INTO schema_migrations (version, checksum) VALUES (%s, %s)",
            (path.name, checksum),
        )
        applied += 1
    return applied


def _clean_row(row: Mapping[str, object], source_file: str) -> dict[str, object]:
    cleaned = {key: (None if value == "" else value) for key, value in row.items()}
    cleaned["source_system"] = "demo_generator"
    cleaned["source_file"] = source_file
    return cleaned


def _upsert_rows(
    conn: psycopg.Connection[tuple[object, ...]], table: str, rows: Iterable[Mapping[str, object]]
) -> int:
    row_list = list(rows)
    if not row_list:
        return 0
    columns = list(row_list[0])
    id_columns = ["tenant_id"] if table == "tenants" else ["tenant_id", _id_column(table)]
    updates = [column for column in columns if column not in id_columns]
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.SQL(", ").join(map(sql.Identifier, id_columns)),
        sql.SQL(", ").join(
            sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(column), sql.Identifier(column))
            for column in updates
        ),
    )
    with conn.cursor() as cursor:
        cursor.executemany(
            statement,
            ([row[column] for column in columns] for row in row_list),
        )
    return len(row_list)


def _id_column(table: str) -> str:
    exceptions = {
        "regions": "region_id",
        "products": "product_id",
        "warehouses": "warehouse_id",
        "suppliers": "supplier_id",
        "carriers": "carrier_id",
        "carrier_manifest_entries": "manifest_entry_id",
        "regional_margin_snapshots": "margin_snapshot_id",
    }
    if table in exceptions:
        return exceptions[table]
    return table.removesuffix("s") + "_id"


def _reference_rows() -> dict[str, list[dict[str, object]]]:
    catalog = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    return {
        table: [
            _clean_row(row, REFERENCE_FILE.relative_to(PROJECT_ROOT).as_posix())
            for row in catalog[table]
        ]
        for table in REFERENCE_TABLES
    }


def _csv_rows(table: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for tenant_dir in sorted(path for path in GENERATED_DIR.iterdir() if path.is_dir()):
        path = tenant_dir / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(
                _clean_row(row, path.relative_to(PROJECT_ROOT).as_posix())
                for row in csv.DictReader(handle)
            )
    return rows


def seed_demo_data(conn: psycopg.Connection[tuple[object, ...]]) -> dict[str, int]:
    """Upsert both demo tenants in dependency order inside the caller transaction."""
    counts: dict[str, int] = {}
    references = _reference_rows()
    for table in REFERENCE_TABLES:
        counts[table] = _upsert_rows(conn, table, references[table])
    for table in CSV_TABLE_ORDER:
        counts[table] = _upsert_rows(conn, table, _csv_rows(table))
    return counts


def verify_database(conn: psycopg.Connection[tuple[object, ...]]) -> dict[str, int]:
    """Return counts and reject missing tenant boundaries or fixture count drift."""
    expected = {table: len(rows) for table, rows in _reference_rows().items()}
    expected.update({table: len(_csv_rows(table)) for table in CSV_TABLE_ORDER})
    actual: dict[str, int] = {}
    for table, expected_count in expected.items():
        count_query = sql.SQL(
            "SELECT count(*) FROM {} WHERE source_system = 'demo_generator'"
        ).format(sql.Identifier(table))
        count = conn.execute(count_query).fetchone()[0]
        null_tenants = conn.execute(
            sql.SQL(
                "SELECT count(*) FROM {} "
                "WHERE source_system = 'demo_generator' AND tenant_id IS NULL"
            ).format(sql.Identifier(table))
        ).fetchone()[0]
        if null_tenants:
            raise RuntimeError(f"{table} contains {null_tenants} rows without tenant_id")
        if count != expected_count:
            raise RuntimeError(f"{table} row-count drift: expected {expected_count}, found {count}")
        expected_rows = (
            _reference_rows()[table] if table in REFERENCE_TABLES else _csv_rows(table)
        )
        expected_tenants = Counter(str(row["tenant_id"]) for row in expected_rows)
        tenant_query = sql.SQL(
            "SELECT tenant_id, count(*) FROM {} WHERE source_system = 'demo_generator' "
            "GROUP BY tenant_id ORDER BY tenant_id"
        ).format(sql.Identifier(table))
        actual_tenants = Counter(dict(conn.execute(tenant_query).fetchall()))
        if actual_tenants != expected_tenants:
            raise RuntimeError(f"{table} tenant-count drift")
        actual[table] = count
    return actual


def migrate_seed_verify(settings: Settings | None = None) -> IngestionReport:
    """Run the complete transaction; rollback all work if any validation fails."""
    with psycopg.connect(connection_url(settings)) as conn:
        migrations = apply_migrations(conn)
        counts = seed_demo_data(conn)
        verified = verify_database(conn)
    if counts != verified:
        raise RuntimeError("Seeded and verified table counts differ")
    return IngestionReport(migration_count=migrations, table_counts=verified)
