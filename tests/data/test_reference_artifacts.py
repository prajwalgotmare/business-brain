import json
from pathlib import Path

from business_brain.data import ReferenceCatalog

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_committed_reference_catalog_matches_schema() -> None:
    catalog_path = PROJECT_ROOT / "data" / "seeds" / "reference_catalog.json"

    catalog = ReferenceCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))

    assert catalog.schema_version == "1.0"
    assert len(catalog.products) == 58


def test_machine_readable_schema_is_committed() -> None:
    schema_path = PROJECT_ROOT / "data" / "schemas" / "reference_catalog.schema.json"

    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == "ReferenceCatalog"
    assert schema["additionalProperties"] is False
    assert {"Tenant", "Region", "Product", "Warehouse", "Supplier", "Carrier"} <= set(
        schema["$defs"]
    )
