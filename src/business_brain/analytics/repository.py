"""Fixed, parameterized PostgreSQL queries executed in read-only transactions."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from datetime import date
from typing import Any

import psycopg
from psycopg.rows import dict_row

from business_brain.core.config import Settings

Row = Mapping[str, Any]
ConnectionFactory = Callable[[], psycopg.Connection]

STOCKOUT_RISK_SQL = """
WITH latest_snapshot AS (
    SELECT max(snapshot_at) AS snapshot_at
    FROM inventory_balances
    WHERE tenant_id = %(tenant_id)s
), recent_demand AS (
    SELECT c.region_id, ol.product_id, sum(ol.quantity)::integer AS demand_14d
    FROM orders o
    JOIN order_lines ol ON ol.tenant_id = o.tenant_id AND ol.order_id = o.order_id
    JOIN customers c ON c.tenant_id = o.tenant_id AND c.customer_id = o.customer_id
    CROSS JOIN latest_snapshot ls
    WHERE o.tenant_id = %(tenant_id)s
      AND o.order_timestamp >= ls.snapshot_at - interval '14 days'
      AND o.order_timestamp <= ls.snapshot_at
      AND o.order_status IN ('allocated', 'shipped', 'delivered', 'returned')
    GROUP BY c.region_id, ol.product_id
), delayed_inbound AS (
    SELECT s.destination_warehouse_id AS warehouse_id, si.product_id,
           sum(si.expected_quantity - si.received_quantity)::integer AS delayed_quantity
    FROM shipments s
    JOIN shipment_items si ON si.tenant_id = s.tenant_id AND si.shipment_id = s.shipment_id
    WHERE s.tenant_id = %(tenant_id)s
      AND s.shipment_direction = 'inbound'
      AND s.shipment_status IN ('delayed', 'exception')
      AND s.delivered_at IS NULL
    GROUP BY s.destination_warehouse_id, si.product_id
)
SELECT ib.product_id, p.sku, ib.warehouse_id, ib.snapshot_at,
       ib.available_quantity, p.reorder_point, coalesce(rd.demand_14d, 0) AS demand_14d,
       round(coalesce(rd.demand_14d, 0)::numeric / 2, 2) AS projected_demand_7d,
       coalesce(di.delayed_quantity, 0) AS delayed_inbound_quantity
FROM inventory_balances ib
JOIN latest_snapshot ls ON ls.snapshot_at = ib.snapshot_at
JOIN products p ON p.tenant_id = ib.tenant_id AND p.product_id = ib.product_id
JOIN warehouses w ON w.tenant_id = ib.tenant_id AND w.warehouse_id = ib.warehouse_id
LEFT JOIN recent_demand rd ON rd.region_id = w.region_id AND rd.product_id = ib.product_id
LEFT JOIN delayed_inbound di ON di.warehouse_id = ib.warehouse_id AND di.product_id = ib.product_id
WHERE ib.tenant_id = %(tenant_id)s
  AND ib.available_quantity < coalesce(rd.demand_14d, 0)::numeric / 2
  AND coalesce(di.delayed_quantity, 0) > 0
ORDER BY (coalesce(rd.demand_14d, 0)::numeric / 2 - ib.available_quantity) DESC,
         di.delayed_quantity DESC, p.sku
LIMIT %(limit)s
"""

FREIGHT_RECONCILIATION_SQL = """
WITH billed AS (
    SELECT vil.tenant_id, vil.shipment_id, vil.vendor_invoice_id,
           sum(vil.line_amount) AS billed_charge
    FROM vendor_invoice_lines vil
    WHERE vil.tenant_id = %(tenant_id)s AND vil.shipment_id = %(shipment_id)s
    GROUP BY vil.tenant_id, vil.shipment_id, vil.vendor_invoice_id
), manifest AS (
    SELECT tenant_id, shipment_id, sum(reported_charge_amount) AS manifest_charge
    FROM carrier_manifest_entries
    WHERE tenant_id = %(tenant_id)s AND shipment_id = %(shipment_id)s
    GROUP BY tenant_id, shipment_id
)
SELECT b.shipment_id, b.vendor_invoice_id, vi.invoice_number, b.billed_charge,
       m.manifest_charge,
       greatest(b.billed_charge - m.manifest_charge, 0) AS overbilling_amount,
       sla.provisional_credit_amount AS sla_credit, sla.delay_minutes AS sla_delay_minutes,
       greatest(b.billed_charge - m.manifest_charge, 0) + sla.provisional_credit_amount
           AS dispute_amount,
       vi.currency_code
FROM billed b
JOIN manifest m ON m.tenant_id = b.tenant_id AND m.shipment_id = b.shipment_id
JOIN vendor_invoices vi
  ON vi.tenant_id = b.tenant_id AND vi.vendor_invoice_id = b.vendor_invoice_id
JOIN carrier_sla_facts sla
  ON sla.tenant_id = b.tenant_id AND sla.shipment_id = b.shipment_id
WHERE b.tenant_id = %(tenant_id)s
"""

OVERDUE_INVOICE_SQL = """
SELECT vi.vendor_invoice_id, vi.invoice_number, vi.supplier_id, s.supplier_name,
       vi.due_date, (%(as_of)s::date - vi.due_date)::integer AS days_overdue,
       vi.outstanding_amount, vi.currency_code
FROM vendor_invoices vi
JOIN suppliers s ON s.tenant_id = vi.tenant_id AND s.supplier_id = vi.supplier_id
WHERE vi.tenant_id = %(tenant_id)s
  AND vi.due_date < %(as_of)s::date
  AND vi.outstanding_amount > 0
  AND vi.invoice_status IN ('open', 'partially_paid', 'overdue', 'disputed')
ORDER BY vi.due_date, vi.vendor_invoice_id
LIMIT %(limit)s
"""

MARGIN_WEEKS_SQL = """
SELECT region_id, week_start_date, revenue_amount, cost_of_goods_amount,
       freight_expense_amount, refund_amount, net_profit_amount, net_margin_pct
FROM regional_margin_snapshots
WHERE tenant_id = %(tenant_id)s
  AND region_id = %(region_id)s
  AND week_start_date IN (%(earlier)s::date, %(later)s::date)
ORDER BY week_start_date
"""


class AnalyticsRepository:
    def __init__(
        self,
        *,
        settings: Settings,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if not settings.database_url and connection_factory is None:
            raise RuntimeError("DATABASE_URL must be configured for analytics")
        self._settings = settings
        self._connection_factory = connection_factory or self._default_connection

    def _default_connection(self) -> psycopg.Connection:
        assert self._settings.database_url is not None
        return psycopg.connect(self._settings.database_url, row_factory=dict_row)

    def _query(self, statement: str, parameters: Mapping[str, object]) -> list[Row]:
        normalized = statement.lstrip().upper()
        if not normalized.startswith(("SELECT", "WITH")):
            raise ValueError("Analytics repository permits read-only statements only")
        tenant_id = parameters.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise ValueError("Analytics queries require an authenticated tenant")
        if "%(tenant_id)s" not in statement:
            raise ValueError("Analytics query is missing its tenant predicate")
        with closing(self._connection_factory()) as connection, connection.transaction():
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(int(self._settings.database_statement_timeout_seconds * 1_000)),),
            )
            connection.execute(
                "SELECT set_config('app.current_tenant_id', %s, true)",
                (tenant_id,),
            )
            return list(connection.execute(statement, parameters).fetchall())

    def stockout_risks(self, tenant_id: str, limit: int) -> Sequence[Row]:
        return self._query(STOCKOUT_RISK_SQL, {"tenant_id": tenant_id, "limit": limit})

    def freight_reconciliation(self, tenant_id: str, shipment_id: str) -> Row | None:
        rows = self._query(
            FREIGHT_RECONCILIATION_SQL,
            {"tenant_id": tenant_id, "shipment_id": shipment_id},
        )
        return rows[0] if rows else None

    def overdue_invoices(self, tenant_id: str, as_of: date, limit: int) -> Sequence[Row]:
        return self._query(
            OVERDUE_INVOICE_SQL,
            {"tenant_id": tenant_id, "as_of": as_of, "limit": limit},
        )

    def margin_weeks(
        self, tenant_id: str, region_id: str, earlier: date, later: date
    ) -> Sequence[Row]:
        return self._query(
            MARGIN_WEEKS_SQL,
            {
                "tenant_id": tenant_id,
                "region_id": region_id,
                "earlier": earlier,
                "later": later,
            },
        )
