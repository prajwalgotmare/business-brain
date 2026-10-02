import csv
import json
from pathlib import Path

from business_brain.data.finance_generator import PUBLIC_CALIBRATION

ROOT = Path(__file__).resolve().parents[2]


def test_finance_schema_and_public_calibration_are_committed() -> None:
    schema = json.loads((ROOT / "data/schemas/finance.schema.json").read_text())
    calibration = json.loads((ROOT / "data/sources/public_calibration.json").read_text())
    assert schema["title"] == "FinanceDataset"
    assert calibration == PUBLIC_CALIBRATION
    assert calibration["sources"][0]["license"] == "CC BY 4.0"


def test_finance_csvs_are_nonempty_and_tenant_scoped() -> None:
    names = {
        "purchase_orders.csv",
        "purchase_order_lines.csv",
        "vendor_invoices.csv",
        "vendor_invoice_lines.csv",
        "payments.csv",
        "regional_margin_snapshots.csv",
    }
    for directory, tenant_id in (
        ("aura_brands", "tenant_aura"),
        ("apex_retail", "tenant_apex"),
    ):
        for name in names:
            path = ROOT / "data/generated" / directory / name
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            assert rows
            assert {row["tenant_id"] for row in rows} == {tenant_id}
