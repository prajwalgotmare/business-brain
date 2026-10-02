"""Generate or verify tenant-separated procurement and finance artifacts."""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from business_brain.data import (
    FinanceDataset,
    build_commerce_inventory_dataset,
    build_finance_dataset,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.finance_generator import PUBLIC_CALIBRATION
from business_brain.data.models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = PROJECT_ROOT / "data" / "generated"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schemas" / "finance.schema.json"
CALIBRATION_PATH = PROJECT_ROOT / "data" / "sources" / "public_calibration.json"
TENANT_DIRECTORIES = {
    "tenant_aura": "aura_brands",
    "tenant_apex": "apex_retail",
}
CSV_COLLECTIONS = (
    "purchase_orders",
    "purchase_order_lines",
    "vendor_invoices",
    "vendor_invoice_lines",
    "payments",
    "regional_margin_snapshots",
)


def _csv_text(records: list[StrictModel]) -> str:
    if not records:
        raise ValueError("CSV collections must not be empty")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=list(type(records[0]).model_fields),
        lineterminator="\n",
    )
    writer.writeheader()
    for record in records:
        writer.writerow(record.model_dump(mode="json"))
    return output.getvalue()


def _json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_artifacts() -> dict[Path, str]:
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    logistics = build_logistics_dataset(catalog, commerce)
    dataset = build_finance_dataset(catalog, commerce, logistics)
    artifacts = {
        SCHEMA_PATH: _json(FinanceDataset.model_json_schema()),
        CALIBRATION_PATH: _json(PUBLIC_CALIBRATION),
    }
    for tenant_id, directory_name in TENANT_DIRECTORIES.items():
        for collection_name in CSV_COLLECTIONS:
            records = [
                record
                for record in getattr(dataset, collection_name)
                if record.tenant_id == tenant_id
            ]
            artifacts[
                GENERATED_ROOT / directory_name / f"{collection_name}.csv"
            ] = _csv_text(records)
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    artifacts = render_artifacts()
    if args.check:
        stale = [
            path
            for path, expected in artifacts.items()
            if not path.exists() or path.read_text(encoding="utf-8") != expected
        ]
        for path in stale:
            print(f"stale: {path.relative_to(PROJECT_ROOT)}")
        if stale:
            return 1
        print("finance artifacts are current")
        return 0
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
