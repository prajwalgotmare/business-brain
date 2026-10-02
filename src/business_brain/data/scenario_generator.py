"""Build six deterministic, source-linked evaluation scenarios."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus
from business_brain.data.finance_models import FinanceDataset, InvoiceLineType
from business_brain.data.logistics_models import LogisticsDataset, ShipmentStatus
from business_brain.data.models import ReferenceCatalog
from business_brain.data.scenario_constants import (
    APPROVAL_PURCHASE_ORDER_ID,
    MARGIN_RETURN_ORDER_IDS,
    OVERBILLING_SHIPMENT_ID,
    OVERDUE_INVOICE_ID,
    PACKAGING_SUPPLIER_ID,
    STOCKOUT_PRODUCT_ID,
    STOCKOUT_WAREHOUSE_ID,
)
from business_brain.data.scenario_models import (
    DocumentDependency,
    EvidenceReference,
    GroundTruthManifest,
    GroundTruthScenario,
    ScenarioType,
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _evidence(collection: str, record_id: str, purpose: str) -> EvidenceReference:
    return EvidenceReference(
        source_collection=collection,
        record_id=record_id,
        purpose=purpose,
    )


def _stockout_scenario(
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
) -> GroundTruthScenario:
    product = next(item for item in catalog.products if item.product_id == STOCKOUT_PRODUCT_ID)
    balance = next(
        item
        for item in commerce.inventory_balances
        if item.product_id == STOCKOUT_PRODUCT_ID
        and item.warehouse_id == STOCKOUT_WAREHOUSE_ID
    )
    west_customers = {
        item.customer_id for item in commerce.customers if item.region_id == "reg_aur_west"
    }
    recent_orders = {
        item.order_id
        for item in commerce.orders
        if item.customer_id in west_customers
        and item.order_timestamp >= commerce.snapshot_at - timedelta(days=14)
        and item.order_status
        in {OrderStatus.ALLOCATED, OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    }
    demand_14d = sum(
        item.quantity
        for item in commerce.order_lines
        if item.order_id in recent_orders and item.product_id == STOCKOUT_PRODUCT_ID
    )
    delayed_shipments = [
        item
        for item in logistics.shipments
        if item.destination_warehouse_id == STOCKOUT_WAREHOUSE_ID
        and item.shipment_status == ShipmentStatus.DELAYED
    ]
    delayed_ids = {item.shipment_id for item in delayed_shipments}
    delayed_items = [
        item
        for item in logistics.shipment_items
        if item.shipment_id in delayed_ids and item.product_id == STOCKOUT_PRODUCT_ID
    ]
    delayed_inbound = sum(item.expected_quantity for item in delayed_items)
    evidence = [
        _evidence(
            "inventory_balances",
            balance.inventory_balance_id,
            "West available inventory at the snapshot",
        ),
        _evidence("products", product.product_id, "SKU reorder and safety-stock thresholds"),
    ]
    evidence.extend(
        _evidence(
            "shipments",
            item.shipment_id,
            "Delayed inbound replenishment to the West warehouse",
        )
        for item in delayed_shipments
        if any(line.shipment_id == item.shipment_id for line in delayed_items)
    )
    projected_7d = Decimal(demand_14d) / Decimal("2")
    return GroundTruthScenario(
        scenario_id="scn_aur_stockout_001",
        scenario_type=ScenarioType.STOCKOUT_RISK,
        question=(
            "Which high-velocity SKU is at risk of stocking out this week due to "
            "regional carrier delays?"
        ),
        expected_summary=(
            "Aura Night Repair Oil is at risk in the West: two units are available "
            "against 3.5 projected units of seven-day demand while 213 units are delayed."
        ),
        expected_facts={
            "product_id": product.product_id,
            "sku": product.sku,
            "warehouse_id": balance.warehouse_id,
            "available_quantity": str(balance.available_quantity),
            "demand_14d": str(demand_14d),
            "projected_demand_7d": str(projected_7d),
            "reorder_point": str(product.reorder_point),
            "delayed_inbound_quantity": str(delayed_inbound),
        },
        evidence=evidence,
        required_role="logistics_manager",
    )


def _overbilling_scenario(
    logistics: LogisticsDataset,
    finance: FinanceDataset,
) -> GroundTruthScenario:
    manifest = next(
        item
        for item in logistics.carrier_manifest_entries
        if item.shipment_id == OVERBILLING_SHIPMENT_ID
    )
    sla = next(
        item
        for item in logistics.carrier_sla_facts
        if item.shipment_id == OVERBILLING_SHIPMENT_ID
    )
    billed_lines = [
        item
        for item in finance.vendor_invoice_lines
        if item.shipment_id == OVERBILLING_SHIPMENT_ID
        and item.line_type in {InvoiceLineType.FREIGHT, InvoiceLineType.FUEL_SURCHARGE}
    ]
    billed = sum((item.line_amount for item in billed_lines), Decimal("0.00"))
    variance = billed - manifest.reported_charge_amount
    dispute = variance + sla.provisional_credit_amount
    return GroundTruthScenario(
        scenario_id="scn_aur_carrier_overbilling_001",
        scenario_type=ScenarioType.CARRIER_OVERBILLING,
        question=(
            "Reconcile the FedEx freight invoice and calculate the dispute amount "
            "under the SLA."
        ),
        expected_summary=(
            "Shipment shp_aur_000021 is overbilled by $18.00 and earns a $2.24 "
            "late-delivery credit, producing a $20.24 dispute amount."
        ),
        expected_facts={
            "shipment_id": OVERBILLING_SHIPMENT_ID,
            "manifest_charge": str(manifest.reported_charge_amount),
            "billed_charge": str(_money(billed)),
            "overbilling_amount": str(_money(variance)),
            "sla_delay_minutes": str(sla.delay_minutes),
            "sla_credit": str(sla.provisional_credit_amount),
            "dispute_amount": str(_money(dispute)),
        },
        evidence=[
            _evidence("shipments", OVERBILLING_SHIPMENT_ID, "Shipment and carrier identity"),
            _evidence(
                "carrier_manifest_entries",
                manifest.manifest_entry_id,
                "Expected carrier charge",
            ),
            _evidence("carrier_sla_facts", sla.carrier_sla_fact_id, "SLA breach and credit"),
            *[
                _evidence("vendor_invoice_lines", item.vendor_invoice_line_id, "Billed charge")
                for item in billed_lines
            ],
        ],
        document_dependencies=[
            DocumentDependency(
                document_id="doc_aur_fedex_msa",
                clause_id="clause_sla_credit_4_2",
            )
        ],
        required_role="staff_accountant",
        approval_required=True,
    )


def _supplier_terms_scenario(catalog: ReferenceCatalog) -> GroundTruthScenario:
    supplier = next(
        item for item in catalog.suppliers if item.supplier_id == PACKAGING_SUPPLIER_ID
    )
    return GroundTruthScenario(
        scenario_id="scn_aur_supplier_terms_001",
        scenario_type=ScenarioType.SUPPLIER_TERMS,
        question="What are the contracted packaging price tier and payment terms?",
        expected_summary=(
            "Evergreen Packaging Works charges $0.42 per unit for 10,000–24,999 "
            "units, with Net-60 payment terms."
        ),
        expected_facts={
            "supplier_id": supplier.supplier_id,
            "unit_price": "0.42",
            "tier_min_units": "10000",
            "tier_max_units": "24999",
            "payment_terms_days": str(supplier.payment_terms_days),
        },
        evidence=[
            _evidence("suppliers", supplier.supplier_id, "Supplier and structured payment terms")
        ],
        document_dependencies=[
            DocumentDependency(
                document_id="doc_aur_packaging_agreement",
                clause_id="clause_price_tier_3_1",
            ),
            DocumentDependency(
                document_id="doc_aur_packaging_agreement",
                clause_id="clause_payment_terms_5_2",
            ),
        ],
        required_role="founder_cfo",
    )


def _overdue_scenario(
    catalog: ReferenceCatalog,
    finance: FinanceDataset,
) -> GroundTruthScenario:
    invoice = next(
        item for item in finance.vendor_invoices if item.vendor_invoice_id == OVERDUE_INVOICE_ID
    )
    supplier = next(
        item for item in catalog.suppliers if item.supplier_id == invoice.supplier_id
    )
    days_overdue = (finance.snapshot_at.date() - invoice.due_date).days
    penalty = _money(invoice.outstanding_amount * Decimal("0.015"))
    return GroundTruthScenario(
        scenario_id="scn_aur_overdue_invoice_001",
        scenario_type=ScenarioType.OVERDUE_INVOICE,
        question="Which supplier invoice is overdue and what late penalty applies?",
        expected_summary=(
            f"Invoice {invoice.invoice_number} is {days_overdue} days overdue with "
            f"${invoice.outstanding_amount} outstanding; the monthly penalty is ${penalty}."
        ),
        expected_facts={
            "vendor_invoice_id": invoice.vendor_invoice_id,
            "invoice_number": invoice.invoice_number,
            "supplier_id": supplier.supplier_id,
            "due_date": invoice.due_date.isoformat(),
            "days_overdue": str(days_overdue),
            "outstanding_amount": str(invoice.outstanding_amount),
            "late_penalty_rate_monthly": "0.015",
            "late_penalty_amount": str(penalty),
        },
        evidence=[
            _evidence("vendor_invoices", invoice.vendor_invoice_id, "Due date and balance"),
            _evidence("suppliers", supplier.supplier_id, "Supplier payment terms"),
        ],
        document_dependencies=[
            DocumentDependency(
                document_id="doc_aur_skincare_agreement",
                clause_id="clause_late_payment_6_3",
            )
        ],
        required_role="staff_accountant",
    )


def _margin_scenario(finance: FinanceDataset) -> GroundTruthScenario:
    snapshots = {
        item.week_start_date: item
        for item in finance.regional_margin_snapshots
        if item.region_id == "reg_aur_west"
    }
    week_2 = snapshots[date(2026, 8, 17)]
    week_3 = snapshots[date(2026, 8, 24)]
    margin_change_pp = (week_3.net_margin_pct - week_2.net_margin_pct) * Decimal("100")
    return GroundTruthScenario(
        scenario_id="scn_aur_west_margin_001",
        scenario_type=ScenarioType.MARGIN_DECLINE,
        question="Why did West Region net margin decline between Week 2 and Week 3?",
        expected_summary=(
            "West margin fell because revenue declined and three returned orders added "
            "a $580.17 refund burden in Week 3."
        ),
        expected_facts={
            "region_id": "reg_aur_west",
            "week_2_start": week_2.week_start_date.isoformat(),
            "week_3_start": week_3.week_start_date.isoformat(),
            "week_2_margin_pct": str(week_2.net_margin_pct),
            "week_3_margin_pct": str(week_3.net_margin_pct),
            "margin_change_percentage_points": str(margin_change_pp.quantize(Decimal("0.01"))),
            "week_2_revenue": str(week_2.revenue_amount),
            "week_3_revenue": str(week_3.revenue_amount),
            "week_3_refunds": str(week_3.refund_amount),
        },
        evidence=[
            _evidence(
                "regional_margin_snapshots",
                week_2.margin_snapshot_id,
                "Week 2 margin components",
            ),
            _evidence(
                "regional_margin_snapshots",
                week_3.margin_snapshot_id,
                "Week 3 margin components",
            ),
            *[
                _evidence("orders", order_id, "Week 3 returned order")
                for order_id in sorted(MARGIN_RETURN_ORDER_IDS)
            ],
        ],
        required_role="founder_cfo",
    )


def _approval_scenario(finance: FinanceDataset) -> GroundTruthScenario:
    purchase_order = next(
        item
        for item in finance.purchase_orders
        if item.purchase_order_id == APPROVAL_PURCHASE_ORDER_ID
    )
    lines = [
        item
        for item in finance.purchase_order_lines
        if item.purchase_order_id == APPROVAL_PURCHASE_ORDER_ID
    ]
    return GroundTruthScenario(
        scenario_id="scn_aur_po_approval_001",
        scenario_type=ScenarioType.PURCHASE_ORDER_APPROVAL,
        question="Can the replenishment purchase order be submitted now?",
        expected_summary=(
            "No. PO po_aur_approval_00001 is pending Founder/CFO approval and cannot "
            "be submitted externally."
        ),
        expected_facts={
            "purchase_order_id": purchase_order.purchase_order_id,
            "status": purchase_order.purchase_order_status.value,
            "total_amount": str(purchase_order.total_amount),
            "approval_role": "founder_cfo",
            "submission_allowed": "false",
        },
        evidence=[
            _evidence(
                "purchase_orders",
                purchase_order.purchase_order_id,
                "Approval state and order total",
            ),
            *[
                _evidence("purchase_order_lines", item.purchase_order_line_id, "Draft PO line")
                for item in lines
            ],
        ],
        required_role="founder_cfo",
        approval_required=True,
    )


def build_ground_truth_manifest(
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
    finance: FinanceDataset,
) -> GroundTruthManifest:
    """Return the six scenario answer keys linked to canonical source records."""

    return GroundTruthManifest(
        generated_at=finance.generated_at + timedelta(minutes=5),
        snapshot_at=finance.snapshot_at,
        scenarios=[
            _stockout_scenario(catalog, commerce, logistics),
            _overbilling_scenario(logistics, finance),
            _supplier_terms_scenario(catalog),
            _overdue_scenario(catalog, finance),
            _margin_scenario(finance),
            _approval_scenario(finance),
        ],
    )
