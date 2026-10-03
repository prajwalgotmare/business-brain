"""Verify governed SQL analytics against locked synthetic scenario answers."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from business_brain.analytics.repository import AnalyticsRepository
from business_brain.analytics.service import GovernedAnalyticsService
from business_brain.core.config import Settings
from business_brain.security.context import AuthContext, UserRole

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "quality" / "sql_analytics_smoke.json"


def _auth(tenant_id: str, role: UserRole) -> AuthContext:
    return AuthContext(tenant_id=tenant_id, user_id="analytics-smoke", role=role)


def _timed(operation):
    started = perf_counter()
    result = operation()
    return result, round((perf_counter() - started) * 1_000, 2)


def main() -> None:
    service = GovernedAnalyticsService(AnalyticsRepository(settings=Settings()))
    logistics = _auth("tenant_aura", UserRole.LOGISTICS_MANAGER)
    accountant = _auth("tenant_aura", UserRole.STAFF_ACCOUNTANT)
    cfo = _auth("tenant_aura", UserRole.FOUNDER_CFO)

    risks, risk_ms = _timed(lambda: service.stockout_risks(logistics, limit=20))
    risk = next(
        item
        for item in risks
        if item.product_id == "prd_aur_006" and item.warehouse_id == "wh_aur_west"
    )
    assert risk.available_quantity == 2
    assert risk.demand_14d == 7
    assert risk.projected_demand_7d == Decimal("3.50")
    assert risk.delayed_inbound_quantity == 213

    freight, freight_ms = _timed(
        lambda: service.freight_reconciliation(accountant, "shp_aur_000021")
    )
    assert freight is not None
    assert freight.billed_charge == Decimal("40.35")
    assert freight.manifest_charge == Decimal("22.35")
    assert freight.overbilling_amount == Decimal("18.00")
    assert freight.sla_credit == Decimal("2.24")
    assert freight.dispute_amount == Decimal("20.24")

    invoices, invoices_ms = _timed(
        lambda: service.overdue_invoices(
            accountant,
            as_of=date(2026, 9, 21),
            limit=100,
        )
    )
    invoice = next(item for item in invoices if item.vendor_invoice_id == "vin_aur_00010")
    assert invoice.due_date == date(2026, 9, 13)
    assert invoice.days_overdue == 8
    assert invoice.outstanding_amount == Decimal("4108.68")

    margin, margin_ms = _timed(
        lambda: service.margin_variance(
            cfo,
            region_id="reg_aur_west",
            earlier=date(2026, 8, 17),
            later=date(2026, 8, 24),
        )
    )
    assert margin is not None
    assert margin.earlier.revenue_amount == Decimal("3892.75")
    assert margin.later.revenue_amount == Decimal("2300.48")
    assert margin.later.refund_amount == Decimal("580.17")
    assert margin.margin_change_percentage_points == Decimal("-13.98")

    apex = _auth("tenant_apex", UserRole.FOUNDER_CFO)
    assert service.freight_reconciliation(apex, "shp_aur_000021") is None
    assert (
        service.margin_variance(
            apex,
            region_id="reg_aur_west",
            earlier=date(2026, 8, 17),
            later=date(2026, 8, 24),
        )
        is None
    )

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "transaction_mode": "read_only",
        "parameterized_queries": 4,
        "scenario_checks": {
            "stockout_risk": "passed",
            "freight_reconciliation": "passed",
            "overdue_invoices": "passed",
            "margin_variance": "passed",
        },
        "latency_ms": {
            "stockout_risk": risk_ms,
            "freight_reconciliation": freight_ms,
            "overdue_invoices": invoices_ms,
            "margin_variance": margin_ms,
        },
        "cross_tenant_leak_count": 0,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Verified SQL analytics: 4")
    print("Cross-tenant leaks: 0")


if __name__ == "__main__":
    main()
