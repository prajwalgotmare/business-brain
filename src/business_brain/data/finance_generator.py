"""Deterministic finance data calibrated to public references."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from business_brain.data.commerce_generator import GENERATED_AT, SNAPSHOT_AT
from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus
from business_brain.data.finance_models import (
    FinanceDataset,
    InvoiceLineType,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    RegionalMarginSnapshot,
    VendorInvoice,
    VendorInvoiceLine,
    validate_finance_against_sources,
)
from business_brain.data.logistics_models import (
    LogisticsDataset,
    ShipmentDirection,
    ShipmentStatus,
)
from business_brain.data.models import Product, ReferenceCatalog, Supplier

FINANCE_DATA_SEED = 20261006
PUBLIC_CALIBRATION = {
    "profile_version": "1.0",
    "profiled_at": "2026-10-03",
    "sources": [
        {
            "name": "UCI Online Retail II",
            "url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii",
            "doi": "10.24432/C5CG6D",
            "license": "CC BY 4.0",
            "use": "commerce quantity, invoice-size, and cancellation plausibility",
            "profile": {
                "sample_rows": 100000,
                "cancellation_line_rate": "0.0213",
                "lines_per_invoice_p50": "15",
                "lines_per_invoice_p75": "28",
                "units_per_line_p50": "3",
                "units_per_line_p75": "10",
                "invoice_value_p25_gbp": "145.00",
                "invoice_value_p50_gbp": "301.00",
                "invoice_value_p75_gbp": "503.93",
                "invoice_value_p90_gbp": "925.67",
            },
            "transformation": (
                "Aggregate statistics only; compact demo row counts and USD catalog prices "
                "are retained, and no source customer or invoice records are copied."
            ),
        },
        {
            "name": "OASIS Universal Business Language 2.3",
            "url": "https://docs.oasis-open.org/ubl/UBL-2.3.html",
            "license": "OASIS specification; freely available",
            "use": "purchase-order, invoice, line, tax, payment-term, and total semantics",
            "transformation": "Mapped relevant concepts into strict Pydantic and CSV contracts.",
        },
        {
            "name": "U.S. Bureau of Labor Statistics Producer Price Index",
            "url": "https://www.bls.gov/ppi/",
            "license": "U.S. government public data",
            "use": "freight-cost terminology and future price-index calibration",
            "transformation": (
                "Current demo charges reconcile to shipment manifests; no BLS index value "
                "is represented as a carrier contract rate."
            ),
        },
    ],
}

CATEGORY_SUPPLIER = {
    "skincare": "sup_aur_skincare",
    "home_care": "sup_aur_home",
    "wellness": "sup_aur_wellness",
    "personal_care": "sup_aur_skincare",
    "travel_accessories": "sup_aur_accessories",
    "general_merchandise": "sup_apx_general",
}
CARRIER_SUPPLIER = {
    "car_aur_fedex_demo": "sup_aur_fedex_demo",
    "car_aur_northstar": "sup_aur_northstar",
    "car_aur_blueline": "sup_aur_blueline",
    "car_apx_summit": "sup_apx_summit",
    "car_apx_rapid": "sup_apx_rapid",
}


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _prefix(tenant_id: str) -> str:
    return "aur" if tenant_id == "tenant_aura" else "apx"


def _purchase_orders(
    catalog: ReferenceCatalog,
    logistics: LogisticsDataset,
) -> tuple[list[PurchaseOrder], list[PurchaseOrderLine]]:
    products = {product.product_id: product for product in catalog.products}
    shipment_items: dict[str, list] = defaultdict(list)
    for item in logistics.shipment_items:
        shipment_items[item.shipment_id].append(item)

    orders: list[PurchaseOrder] = []
    lines: list[PurchaseOrderLine] = []
    for shipment in logistics.shipments:
        if shipment.shipment_direction != ShipmentDirection.INBOUND:
            continue
        items = shipment_items[shipment.shipment_id]
        first_product: Product = products[items[0].product_id]
        supplier_id = CATEGORY_SUPPLIER[first_product.category]
        prefix = _prefix(shipment.tenant_id)
        subtotal = Decimal("0.00")
        for line_sequence, item in enumerate(items, start=1):
            product = products[item.product_id]
            unit_cost = product.standard_cost
            line_amount = _money(unit_cost * item.expected_quantity)
            subtotal += line_amount
            lines.append(
                PurchaseOrderLine(
                    purchase_order_line_id=(
                        f"pol_{prefix}_{shipment.purchase_order_id.split('_')[-1]}_"
                        f"{line_sequence:02d}"
                    ),
                    tenant_id=shipment.tenant_id,
                    purchase_order_id=shipment.purchase_order_id,
                    product_id=item.product_id,
                    quantity=item.expected_quantity,
                    unit_cost=unit_cost,
                    line_amount=line_amount,
                )
            )
        freight = _money(shipment.freight_charge_amount)
        tax = Decimal("0.00")
        status = {
            ShipmentStatus.DELIVERED: PurchaseOrderStatus.RECEIVED,
            ShipmentStatus.IN_TRANSIT: PurchaseOrderStatus.SENT,
            ShipmentStatus.DELAYED: PurchaseOrderStatus.SENT,
        }.get(shipment.shipment_status, PurchaseOrderStatus.APPROVED)
        supplier = next(
            supplier for supplier in catalog.suppliers if supplier.supplier_id == supplier_id
        )
        orders.append(
            PurchaseOrder(
                purchase_order_id=shipment.purchase_order_id,
                tenant_id=shipment.tenant_id,
                supplier_id=supplier_id,
                warehouse_id=shipment.destination_warehouse_id,
                created_at=shipment.shipped_at - timedelta(days=supplier.lead_time_days),
                expected_at=shipment.promised_delivery_at,
                purchase_order_status=status,
                currency_code="USD",
                subtotal_amount=_money(subtotal),
                tax_amount=tax,
                freight_amount=freight,
                total_amount=_money(subtotal + freight + tax),
                approval_required=True,
            )
        )
    return orders, lines


def _invoice_status(total: Decimal, paid: Decimal, due_date) -> InvoiceStatus:
    if paid == total:
        return InvoiceStatus.PAID
    if paid > 0:
        return InvoiceStatus.PARTIALLY_PAID
    if due_date < SNAPSHOT_AT.date():
        return InvoiceStatus.OVERDUE
    return InvoiceStatus.OPEN


def _procurement_invoices(
    catalog: ReferenceCatalog,
    purchase_orders: list[PurchaseOrder],
    purchase_order_lines: list[PurchaseOrderLine],
) -> tuple[list[VendorInvoice], list[VendorInvoiceLine], list[Payment]]:
    supplier_by_id: dict[str, Supplier] = {
        supplier.supplier_id: supplier for supplier in catalog.suppliers
    }
    lines_by_po: dict[str, list[PurchaseOrderLine]] = defaultdict(list)
    for line in purchase_order_lines:
        lines_by_po[line.purchase_order_id].append(line)

    invoices: list[VendorInvoice] = []
    invoice_lines: list[VendorInvoiceLine] = []
    payments: list[Payment] = []
    for sequence, purchase_order in enumerate(purchase_orders, start=1):
        prefix = _prefix(purchase_order.tenant_id)
        invoice_id = f"vin_{prefix}_{sequence:05d}"
        invoice_date = (purchase_order.created_at + timedelta(days=2)).date()
        supplier = supplier_by_id[purchase_order.supplier_id]
        due_date = invoice_date + timedelta(days=supplier.payment_terms_days)
        subtotal = purchase_order.subtotal_amount + purchase_order.freight_amount
        for line_sequence, po_line in enumerate(
            lines_by_po[purchase_order.purchase_order_id], start=1
        ):
            invoice_lines.append(
                VendorInvoiceLine(
                    vendor_invoice_line_id=f"vil_{prefix}_{sequence:05d}_{line_sequence:02d}",
                    tenant_id=purchase_order.tenant_id,
                    vendor_invoice_id=invoice_id,
                    line_type=InvoiceLineType.PRODUCT,
                    description=f"Inventory goods for {po_line.product_id}",
                    quantity=Decimal(po_line.quantity),
                    unit_price=po_line.unit_cost,
                    line_amount=po_line.line_amount,
                )
            )
        invoice_lines.append(
            VendorInvoiceLine(
                vendor_invoice_line_id=f"vil_{prefix}_{sequence:05d}_99",
                tenant_id=purchase_order.tenant_id,
                vendor_invoice_id=invoice_id,
                line_type=InvoiceLineType.OTHER,
                description="Inbound freight charge",
                quantity=Decimal("1.000"),
                unit_price=purchase_order.freight_amount,
                line_amount=purchase_order.freight_amount,
            )
        )

        total = subtotal + purchase_order.tax_amount
        paid = Decimal("0.00")
        if sequence % 5 != 0 and invoice_date + timedelta(days=14) <= SNAPSHOT_AT.date():
            paid = total if sequence % 3 else _money(total * Decimal("0.50"))
            payments.append(
                Payment(
                    payment_id=f"pay_{prefix}_{sequence:05d}",
                    tenant_id=purchase_order.tenant_id,
                    vendor_invoice_id=invoice_id,
                    payment_date=min(invoice_date + timedelta(days=14), SNAPSHOT_AT.date()),
                    payment_amount=paid,
                    currency_code="USD",
                    payment_status=PaymentStatus.COMPLETED,
                )
            )
        invoices.append(
            VendorInvoice(
                vendor_invoice_id=invoice_id,
                tenant_id=purchase_order.tenant_id,
                supplier_id=purchase_order.supplier_id,
                purchase_order_id=purchase_order.purchase_order_id,
                invoice_number=f"INV-{prefix.upper()}-{sequence:05d}",
                invoice_date=invoice_date,
                due_date=due_date,
                invoice_status=_invoice_status(total, paid, due_date),
                currency_code="USD",
                subtotal_amount=subtotal,
                tax_amount=purchase_order.tax_amount,
                total_amount=total,
                outstanding_amount=total - paid,
            )
        )
    return invoices, invoice_lines, payments


def _carrier_invoices(
    logistics: LogisticsDataset,
    starting_sequence: int,
) -> tuple[list[VendorInvoice], list[VendorInvoiceLine]]:
    manifests_by_carrier: dict[tuple[str, str], list] = defaultdict(list)
    for manifest in logistics.carrier_manifest_entries:
        manifests_by_carrier[(manifest.tenant_id, manifest.carrier_id)].append(manifest)

    invoices: list[VendorInvoice] = []
    lines: list[VendorInvoiceLine] = []
    for offset, ((tenant_id, carrier_id), manifests) in enumerate(
        sorted(manifests_by_carrier.items()), start=starting_sequence
    ):
        prefix = _prefix(tenant_id)
        invoice_id = f"vin_{prefix}_{offset:05d}"
        line_sequence = 1
        subtotal = Decimal("0.00")
        for manifest in sorted(manifests, key=lambda item: item.shipment_id):
            for line_type, description, amount in (
                (
                    InvoiceLineType.FREIGHT,
                    "Parcel or freight base charge",
                    manifest.base_charge_amount,
                ),
                (
                    InvoiceLineType.FUEL_SURCHARGE,
                    "Carrier fuel surcharge",
                    manifest.fuel_surcharge_amount,
                ),
            ):
                lines.append(
                    VendorInvoiceLine(
                        vendor_invoice_line_id=f"vil_{prefix}_{offset:05d}_{line_sequence:04d}",
                        tenant_id=tenant_id,
                        vendor_invoice_id=invoice_id,
                        line_type=line_type,
                        description=description,
                        shipment_id=manifest.shipment_id,
                        quantity=Decimal("1.000"),
                        unit_price=amount,
                        line_amount=amount,
                    )
                )
                subtotal += amount
                line_sequence += 1
        subtotal = _money(subtotal)
        invoices.append(
            VendorInvoice(
                vendor_invoice_id=invoice_id,
                tenant_id=tenant_id,
                supplier_id=CARRIER_SUPPLIER[carrier_id],
                invoice_number=f"FRT-{prefix.upper()}-{offset:05d}",
                invoice_date=SNAPSHOT_AT.date(),
                due_date=SNAPSHOT_AT.date() + timedelta(days=30),
                invoice_status=InvoiceStatus.OPEN,
                currency_code="USD",
                subtotal_amount=subtotal,
                tax_amount=Decimal("0.00"),
                total_amount=subtotal,
                outstanding_amount=subtotal,
            )
        )
    return invoices, lines


def _margin_snapshots(
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
) -> list[RegionalMarginSnapshot]:
    customers = {item.customer_id: item for item in commerce.customers}
    lines_by_order: dict[str, list] = defaultdict(list)
    for line in commerce.order_lines:
        lines_by_order[line.order_id].append(line)
    freight_by_order = {
        shipment.order_id: shipment.freight_charge_amount
        for shipment in logistics.shipments
        if shipment.shipment_direction == ShipmentDirection.OUTBOUND
    }
    values: dict[tuple[str, str, object], dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    qualifying = {OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    for order in commerce.orders:
        if order.order_status not in qualifying:
            continue
        region_id = customers[order.customer_id].region_id
        week_start = order.order_timestamp.date() - timedelta(
            days=order.order_timestamp.weekday()
        )
        key = (order.tenant_id, region_id, week_start)
        for line in lines_by_order[order.order_id]:
            values[key]["revenue"] += line.net_amount
            values[key]["cogs"] += line.unit_cost_snapshot * line.quantity
            if order.order_status == OrderStatus.RETURNED:
                values[key]["refund"] += line.net_amount
        values[key]["freight"] += freight_by_order.get(order.order_id, Decimal("0.00"))

    regions = {(item.tenant_id, item.region_id) for item in catalog.regions}
    snapshots: list[RegionalMarginSnapshot] = []
    sequence_by_tenant: dict[str, int] = defaultdict(int)
    for (tenant_id, region_id, week_start), amounts in sorted(values.items()):
        if (tenant_id, region_id) not in regions:
            raise ValueError("unknown margin region")
        sequence_by_tenant[tenant_id] += 1
        revenue = _money(amounts["revenue"])
        cogs = _money(amounts["cogs"])
        freight = _money(amounts["freight"])
        refund = _money(amounts["refund"])
        profit = revenue - cogs - freight - refund
        margin = (
            (profit / revenue).quantize(Decimal("0.0001"))
            if revenue
            else Decimal("0.0000")
        )
        prefix = _prefix(tenant_id)
        snapshots.append(
            RegionalMarginSnapshot(
                margin_snapshot_id=f"mrg_{prefix}_{sequence_by_tenant[tenant_id]:05d}",
                tenant_id=tenant_id,
                region_id=region_id,
                week_start_date=week_start,
                revenue_amount=revenue,
                cost_of_goods_amount=cogs,
                freight_expense_amount=freight,
                refund_amount=refund,
                net_profit_amount=profit,
                net_margin_pct=margin,
                calculated_at=GENERATED_AT + timedelta(minutes=10),
            )
        )
    return snapshots


def build_finance_dataset(
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
) -> FinanceDataset:
    """Build procurement, AP, freight billing, payment, and margin records."""

    purchase_orders, purchase_order_lines = _purchase_orders(catalog, logistics)
    invoices, invoice_lines, payments = _procurement_invoices(
        catalog, purchase_orders, purchase_order_lines
    )
    carrier_invoices, carrier_lines = _carrier_invoices(
        logistics, starting_sequence=len(invoices) + 1
    )
    dataset = FinanceDataset(
        generation_seed=FINANCE_DATA_SEED,
        generated_at=GENERATED_AT + timedelta(minutes=10),
        snapshot_at=SNAPSHOT_AT,
        purchase_orders=purchase_orders,
        purchase_order_lines=purchase_order_lines,
        vendor_invoices=[*invoices, *carrier_invoices],
        vendor_invoice_lines=[*invoice_lines, *carrier_lines],
        payments=payments,
        regional_margin_snapshots=_margin_snapshots(catalog, commerce, logistics),
    )
    validate_finance_against_sources(dataset, catalog, commerce, logistics)
    return dataset
