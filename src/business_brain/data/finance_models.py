"""Validated procurement, accounts-payable, and margin contracts."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus
from business_brain.data.logistics_models import LogisticsDataset, ShipmentDirection
from business_brain.data.models import (
    CurrencyCode,
    Identifier,
    Money,
    ReferenceCatalog,
    Sensitivity,
    StrictModel,
    TenantEntity,
)

SignedMoney = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
InvoiceNumber = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{6,40}$")]


class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


class InvoiceStatus(StrEnum):
    OPEN = "open"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    VOID = "void"


class InvoiceLineType(StrEnum):
    PRODUCT = "product"
    FREIGHT = "freight"
    FUEL_SURCHARGE = "fuel_surcharge"
    TAX = "tax"
    CREDIT = "credit"
    OTHER = "other"


class PaymentStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PurchaseOrder(TenantEntity):
    purchase_order_id: Identifier
    supplier_id: Identifier
    warehouse_id: Identifier
    created_at: AwareDatetime
    expected_at: AwareDatetime
    purchase_order_status: PurchaseOrderStatus
    currency_code: CurrencyCode
    subtotal_amount: Money
    tax_amount: Money
    freight_amount: Money
    total_amount: Money
    approval_required: bool
    sensitivity: Literal[Sensitivity.EXECUTIVE] = Sensitivity.EXECUTIVE

    @model_validator(mode="after")
    def validate_order(self) -> PurchaseOrder:
        if self.expected_at <= self.created_at:
            raise ValueError("expected_at must be after created_at")
        if self.total_amount != self.subtotal_amount + self.tax_amount + self.freight_amount:
            raise ValueError("purchase-order total does not reconcile")
        if not self.approval_required:
            raise ValueError("external demo purchase orders require approval")
        return self


class PurchaseOrderLine(TenantEntity):
    purchase_order_line_id: Identifier
    purchase_order_id: Identifier
    product_id: Identifier
    quantity: Annotated[int, Field(gt=0)]
    unit_cost: Money
    line_amount: Money
    sensitivity: Literal[Sensitivity.EXECUTIVE] = Sensitivity.EXECUTIVE

    @model_validator(mode="after")
    def validate_line(self) -> PurchaseOrderLine:
        if self.line_amount != self.unit_cost * self.quantity:
            raise ValueError("purchase-order line does not reconcile")
        return self


class VendorInvoice(TenantEntity):
    vendor_invoice_id: Identifier
    supplier_id: Identifier
    purchase_order_id: Identifier | None = None
    invoice_number: InvoiceNumber
    invoice_date: date
    due_date: date
    invoice_status: InvoiceStatus
    currency_code: CurrencyCode
    subtotal_amount: Money
    tax_amount: Money
    total_amount: Money
    outstanding_amount: Money
    sensitivity: Literal[Sensitivity.ACCOUNTING] = Sensitivity.ACCOUNTING

    @model_validator(mode="after")
    def validate_invoice(self) -> VendorInvoice:
        if self.due_date < self.invoice_date:
            raise ValueError("invoice due date cannot precede invoice date")
        if self.total_amount != self.subtotal_amount + self.tax_amount:
            raise ValueError("invoice total does not reconcile")
        if self.outstanding_amount > self.total_amount:
            raise ValueError("invoice outstanding amount cannot exceed total")
        if self.invoice_status == InvoiceStatus.PAID and self.outstanding_amount != Decimal("0.00"):
            raise ValueError("paid invoice cannot have an outstanding amount")
        return self


class VendorInvoiceLine(TenantEntity):
    vendor_invoice_line_id: Identifier
    vendor_invoice_id: Identifier
    line_type: InvoiceLineType
    description: Annotated[str, StringConstraints(min_length=3, max_length=160)]
    shipment_id: Identifier | None = None
    quantity: Annotated[Decimal, Field(max_digits=12, decimal_places=3)]
    unit_price: SignedMoney
    line_amount: SignedMoney
    sensitivity: Literal[Sensitivity.ACCOUNTING] = Sensitivity.ACCOUNTING

    @model_validator(mode="after")
    def validate_line(self) -> VendorInvoiceLine:
        if self.quantity == 0:
            raise ValueError("invoice-line quantity cannot be zero")
        if self.line_type == InvoiceLineType.CREDIT:
            if self.line_amount >= 0:
                raise ValueError("credit lines must be negative")
        elif self.quantity < 0 or self.unit_price < 0 or self.line_amount < 0:
            raise ValueError("non-credit invoice lines cannot be negative")
        if self.line_amount != self.quantity * self.unit_price:
            raise ValueError("invoice line does not reconcile")
        if self.line_type in {InvoiceLineType.FREIGHT, InvoiceLineType.FUEL_SURCHARGE}:
            if self.shipment_id is None:
                raise ValueError("freight invoice lines require a shipment")
        elif self.shipment_id is not None:
            raise ValueError("only freight lines may reference a shipment")
        return self


class Payment(TenantEntity):
    payment_id: Identifier
    vendor_invoice_id: Identifier
    payment_date: date
    payment_amount: PositiveMoney
    currency_code: CurrencyCode
    payment_status: PaymentStatus
    sensitivity: Literal[Sensitivity.ACCOUNTING] = Sensitivity.ACCOUNTING


class RegionalMarginSnapshot(TenantEntity):
    margin_snapshot_id: Identifier
    region_id: Identifier
    week_start_date: date
    revenue_amount: Money
    cost_of_goods_amount: Money
    freight_expense_amount: Money
    refund_amount: Money
    net_profit_amount: SignedMoney
    net_margin_pct: Annotated[Decimal, Field(max_digits=7, decimal_places=4)]
    calculated_at: AwareDatetime
    sensitivity: Literal[Sensitivity.EXECUTIVE] = Sensitivity.EXECUTIVE

    @model_validator(mode="after")
    def validate_margin(self) -> RegionalMarginSnapshot:
        expected_profit = (
            self.revenue_amount
            - self.cost_of_goods_amount
            - self.freight_expense_amount
            - self.refund_amount
        )
        if self.net_profit_amount != expected_profit:
            raise ValueError("net profit does not reconcile")
        expected_margin = (
            (expected_profit / self.revenue_amount).quantize(Decimal("0.0001"))
            if self.revenue_amount
            else Decimal("0.0000")
        )
        if self.net_margin_pct != expected_margin:
            raise ValueError("net margin does not reconcile")
        return self


class FinanceDataset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generation_seed: Annotated[int, Field(ge=0)]
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    purchase_orders: list[PurchaseOrder]
    purchase_order_lines: list[PurchaseOrderLine]
    vendor_invoices: list[VendorInvoice]
    vendor_invoice_lines: list[VendorInvoiceLine]
    payments: list[Payment]
    regional_margin_snapshots: list[RegionalMarginSnapshot]

    @model_validator(mode="after")
    def validate_internal_relationships(self) -> FinanceDataset:
        specs = (
            (self.purchase_orders, "purchase_order_id"),
            (self.purchase_order_lines, "purchase_order_line_id"),
            (self.vendor_invoices, "vendor_invoice_id"),
            (self.vendor_invoice_lines, "vendor_invoice_line_id"),
            (self.payments, "payment_id"),
            (self.regional_margin_snapshots, "margin_snapshot_id"),
        )
        for records, field in specs:
            values = [getattr(record, field) for record in records]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {field}")

        po_by_id = {record.purchase_order_id: record for record in self.purchase_orders}
        po_lines: dict[str, list[PurchaseOrderLine]] = defaultdict(list)
        for line in self.purchase_order_lines:
            parent = po_by_id.get(line.purchase_order_id)
            if parent is None or parent.tenant_id != line.tenant_id:
                raise ValueError("purchase-order line must remain in tenant")
            po_lines[line.purchase_order_id].append(line)
        for purchase_order in self.purchase_orders:
            line_total = sum(
                (
                    line.line_amount
                    for line in po_lines[purchase_order.purchase_order_id]
                ),
                Decimal(),
            )
            if line_total != purchase_order.subtotal_amount:
                raise ValueError("purchase-order subtotal does not match lines")

        invoice_by_id = {record.vendor_invoice_id: record for record in self.vendor_invoices}
        invoice_lines: dict[str, list[VendorInvoiceLine]] = defaultdict(list)
        completed_payments: dict[str, Decimal] = defaultdict(Decimal)
        for line in self.vendor_invoice_lines:
            parent = invoice_by_id.get(line.vendor_invoice_id)
            if parent is None or parent.tenant_id != line.tenant_id:
                raise ValueError("invoice line must remain in tenant")
            invoice_lines[line.vendor_invoice_id].append(line)
        for payment in self.payments:
            parent = invoice_by_id.get(payment.vendor_invoice_id)
            if parent is None or parent.tenant_id != payment.tenant_id:
                raise ValueError("payment must remain in tenant")
            if payment.payment_date < parent.invoice_date:
                raise ValueError("payment date cannot precede invoice date")
            if payment.currency_code != parent.currency_code:
                raise ValueError("payment currency must match invoice")
            if payment.payment_status == PaymentStatus.COMPLETED:
                completed_payments[payment.vendor_invoice_id] += payment.payment_amount
        for invoice in self.vendor_invoices:
            line_total = sum(
                (line.line_amount for line in invoice_lines[invoice.vendor_invoice_id]),
                Decimal(),
            )
            if line_total != invoice.subtotal_amount:
                raise ValueError("invoice subtotal does not match lines")
            expected_outstanding = (
                invoice.total_amount - completed_payments[invoice.vendor_invoice_id]
            )
            if expected_outstanding != invoice.outstanding_amount:
                raise ValueError("invoice outstanding amount does not match payments")
        return self


def validate_finance_against_sources(
    dataset: FinanceDataset,
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
    logistics: LogisticsDataset,
) -> None:
    suppliers = {item.supplier_id: item for item in catalog.suppliers}
    warehouses = {item.warehouse_id: item for item in catalog.warehouses}
    products = {item.product_id: item for item in catalog.products}
    regions = {item.region_id: item for item in catalog.regions}
    shipments = {item.shipment_id: item for item in logistics.shipments}
    shipment_items: dict[str, list] = defaultdict(list)
    for item in logistics.shipment_items:
        shipment_items[item.shipment_id].append(item)
    inbound = {
        item.purchase_order_id: item
        for item in logistics.shipments
        if item.shipment_direction == ShipmentDirection.INBOUND
    }
    po_by_id = {item.purchase_order_id: item for item in dataset.purchase_orders}
    po_lines: dict[str, list[PurchaseOrderLine]] = defaultdict(list)
    for line in dataset.purchase_order_lines:
        po_lines[line.purchase_order_id].append(line)
    if set(inbound) != set(po_by_id):
        raise ValueError("every inbound shipment must have one purchase order")
    for purchase_order in dataset.purchase_orders:
        supplier = suppliers.get(purchase_order.supplier_id)
        warehouse = warehouses.get(purchase_order.warehouse_id)
        if supplier is None or supplier.tenant_id != purchase_order.tenant_id:
            raise ValueError("purchase-order supplier must remain in tenant")
        if warehouse is None or warehouse.tenant_id != purchase_order.tenant_id:
            raise ValueError("purchase-order warehouse must remain in tenant")
        inbound_warehouse = inbound[
            purchase_order.purchase_order_id
        ].destination_warehouse_id
        if inbound_warehouse != purchase_order.warehouse_id:
            raise ValueError("purchase order and inbound shipment warehouse must match")
        shipment = inbound[purchase_order.purchase_order_id]
        expected_items = {
            item.product_id: item.expected_quantity
            for item in shipment_items[shipment.shipment_id]
        }
        actual_items = {
            line.product_id: line.quantity
            for line in po_lines[purchase_order.purchase_order_id]
        }
        if actual_items != expected_items:
            raise ValueError("purchase-order lines must match inbound shipment items")
    for line in dataset.purchase_order_lines:
        product = products.get(line.product_id)
        if product is None or product.tenant_id != line.tenant_id:
            raise ValueError("purchase-order product must remain in tenant")
    for invoice in dataset.vendor_invoices:
        supplier = suppliers.get(invoice.supplier_id)
        if supplier is None or supplier.tenant_id != invoice.tenant_id:
            raise ValueError("invoice supplier must remain in tenant")
        if invoice.purchase_order_id is not None:
            purchase_order = po_by_id.get(invoice.purchase_order_id)
            if purchase_order is None or purchase_order.tenant_id != invoice.tenant_id:
                raise ValueError("invoice purchase order must remain in tenant")
    for line in dataset.vendor_invoice_lines:
        if line.shipment_id is not None:
            shipment = shipments.get(line.shipment_id)
            if shipment is None or shipment.tenant_id != line.tenant_id:
                raise ValueError("invoice shipment must remain in tenant")
    billed_by_shipment: dict[str, Decimal] = defaultdict(Decimal)
    for line in dataset.vendor_invoice_lines:
        if line.shipment_id is not None:
            billed_by_shipment[line.shipment_id] += line.line_amount
    manifest_charge = {
        item.shipment_id: item.reported_charge_amount
        for item in logistics.carrier_manifest_entries
    }
    if billed_by_shipment != manifest_charge:
        raise ValueError("carrier invoice lines must reconcile to shipment manifests")
    for snapshot in dataset.regional_margin_snapshots:
        region = regions.get(snapshot.region_id)
        if region is None or region.tenant_id != snapshot.tenant_id:
            raise ValueError("margin region must remain in tenant")

    valid_order_ids = {
        order.order_id
        for order in commerce.orders
        if order.order_status in {OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    }
    if not valid_order_ids:
        raise ValueError("margin source requires revenue-eligible orders")
