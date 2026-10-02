from datetime import date
from decimal import Decimal

from business_brain.data import (
    build_commerce_inventory_dataset,
    build_finance_dataset,
    build_ground_truth_manifest,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.finance_models import InvoiceStatus, PurchaseOrderStatus
from business_brain.data.scenario_constants import (
    APPROVAL_PURCHASE_ORDER_ID,
    MARGIN_RETURN_ORDER_IDS,
    OVERBILLING_SHIPMENT_ID,
    OVERDUE_INVOICE_ID,
    STOCKOUT_PRODUCT_ID,
    STOCKOUT_WAREHOUSE_ID,
)
from business_brain.data.scenario_models import ScenarioType


def _datasets():
    catalog = build_reference_catalog()
    commerce = build_commerce_inventory_dataset(catalog)
    logistics = build_logistics_dataset(catalog, commerce)
    finance = build_finance_dataset(catalog, commerce, logistics)
    manifest = build_ground_truth_manifest(catalog, commerce, logistics, finance)
    scenarios = {item.scenario_type: item for item in manifest.scenarios}
    return catalog, commerce, logistics, finance, scenarios


def test_stockout_scenario_has_low_stock_and_delayed_replenishment() -> None:
    _, commerce, _, _, scenarios = _datasets()
    scenario = scenarios[ScenarioType.STOCKOUT_RISK]
    balance = next(
        item
        for item in commerce.inventory_balances
        if item.product_id == STOCKOUT_PRODUCT_ID
        and item.warehouse_id == STOCKOUT_WAREHOUSE_ID
    )
    assert balance.available_quantity == 2
    assert Decimal(scenario.expected_facts["projected_demand_7d"]) > balance.available_quantity
    assert scenario.expected_facts["delayed_inbound_quantity"] == "213"


def test_overbilling_scenario_combines_variance_and_sla_credit() -> None:
    _, _, _, _, scenarios = _datasets()
    facts = scenarios[ScenarioType.CARRIER_OVERBILLING].expected_facts
    assert facts["shipment_id"] == OVERBILLING_SHIPMENT_ID
    assert facts["overbilling_amount"] == "18.00"
    assert facts["sla_credit"] == "2.24"
    assert facts["dispute_amount"] == "20.24"


def test_supplier_terms_scenario_locks_price_tier_and_net_60() -> None:
    _, _, _, _, scenarios = _datasets()
    scenario = scenarios[ScenarioType.SUPPLIER_TERMS]
    assert scenario.expected_facts["unit_price"] == "0.42"
    assert scenario.expected_facts["payment_terms_days"] == "60"
    assert len(scenario.document_dependencies) == 2


def test_overdue_invoice_scenario_references_open_balance() -> None:
    _, _, _, finance, scenarios = _datasets()
    invoice = next(
        item for item in finance.vendor_invoices if item.vendor_invoice_id == OVERDUE_INVOICE_ID
    )
    assert invoice.invoice_status == InvoiceStatus.OVERDUE
    assert invoice.outstanding_amount == Decimal("4108.68")
    assert scenarios[ScenarioType.OVERDUE_INVOICE].expected_facts["days_overdue"] == "8"


def test_west_margin_declines_from_week_2_to_week_3() -> None:
    _, commerce, _, finance, scenarios = _datasets()
    returned_ids = {
        item.order_id
        for item in commerce.orders
        if item.order_id in MARGIN_RETURN_ORDER_IDS and item.order_status == "returned"
    }
    assert returned_ids == MARGIN_RETURN_ORDER_IDS
    snapshots = {
        item.week_start_date: item
        for item in finance.regional_margin_snapshots
        if item.region_id == "reg_aur_west"
    }
    assert snapshots[date(2026, 8, 24)].net_margin_pct < snapshots[date(2026, 8, 17)].net_margin_pct
    assert scenarios[ScenarioType.MARGIN_DECLINE].expected_facts["week_3_refunds"] == "580.17"


def test_purchase_order_is_blocked_pending_cfo_approval() -> None:
    _, _, _, finance, scenarios = _datasets()
    purchase_order = next(
        item
        for item in finance.purchase_orders
        if item.purchase_order_id == APPROVAL_PURCHASE_ORDER_ID
    )
    assert purchase_order.purchase_order_status == PurchaseOrderStatus.PENDING_APPROVAL
    assert not any(
        item.purchase_order_id == APPROVAL_PURCHASE_ORDER_ID
        for item in finance.vendor_invoices
    )
    scenario = scenarios[ScenarioType.PURCHASE_ORDER_APPROVAL]
    assert scenario.approval_required
    assert scenario.expected_facts["submission_allowed"] == "false"
