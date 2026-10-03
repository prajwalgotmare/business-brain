from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from business_brain.analytics.repository import (
    FREIGHT_RECONCILIATION_SQL,
    MARGIN_WEEKS_SQL,
    OVERDUE_INVOICE_SQL,
    STOCKOUT_RISK_SQL,
    AnalyticsRepository,
)
from business_brain.analytics.service import (
    AnalyticsAccessDeniedError,
    GovernedAnalyticsService,
)
from business_brain.core.config import Settings
from business_brain.security.context import AuthContext, UserRole


class StubRepository:
    def __init__(self) -> None:
        self.calls = []

    def stockout_risks(self, tenant_id, limit):
        self.calls.append(("stockout", tenant_id, limit))
        return [
            {
                "product_id": "prd_aur_006",
                "sku": "AUR-SKN-006",
                "warehouse_id": "wh_aur_west",
                "snapshot_at": datetime(2026, 9, 21, 23, 59, 59, tzinfo=UTC),
                "available_quantity": 2,
                "reorder_point": 59,
                "demand_14d": 7,
                "projected_demand_7d": Decimal("3.50"),
                "delayed_inbound_quantity": 213,
            }
        ]

    def freight_reconciliation(self, tenant_id, shipment_id):
        self.calls.append(("freight", tenant_id, shipment_id))
        return {
            "shipment_id": shipment_id,
            "vendor_invoice_id": "vin_aur_00034",
            "invoice_number": "FRT-AUR-00034",
            "billed_charge": Decimal("40.35"),
            "manifest_charge": Decimal("22.35"),
            "overbilling_amount": Decimal("18.00"),
            "sla_credit": Decimal("2.24"),
            "sla_delay_minutes": 30414,
            "dispute_amount": Decimal("20.24"),
            "currency_code": "USD",
        }

    def overdue_invoices(self, tenant_id, as_of, limit):
        self.calls.append(("overdue", tenant_id, as_of, limit))
        return []

    def margin_weeks(self, tenant_id, region_id, earlier, later):
        self.calls.append(("margin", tenant_id, region_id, earlier, later))
        base = {
            "region_id": region_id,
            "cost_of_goods_amount": Decimal("100.00"),
            "freight_expense_amount": Decimal("20.00"),
            "net_profit_amount": Decimal("80.00"),
        }
        return [
            base
            | {
                "week_start_date": earlier,
                "revenue_amount": Decimal("200.00"),
                "refund_amount": Decimal("10.00"),
                "net_margin_pct": Decimal("0.3467"),
            },
            base
            | {
                "week_start_date": later,
                "revenue_amount": Decimal("150.00"),
                "refund_amount": Decimal("25.00"),
                "net_margin_pct": Decimal("0.2069"),
            },
        ]


def auth(role: UserRole, tenant_id: str = "tenant_aura") -> AuthContext:
    return AuthContext(tenant_id=tenant_id, user_id="test-user", role=role)


def test_fixed_sql_is_read_only_and_tenant_scoped() -> None:
    forbidden = (" INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ")
    for statement in (
        STOCKOUT_RISK_SQL,
        FREIGHT_RECONCILIATION_SQL,
        OVERDUE_INVOICE_SQL,
        MARGIN_WEEKS_SQL,
    ):
        normalized = f" {statement.upper()} "
        assert statement.lstrip().upper().startswith(("SELECT", "WITH"))
        assert "%(tenant_id)s" in statement
        assert not any(keyword in normalized for keyword in forbidden)


def test_repository_fails_closed_without_tenant_parameter_and_predicate() -> None:
    def connection_must_not_run():
        raise AssertionError("database connection must not open")

    repository = AnalyticsRepository(
        settings=Settings(_env_file=None),
        connection_factory=connection_must_not_run,
    )
    with pytest.raises(ValueError, match="authenticated tenant"):
        repository._query("SELECT 1", {})
    with pytest.raises(ValueError, match="tenant predicate"):
        repository._query("SELECT 1", {"tenant_id": "tenant_aura"})


def test_roles_are_checked_before_repository_access() -> None:
    repository = StubRepository()
    service = GovernedAnalyticsService(repository)

    with pytest.raises(AnalyticsAccessDeniedError):
        service.stockout_risks(auth(UserRole.SUPPORT_INTERN))
    with pytest.raises(AnalyticsAccessDeniedError):
        service.freight_reconciliation(auth(UserRole.LOGISTICS_MANAGER), "shp_aur_000021")
    with pytest.raises(AnalyticsAccessDeniedError):
        service.overdue_invoices(auth(UserRole.LOGISTICS_MANAGER), as_of=date(2026, 9, 21))
    with pytest.raises(AnalyticsAccessDeniedError):
        service.margin_variance(
            auth(UserRole.STAFF_ACCOUNTANT),
            region_id="reg_aur_west",
            earlier=date(2026, 8, 17),
            later=date(2026, 8, 24),
        )
    assert repository.calls == []


def test_services_pass_authenticated_tenant_and_validate_results() -> None:
    repository = StubRepository()
    service = GovernedAnalyticsService(repository)

    risk = service.stockout_risks(auth(UserRole.LOGISTICS_MANAGER))[0]
    freight = service.freight_reconciliation(
        auth(UserRole.STAFF_ACCOUNTANT), "shp_aur_000021"
    )
    margin = service.margin_variance(
        auth(UserRole.FOUNDER_CFO),
        region_id="reg_aur_west",
        earlier=date(2026, 8, 17),
        later=date(2026, 8, 24),
    )

    assert risk.delayed_inbound_quantity == 213
    assert freight is not None and freight.dispute_amount == Decimal("20.24")
    assert margin is not None
    assert margin.margin_change_percentage_points == Decimal("-13.98")
    assert all(call[1] == "tenant_aura" for call in repository.calls)


def test_margin_dates_must_be_ordered() -> None:
    service = GovernedAnalyticsService(StubRepository())
    with pytest.raises(ValueError, match="later week"):
        service.margin_variance(
            auth(UserRole.FOUNDER_CFO),
            region_id="reg_aur_west",
            earlier=date(2026, 8, 24),
            later=date(2026, 8, 17),
        )
