import csv
import json
from pathlib import Path

from business_brain.data import LogisticsDataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_ROOT = PROJECT_ROOT / "data" / "generated"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_every_tenant_export_has_all_six_logistics_collections() -> None:
    expected_files = {
        "shipments.csv",
        "shipment_items.csv",
        "tracking_events.csv",
        "carrier_sla_facts.csv",
        "delivery_exceptions.csv",
        "carrier_manifest_entries.csv",
    }
    for directory in ("aura_brands", "apex_retail"):
        actual = {
            path.name
            for path in (GENERATED_ROOT / directory).glob("*.csv")
            if path.name in expected_files
        }
        assert actual == expected_files


def test_logistics_csv_exports_are_tenant_isolated() -> None:
    filenames = (
        "shipments.csv",
        "shipment_items.csv",
        "tracking_events.csv",
        "carrier_sla_facts.csv",
        "delivery_exceptions.csv",
        "carrier_manifest_entries.csv",
    )
    for directory, tenant_id in (
        ("aura_brands", "tenant_aura"),
        ("apex_retail", "tenant_apex"),
    ):
        for filename in filenames:
            rows = _rows(GENERATED_ROOT / directory / filename)
            assert rows
            assert {row["tenant_id"] for row in rows} == {tenant_id}


def test_logistics_json_schema_is_committed() -> None:
    schema_path = PROJECT_ROOT / "data" / "schemas" / "logistics.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == LogisticsDataset.__name__
    assert schema["additionalProperties"] is False
    assert {
        "Shipment",
        "ShipmentItem",
        "TrackingEvent",
        "CarrierSlaFact",
        "DeliveryException",
        "CarrierManifestEntry",
    } <= set(schema["$defs"])
