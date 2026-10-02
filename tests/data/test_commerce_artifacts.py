import csv
import json
from pathlib import Path

from business_brain.data.commerce_models import CommerceInventoryDataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_ROOT = PROJECT_ROOT / "data" / "generated"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def test_tenant_csv_exports_have_expected_counts_and_boundaries() -> None:
    aura_root = GENERATED_ROOT / "aura_brands"
    apex_root = GENERATED_ROOT / "apex_retail"

    expected_counts = {
        aura_root / "customers.csv": 180,
        aura_root / "orders.csv": 500,
        aura_root / "inventory_balances.csv": 150,
        apex_root / "customers.csv": 30,
        apex_root / "orders.csv": 80,
        apex_root / "inventory_balances.csv": 16,
    }
    for path, expected_count in expected_counts.items():
        rows = _rows(path)
        assert len(rows) == expected_count
        expected_tenant = "tenant_aura" if "aura_brands" in path.parts else "tenant_apex"
        assert {row["tenant_id"] for row in rows} == {expected_tenant}


def test_every_tenant_export_has_all_five_csv_collections() -> None:
    expected_files = {
        "customers.csv",
        "orders.csv",
        "order_lines.csv",
        "inventory_balances.csv",
        "inventory_movements.csv",
    }

    assert {path.name for path in (GENERATED_ROOT / "aura_brands").glob("*.csv")} == expected_files
    assert {path.name for path in (GENERATED_ROOT / "apex_retail").glob("*.csv")} == expected_files


def test_commerce_json_schema_is_committed() -> None:
    schema_path = PROJECT_ROOT / "data" / "schemas" / "commerce_inventory.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert schema["title"] == CommerceInventoryDataset.__name__
    assert schema["additionalProperties"] is False
    assert {"Customer", "Order", "OrderLine", "InventoryBalance", "InventoryMovement"} <= set(
        schema["$defs"]
    )
