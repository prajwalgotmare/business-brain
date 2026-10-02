from collections import defaultdict
from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_brain.data import (
    FinanceDataset,
    build_commerce_inventory_dataset,
    build_finance_dataset,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.finance_models import PaymentStatus
from business_brain.data.logistics_models import ShipmentDirection
from business_brain.data.scenario_constants import (
    APPROVAL_PURCHASE_ORDER_ID,
    OVERBILLING_AMOUNT,
    OVERBILLING_SHIPMENT_ID,
)


def _sources():
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    logistics = build_logistics_dataset(catalog, commerce)
    return catalog, commerce, logistics


def test_every_inbound_shipment_has_a_reconciled_purchase_order() -> None:
    catalog, commerce, logistics = _sources()
    finance = build_finance_dataset(catalog, commerce, logistics)
    inbound_ids = {
        shipment.purchase_order_id
        for shipment in logistics.shipments
        if shipment.shipment_direction == ShipmentDirection.INBOUND
    }
    purchase_order_ids = {item.purchase_order_id for item in finance.purchase_orders}
    assert inbound_ids < purchase_order_ids
    assert purchase_order_ids - inbound_ids == {APPROVAL_PURCHASE_ORDER_ID}
    assert all(item.approval_required for item in finance.purchase_orders)


def test_invoices_and_completed_payments_reconcile() -> None:
    catalog, commerce, logistics = _sources()
    finance = build_finance_dataset(catalog, commerce, logistics)
    paid: dict[str, Decimal] = defaultdict(Decimal)
    for payment in finance.payments:
        if payment.payment_status == PaymentStatus.COMPLETED:
            paid[payment.vendor_invoice_id] += payment.payment_amount
    for invoice in finance.vendor_invoices:
        assert invoice.total_amount - paid[invoice.vendor_invoice_id] == invoice.outstanding_amount


def test_freight_invoice_lines_reconcile_to_manifests() -> None:
    catalog, commerce, logistics = _sources()
    finance = build_finance_dataset(catalog, commerce, logistics)
    billed: dict[str, Decimal] = defaultdict(Decimal)
    for line in finance.vendor_invoice_lines:
        if line.shipment_id:
            billed[line.shipment_id] += line.line_amount
    expected = {
        manifest.shipment_id: manifest.reported_charge_amount
        for manifest in logistics.carrier_manifest_entries
    }
    expected[OVERBILLING_SHIPMENT_ID] += OVERBILLING_AMOUNT
    assert billed == expected


def test_margin_snapshots_reconcile() -> None:
    catalog, commerce, logistics = _sources()
    finance = build_finance_dataset(catalog, commerce, logistics)
    assert finance.regional_margin_snapshots
    for snapshot in finance.regional_margin_snapshots:
        assert snapshot.net_profit_amount == (
            snapshot.revenue_amount
            - snapshot.cost_of_goods_amount
            - snapshot.freight_expense_amount
            - snapshot.refund_amount
        )


def test_cross_tenant_invoice_reference_is_rejected() -> None:
    catalog, commerce, logistics = _sources()
    payload = build_finance_dataset(catalog, commerce, logistics).model_dump(mode="json")
    payload["vendor_invoices"][0]["tenant_id"] = "tenant_apex"
    with pytest.raises(ValidationError, match="tenant"):
        FinanceDataset.model_validate(payload)
