"""Deterministic commerce and inventory generator."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from business_brain.data.commerce_models import (
    CommerceInventoryDataset,
    Customer,
    CustomerSegment,
    InventoryBalance,
    InventoryMovement,
    MovementType,
    Order,
    OrderLine,
    OrderStatus,
    ReferenceType,
    SalesChannel,
    validate_commerce_against_catalog,
)
from business_brain.data.models import Product, ReferenceCatalog
from business_brain.data.scenario_constants import (
    MARGIN_RETURN_ORDER_IDS,
    STOCKOUT_PRODUCT_ID,
    STOCKOUT_TARGET_ON_HAND,
    STOCKOUT_WAREHOUSE_ID,
)

COMMERCE_DATA_SEED = 20261004
DATA_START = datetime(2026, 8, 10, tzinfo=UTC)
SNAPSHOT_AT = datetime(2026, 9, 21, 23, 59, 59, tzinfo=UTC)
GENERATED_AT = datetime(2026, 9, 22, 0, 5, tzinfo=UTC)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _prefix(tenant_id: str) -> str:
    return "aur" if tenant_id == "tenant_aura" else "apx"


def _build_customers(
    *,
    tenant_id: str,
    count: int,
    region_ids: list[str],
    rng: random.Random,
) -> list[Customer]:
    prefix = _prefix(tenant_id)
    segments = [
        CustomerSegment.CONSUMER,
        CustomerSegment.SMALL_BUSINESS,
        CustomerSegment.WHOLESALE,
    ]
    weights = [76, 18, 6]
    customers: list[Customer] = []
    for sequence in range(1, count + 1):
        customers.append(
            Customer(
                customer_id=f"cus_{prefix}_{sequence:04d}",
                tenant_id=tenant_id,
                customer_segment=rng.choices(segments, weights=weights, k=1)[0],
                region_id=region_ids[(sequence - 1) % len(region_ids)],
                display_name=f"{prefix.upper()} Customer {sequence:04d}",
                email_alias=f"customer{sequence:04d}@{prefix}.example",
            )
        )
    return customers


def _order_status(rng: random.Random) -> OrderStatus:
    statuses = [
        OrderStatus.DELIVERED,
        OrderStatus.SHIPPED,
        OrderStatus.ALLOCATED,
        OrderStatus.PENDING,
        OrderStatus.RETURNED,
        OrderStatus.CANCELLED,
    ]
    return rng.choices(statuses, weights=[68, 12, 6, 5, 5, 4], k=1)[0]


def _build_orders(
    *,
    tenant_id: str,
    count: int,
    customers: list[Customer],
    products: list[Product],
    warehouse_by_region: dict[str, str],
    rng: random.Random,
) -> tuple[list[Order], list[OrderLine]]:
    prefix = _prefix(tenant_id)
    orders: list[Order] = []
    order_lines: list[OrderLine] = []
    line_sequence = 1
    duration_minutes = int((SNAPSHOT_AT - DATA_START).total_seconds() // 60) - 4_320

    for order_sequence in range(1, count + 1):
        customer = rng.choice(customers)
        order_id = f"ord_{prefix}_{order_sequence:05d}"
        order_timestamp = DATA_START + timedelta(minutes=rng.randrange(duration_minutes))
        sales_channel = rng.choices(
            [SalesChannel.WEB, SalesChannel.MARKETPLACE, SalesChannel.WHOLESALE],
            weights=[64, 28, 8],
            k=1,
        )[0]
        line_count = rng.choices([1, 2, 3, 4], weights=[30, 42, 22, 6], k=1)[0]
        selected_products = rng.sample(products, k=line_count)
        current_lines: list[OrderLine] = []
        for product in selected_products:
            quantity = rng.choices([1, 2, 3, 4], weights=[51, 29, 14, 6], k=1)[0]
            line_discount_rate = rng.choices(
                [Decimal("0"), Decimal("0.05"), Decimal("0.10"), Decimal("0.15")],
                weights=[57, 23, 15, 5],
                k=1,
            )[0]
            gross = product.list_price * quantity
            line_discount = _money(gross * line_discount_rate)
            line = OrderLine(
                order_line_id=f"oln_{prefix}_{line_sequence:06d}",
                tenant_id=tenant_id,
                order_id=order_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_price=product.list_price,
                discount_amount=line_discount,
                net_amount=_money(gross - line_discount),
                unit_cost_snapshot=product.standard_cost,
            )
            current_lines.append(line)
            order_lines.append(line)
            line_sequence += 1

        subtotal = sum((line.net_amount for line in current_lines), Decimal("0.00"))
        order_discount_rate = rng.choices(
            [Decimal("0"), Decimal("0.05")], weights=[88, 12], k=1
        )[0]
        order_discount = _money(subtotal * order_discount_rate)
        taxable = subtotal - order_discount
        tax = _money(taxable * Decimal("0.0825"))
        shipping = Decimal("0.00") if taxable >= Decimal("75.00") else Decimal("6.99")
        orders.append(
            Order(
                order_id=order_id,
                tenant_id=tenant_id,
                customer_id=customer.customer_id,
                warehouse_id=warehouse_by_region[customer.region_id],
                order_timestamp=order_timestamp,
                order_status=_order_status(rng),
                sales_channel=sales_channel,
                currency_code="USD",
                subtotal_amount=subtotal,
                discount_amount=order_discount,
                tax_amount=tax,
                shipping_amount=shipping,
                order_total_amount=_money(taxable + tax + shipping),
            )
        )
    return orders, order_lines


def _build_inventory(
    *,
    tenant_id: str,
    products: list[Product],
    warehouse_ids: list[str],
    orders: list[Order],
    order_lines: list[OrderLine],
    rng: random.Random,
) -> tuple[list[InventoryBalance], list[InventoryMovement]]:
    prefix = _prefix(tenant_id)
    movements: list[InventoryMovement] = []
    movement_sequence = 1
    on_hand_by_key: dict[tuple[str, str], int] = {}
    allocated_by_key: dict[tuple[str, str], int] = defaultdict(int)

    for warehouse_index, warehouse_id in enumerate(warehouse_ids, start=1):
        for product_index, product in enumerate(products, start=1):
            opening_quantity = 310 + ((product_index * 17 + warehouse_index * 41) % 230)
            key = (warehouse_id, product.product_id)
            on_hand_by_key[key] = opening_quantity
            movements.append(
                InventoryMovement(
                    inventory_movement_id=f"imv_{prefix}_{movement_sequence:07d}",
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    product_id=product.product_id,
                    occurred_at=DATA_START - timedelta(seconds=1),
                    movement_type=MovementType.ADJUSTMENT,
                    quantity_delta=opening_quantity,
                    reference_type=ReferenceType.ADJUSTMENT,
                    reference_id=f"adj_{prefix}_opening",
                )
            )
            movement_sequence += 1

    order_by_id = {order.order_id: order for order in orders}
    for line in order_lines:
        order = order_by_id[line.order_id]
        key = (order.warehouse_id, line.product_id)
        if order.order_status == OrderStatus.ALLOCATED:
            allocated_by_key[key] += line.quantity
            continue
        if order.order_status not in {
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
            OrderStatus.RETURNED,
        }:
            continue

        ship_time = min(
            order.order_timestamp + timedelta(hours=rng.randint(12, 72)),
            SNAPSHOT_AT,
        )
        on_hand_by_key[key] -= line.quantity
        movements.append(
            InventoryMovement(
                inventory_movement_id=f"imv_{prefix}_{movement_sequence:07d}",
                tenant_id=tenant_id,
                warehouse_id=order.warehouse_id,
                product_id=line.product_id,
                occurred_at=ship_time,
                movement_type=MovementType.SHIPMENT,
                quantity_delta=-line.quantity,
                reference_type=ReferenceType.ORDER,
                reference_id=order.order_id,
            )
        )
        movement_sequence += 1

        if (
            order.order_status == OrderStatus.RETURNED
            and order.order_id not in MARGIN_RETURN_ORDER_IDS
        ):
            return_days = rng.randint(3, 8)
            return_time = min(ship_time + timedelta(days=return_days), SNAPSHOT_AT)
            on_hand_by_key[key] += line.quantity
            movements.append(
                InventoryMovement(
                    inventory_movement_id=f"imv_{prefix}_{movement_sequence:07d}",
                    tenant_id=tenant_id,
                    warehouse_id=order.warehouse_id,
                    product_id=line.product_id,
                    occurred_at=return_time,
                    movement_type=MovementType.RETURN,
                    quantity_delta=line.quantity,
                    reference_type=ReferenceType.ORDER,
                    reference_id=order.order_id,
                )
            )
            movement_sequence += 1

    if tenant_id == "tenant_aura":
        scenario_return_sequence = 1
        for line in order_lines:
            if line.order_id not in MARGIN_RETURN_ORDER_IDS:
                continue
            order = order_by_id[line.order_id]
            key = (order.warehouse_id, line.product_id)
            on_hand_by_key[key] += line.quantity
            movements.append(
                InventoryMovement(
                    inventory_movement_id=(
                        f"imv_aur_scn_margin_{scenario_return_sequence:02d}"
                    ),
                    tenant_id=tenant_id,
                    warehouse_id=order.warehouse_id,
                    product_id=line.product_id,
                    occurred_at=min(
                        order.order_timestamp + timedelta(days=7), SNAPSHOT_AT
                    ),
                    movement_type=MovementType.RETURN,
                    quantity_delta=line.quantity,
                    reference_type=ReferenceType.ORDER,
                    reference_id=order.order_id,
                )
            )
            scenario_return_sequence += 1

    if tenant_id == "tenant_aura":
        scenario_key = (STOCKOUT_WAREHOUSE_ID, STOCKOUT_PRODUCT_ID)
        adjustment = STOCKOUT_TARGET_ON_HAND - on_hand_by_key[scenario_key]
        on_hand_by_key[scenario_key] = STOCKOUT_TARGET_ON_HAND
        movements.append(
            InventoryMovement(
                inventory_movement_id="imv_aur_scn_stockout",
                tenant_id=tenant_id,
                warehouse_id=STOCKOUT_WAREHOUSE_ID,
                product_id=STOCKOUT_PRODUCT_ID,
                occurred_at=SNAPSHOT_AT,
                movement_type=MovementType.ADJUSTMENT,
                quantity_delta=adjustment,
                reference_type=ReferenceType.ADJUSTMENT,
                reference_id="adj_aur_scn_stockout",
            )
        )

    balances: list[InventoryBalance] = []
    balance_sequence = 1
    for warehouse_id in warehouse_ids:
        for product in products:
            key = (warehouse_id, product.product_id)
            on_hand = on_hand_by_key[key]
            allocated = allocated_by_key[key]
            balances.append(
                InventoryBalance(
                    inventory_balance_id=f"ibl_{prefix}_{balance_sequence:05d}",
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    product_id=product.product_id,
                    snapshot_at=SNAPSHOT_AT,
                    on_hand_quantity=on_hand,
                    allocated_quantity=allocated,
                    available_quantity=on_hand - allocated,
                    inbound_quantity=0,
                )
            )
            balance_sequence += 1
    return balances, movements


def build_commerce_inventory_dataset(
    catalog: ReferenceCatalog,
) -> CommerceInventoryDataset:
    """Build deterministic base commerce data without logistics or finance records."""

    customers: list[Customer] = []
    orders: list[Order] = []
    order_lines: list[OrderLine] = []
    balances: list[InventoryBalance] = []
    movements: list[InventoryMovement] = []

    tenant_settings = (
        ("tenant_aura", 180, 500, COMMERCE_DATA_SEED),
        ("tenant_apex", 30, 80, COMMERCE_DATA_SEED + 1),
    )
    for tenant_id, customer_count, order_count, seed in tenant_settings:
        rng = random.Random(seed)
        tenant_regions = [
            region.region_id for region in catalog.regions if region.tenant_id == tenant_id
        ]
        tenant_products = [
            product for product in catalog.products if product.tenant_id == tenant_id
        ]
        tenant_warehouses = [
            warehouse for warehouse in catalog.warehouses if warehouse.tenant_id == tenant_id
        ]
        warehouse_by_region = {
            warehouse.region_id: warehouse.warehouse_id for warehouse in tenant_warehouses
        }

        tenant_customers = _build_customers(
            tenant_id=tenant_id,
            count=customer_count,
            region_ids=tenant_regions,
            rng=rng,
        )
        tenant_orders, tenant_lines = _build_orders(
            tenant_id=tenant_id,
            count=order_count,
            customers=tenant_customers,
            products=tenant_products,
            warehouse_by_region=warehouse_by_region,
            rng=rng,
        )
        if tenant_id == "tenant_aura":
            for order in tenant_orders:
                if order.order_id in MARGIN_RETURN_ORDER_IDS:
                    order.order_status = OrderStatus.RETURNED
        tenant_balances, tenant_movements = _build_inventory(
            tenant_id=tenant_id,
            products=tenant_products,
            warehouse_ids=[warehouse.warehouse_id for warehouse in tenant_warehouses],
            orders=tenant_orders,
            order_lines=tenant_lines,
            rng=rng,
        )
        customers.extend(tenant_customers)
        orders.extend(tenant_orders)
        order_lines.extend(tenant_lines)
        balances.extend(tenant_balances)
        movements.extend(tenant_movements)

    dataset = CommerceInventoryDataset(
        generation_seed=COMMERCE_DATA_SEED,
        generated_at=GENERATED_AT,
        snapshot_at=SNAPSHOT_AT,
        customers=customers,
        orders=orders,
        order_lines=order_lines,
        inventory_balances=balances,
        inventory_movements=movements,
    )
    validate_commerce_against_catalog(dataset, catalog)
    return dataset
