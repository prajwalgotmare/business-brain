"""Role-governed analytics service reusable by APIs and future agent tools."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from business_brain.analytics.repository import AnalyticsRepository
from business_brain.analytics.schemas import (
    FreightReconciliation,
    MarginVariance,
    MarginWeek,
    OverdueInvoice,
    StockoutRisk,
)
from business_brain.security.context import AuthContext, UserRole


class AnalyticsAccessDeniedError(PermissionError):
    pass


def _require_role(auth: AuthContext, allowed: set[UserRole]) -> None:
    if auth.role not in allowed:
        raise AnalyticsAccessDeniedError(f"Role {auth.role.value} cannot use this analytic")


class GovernedAnalyticsService:
    def __init__(self, repository: AnalyticsRepository) -> None:
        self.repository = repository

    def stockout_risks(self, auth: AuthContext, *, limit: int = 20) -> list[StockoutRisk]:
        _require_role(auth, {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER})
        return [
            StockoutRisk.model_validate(row)
            for row in self.repository.stockout_risks(auth.tenant_id, limit)
        ]

    def freight_reconciliation(
        self, auth: AuthContext, shipment_id: str
    ) -> FreightReconciliation | None:
        _require_role(auth, {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT})
        row = self.repository.freight_reconciliation(auth.tenant_id, shipment_id)
        return FreightReconciliation.model_validate(row) if row else None

    def overdue_invoices(
        self, auth: AuthContext, *, as_of: date, limit: int = 50
    ) -> list[OverdueInvoice]:
        _require_role(auth, {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT})
        return [
            OverdueInvoice.model_validate(row)
            for row in self.repository.overdue_invoices(auth.tenant_id, as_of, limit)
        ]

    def margin_variance(
        self, auth: AuthContext, *, region_id: str, earlier: date, later: date
    ) -> MarginVariance | None:
        _require_role(auth, {UserRole.FOUNDER_CFO})
        if later <= earlier:
            raise ValueError("later week must be after earlier week")
        rows = list(self.repository.margin_weeks(auth.tenant_id, region_id, earlier, later))
        if not rows:
            return None
        if len(rows) != 2:
            raise RuntimeError("Both requested margin weeks must exist")
        first = MarginWeek.model_validate(rows[0])
        second = MarginWeek.model_validate(rows[1])
        percentage_points = ((second.net_margin_pct - first.net_margin_pct) * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return MarginVariance(
            region_id=region_id,
            earlier=first,
            later=second,
            margin_change_percentage_points=percentage_points,
            revenue_change_amount=second.revenue_amount - first.revenue_amount,
            refund_change_amount=second.refund_amount - first.refund_amount,
        )
