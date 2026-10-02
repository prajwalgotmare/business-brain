"""Validated commerce and inventory transaction contracts."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator, model_validator

from business_brain.data.models import (
    CurrencyCode,
    Identifier,
    Money,
    ReferenceCatalog,
    Sensitivity,
    StrictModel,
    TenantEntity,
)

SyntheticEmail = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z0-9._-]+@[a-z0-9-]+\.example$"),
]


class CustomerSegment(StrEnum):
    CONSUMER = "consumer"
    SMALL_BUSINESS = "small_business"
    WHOLESALE = "wholesale"


class OrderStatus(StrEnum):
    PENDING = "pending"
    ALLOCATED = "allocated"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    RETURNED = "returned"


class SalesChannel(StrEnum):
    WEB = "web"
    MARKETPLACE = "marketplace"
    WHOLESALE = "wholesale"


class MovementType(StrEnum):
    RECEIPT = "receipt"
    ALLOCATION = "allocation"
    SHIPMENT = "shipment"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


class ReferenceType(StrEnum):
    ORDER = "order"
    PURCHASE_ORDER = "purchase_order"
    RETURN = "return"
    ADJUSTMENT = "adjustment"


class Customer(TenantEntity):
    customer_id: Identifier
    customer_segment: CustomerSegment
    region_id: Identifier
    display_name: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    email_alias: SyntheticEmail
    sensitivity: Literal[Sensitivity.SUPPORT] = Sensitivity.SUPPORT


class Order(TenantEntity):
    order_id: Identifier
    customer_id: Identifier
    warehouse_id: Identifier
    order_timestamp: AwareDatetime
    order_status: OrderStatus
    sales_channel: SalesChannel
    currency_code: CurrencyCode
    subtotal_amount: Money
    discount_amount: Money
    tax_amount: Money
    shipping_amount: Money
    order_total_amount: Money
    sensitivity: Literal[Sensitivity.SUPPORT] = Sensitivity.SUPPORT

    @model_validator(mode="after")
    def validate_total(self) -> Order:
        if self.discount_amount > self.subtotal_amount:
            raise ValueError("discount_amount cannot exceed subtotal_amount")
        expected = (
            self.subtotal_amount
            - self.discount_amount
            + self.tax_amount
            + self.shipping_amount
        )
        if self.order_total_amount != expected:
            raise ValueError("order_total_amount does not reconcile")
        return self


class OrderLine(TenantEntity):
    order_line_id: Identifier
    order_id: Identifier
    product_id: Identifier
    quantity: Annotated[int, Field(gt=0)]
    unit_price: Money
    discount_amount: Money
    net_amount: Money
    unit_cost_snapshot: Money
    sensitivity: Literal[Sensitivity.SUPPORT] = Sensitivity.SUPPORT

    @model_validator(mode="after")
    def validate_net_amount(self) -> OrderLine:
        gross = self.unit_price * self.quantity
        if self.discount_amount > gross:
            raise ValueError("line discount cannot exceed gross amount")
        if self.net_amount != gross - self.discount_amount:
            raise ValueError("net_amount does not reconcile")
        return self


class InventoryBalance(TenantEntity):
    inventory_balance_id: Identifier
    warehouse_id: Identifier
    product_id: Identifier
    snapshot_at: AwareDatetime
    on_hand_quantity: Annotated[int, Field(ge=0)]
    allocated_quantity: Annotated[int, Field(ge=0)]
    available_quantity: Annotated[int, Field(ge=0)]
    inbound_quantity: Annotated[int, Field(ge=0)]
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_available_quantity(self) -> InventoryBalance:
        if self.allocated_quantity > self.on_hand_quantity:
            raise ValueError("allocated_quantity cannot exceed on_hand_quantity")
        if self.available_quantity != self.on_hand_quantity - self.allocated_quantity:
            raise ValueError("available_quantity does not reconcile")
        return self


class InventoryMovement(TenantEntity):
    inventory_movement_id: Identifier
    warehouse_id: Identifier
    product_id: Identifier
    occurred_at: AwareDatetime
    movement_type: MovementType
    quantity_delta: int
    reference_type: ReferenceType
    reference_id: Identifier
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @field_validator("quantity_delta")
    @classmethod
    def quantity_delta_cannot_be_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("quantity_delta cannot be zero")
        return value


class CommerceInventoryDataset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generation_seed: Annotated[int, Field(ge=0)]
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    customers: list[Customer]
    orders: list[Order]
    order_lines: list[OrderLine]
    inventory_balances: list[InventoryBalance]
    inventory_movements: list[InventoryMovement]

    @staticmethod
    def _require_unique(records: list[StrictModel], field: str) -> None:
        keys = [getattr(record, field) for record in records]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {field}")

    @model_validator(mode="after")
    def validate_internal_relationships(self) -> CommerceInventoryDataset:
        specs = (
            (self.customers, "customer_id"),
            (self.orders, "order_id"),
            (self.order_lines, "order_line_id"),
            (self.inventory_balances, "inventory_balance_id"),
            (self.inventory_movements, "inventory_movement_id"),
        )
        for records, field in specs:
            self._require_unique(records, field)

        customer_by_id = {customer.customer_id: customer for customer in self.customers}
        order_by_id = {order.order_id: order for order in self.orders}
        lines_by_order: dict[str, list[OrderLine]] = defaultdict(list)
        for order in self.orders:
            customer = customer_by_id.get(order.customer_id)
            if customer is None:
                raise ValueError(f"unknown customer_id: {order.customer_id}")
            if customer.tenant_id != order.tenant_id:
                raise ValueError("order and customer must belong to the same tenant")

        for line in self.order_lines:
            order = order_by_id.get(line.order_id)
            if order is None:
                raise ValueError(f"unknown order_id: {line.order_id}")
            if order.tenant_id != line.tenant_id:
                raise ValueError("order line and order must belong to the same tenant")
            lines_by_order[line.order_id].append(line)

        for order in self.orders:
            lines = lines_by_order.get(order.order_id, [])
            if not lines:
                raise ValueError(f"order has no lines: {order.order_id}")
            if sum((line.net_amount for line in lines), Decimal("0.00")) != order.subtotal_amount:
                raise ValueError(f"order subtotal does not match lines: {order.order_id}")

        balance_keys = [
            (balance.tenant_id, balance.warehouse_id, balance.product_id, balance.snapshot_at)
            for balance in self.inventory_balances
        ]
        if len(balance_keys) != len(set(balance_keys)):
            raise ValueError("duplicate inventory balance snapshot")

        allocated_by_key: dict[tuple[str, str, str], int] = defaultdict(int)
        for line in self.order_lines:
            order = order_by_id[line.order_id]
            if order.order_status == OrderStatus.ALLOCATED:
                key = (line.tenant_id, order.warehouse_id, line.product_id)
                allocated_by_key[key] += line.quantity

        movement_total_by_key: dict[tuple[str, str, str], int] = defaultdict(int)
        for movement in self.inventory_movements:
            movement_total_by_key[
                (movement.tenant_id, movement.warehouse_id, movement.product_id)
            ] += movement.quantity_delta
            if movement.reference_type == ReferenceType.ORDER:
                order = order_by_id.get(movement.reference_id)
                if order is None or order.tenant_id != movement.tenant_id:
                    raise ValueError("order movement must reference an order in the same tenant")

        for balance in self.inventory_balances:
            key = (balance.tenant_id, balance.warehouse_id, balance.product_id)
            if movement_total_by_key[key] != balance.on_hand_quantity:
                raise ValueError("inventory balance does not reconcile to movements")
            if allocated_by_key[key] != balance.allocated_quantity:
                raise ValueError("allocated inventory does not reconcile to allocated orders")

        if self.generated_at < self.snapshot_at:
            raise ValueError("generated_at cannot precede snapshot_at")
        return self


def validate_commerce_against_catalog(
    dataset: CommerceInventoryDataset,
    catalog: ReferenceCatalog,
) -> None:
    """Validate external references and tenant boundaries against the master catalog."""

    region_by_id = {region.region_id: region for region in catalog.regions}
    product_by_id = {product.product_id: product for product in catalog.products}
    warehouse_by_id = {warehouse.warehouse_id: warehouse for warehouse in catalog.warehouses}
    currency_by_tenant = {
        tenant.tenant_id: tenant.default_currency_code for tenant in catalog.tenants
    }

    for customer in dataset.customers:
        region = region_by_id.get(customer.region_id)
        if region is None or region.tenant_id != customer.tenant_id:
            raise ValueError("customer region must exist in the same tenant")

    order_by_id = {order.order_id: order for order in dataset.orders}
    for order in dataset.orders:
        warehouse = warehouse_by_id.get(order.warehouse_id)
        if warehouse is None or warehouse.tenant_id != order.tenant_id:
            raise ValueError("order warehouse must exist in the same tenant")
        if order.currency_code != currency_by_tenant[order.tenant_id]:
            raise ValueError("order currency must match tenant default")

    for line in dataset.order_lines:
        product = product_by_id.get(line.product_id)
        order = order_by_id[line.order_id]
        if product is None or product.tenant_id != line.tenant_id:
            raise ValueError("order-line product must exist in the same tenant")
        if product.currency_code != order.currency_code:
            raise ValueError("order-line product currency must match order currency")

    inventory_records = [*dataset.inventory_balances, *dataset.inventory_movements]
    for record in inventory_records:
        product = product_by_id.get(record.product_id)
        warehouse = warehouse_by_id.get(record.warehouse_id)
        if product is None or product.tenant_id != record.tenant_id:
            raise ValueError("inventory product must exist in the same tenant")
        if warehouse is None or warehouse.tenant_id != record.tenant_id:
            raise ValueError("inventory warehouse must exist in the same tenant")

    if any(timestamp > dataset.snapshot_at for timestamp in _event_timestamps(dataset)):
        raise ValueError("commerce events cannot occur after the dataset snapshot")


def _event_timestamps(dataset: CommerceInventoryDataset) -> list[datetime]:
    return [
        *(order.order_timestamp for order in dataset.orders),
        *(movement.occurred_at for movement in dataset.inventory_movements),
    ]
