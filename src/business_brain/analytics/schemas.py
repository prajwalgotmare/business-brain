"""Typed result contracts for governed SQL analytics."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class StockoutRisk(BaseModel):
    product_id: str
    sku: str
    warehouse_id: str
    snapshot_at: datetime
    available_quantity: int = Field(ge=0)
    reorder_point: int = Field(ge=0)
    demand_14d: int = Field(ge=0)
    projected_demand_7d: Decimal = Field(ge=0)
    delayed_inbound_quantity: int = Field(ge=0)


class FreightReconciliation(BaseModel):
    shipment_id: str
    vendor_invoice_id: str
    invoice_number: str
    billed_charge: Decimal
    manifest_charge: Decimal
    overbilling_amount: Decimal
    sla_credit: Decimal
    sla_delay_minutes: int = Field(ge=0)
    dispute_amount: Decimal
    currency_code: str


class OverdueInvoice(BaseModel):
    vendor_invoice_id: str
    invoice_number: str
    supplier_id: str
    supplier_name: str
    due_date: date
    days_overdue: int = Field(gt=0)
    outstanding_amount: Decimal = Field(gt=0)
    currency_code: str


class MarginWeek(BaseModel):
    week_start_date: date
    revenue_amount: Decimal
    cost_of_goods_amount: Decimal
    freight_expense_amount: Decimal
    refund_amount: Decimal
    net_profit_amount: Decimal
    net_margin_pct: Decimal


class MarginVariance(BaseModel):
    region_id: str
    earlier: MarginWeek
    later: MarginWeek
    margin_change_percentage_points: Decimal
    revenue_change_amount: Decimal
    refund_change_amount: Decimal
