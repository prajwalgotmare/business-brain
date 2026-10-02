"""Generate or verify tenant-separated logistics CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from business_brain.data import (
    LogisticsDataset,
    build_commerce_inventory_dataset,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.models import StrictModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = PROJECT_ROOT / "data" / "generated"
SCHEMA_PATH = PROJECT_ROOT / "data" / "schemas" / "logistics.schema.json"
TENANT_DIRECTORIES = {
    "tenant_aura": "aura_brands",
    "tenant_apex": "apex_retail",
}
CSV_COLLECTIONS = (
    "shipments",
    "shipment_items",
    "tracking_events",
    "carrier_sla_facts",
    "delivery_exceptions",
    "carrier_manifest_entries",
)


def _csv_text(records: list[StrictModel]) -> str:
    if not records:
        raise ValueError("CSV collections must not be empty")
    fieldnames = list(type(records[0]).model_fields)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow(record.model_dump(mode="json"))
    return output.getvalue()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def render_artifacts() -> dict[Path, str]:
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    dataset = build_logistics_dataset(catalog, commerce)
    artifacts: dict[Path, str] = {
        SCHEMA_PATH: _canonical_json(LogisticsDataset.model_json_schema())
    }
    for tenant_id, directory_name in TENANT_DIRECTORIES.items():
        for collection_name in CSV_COLLECTIONS:
            records = [
                record
                for record in getattr(dataset, collection_name)
                if record.tenant_id == tenant_id
            ]
            path = GENERATED_ROOT / directory_name / f"{collection_name}.csv"
            artifacts[path] = _csv_text(records)
    return artifacts


def write_artifacts(artifacts: dict[Path, str]) -> None:
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def verify_artifacts(artifacts: dict[Path, str]) -> list[Path]:
    return [
        path
        for path, expected in artifacts.items()
        if not path.exists() or path.read_text(encoding="utf-8") != expected
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when committed logistics CSV/schema artifacts are stale.",
    )
    args = parser.parse_args()
    artifacts = render_artifacts()

    if args.check:
        stale = verify_artifacts(artifacts)
        if stale:
            for path in stale:
                print(f"stale: {path.relative_to(PROJECT_ROOT)}")
            return 1
        print("logistics artifacts are current")
        return 0

    write_artifacts(artifacts)
    for path in artifacts:
        print(f"wrote: {path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
