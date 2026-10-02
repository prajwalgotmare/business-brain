from collections import defaultdict
from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_brain.data import build_commerce_inventory_dataset, build_reference_catalog
from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus


def _dataset() -> CommerceInventoryDataset:
    return build_commerce_inventory_dataset(build_reference_catalog())


def test_locked_commerce_entity_counts() -> None:
    dataset = _dataset()

    assert len(dataset.customers) == 210
    assert len(dataset.orders) == 580
    assert 1_100 <= len(dataset.order_lines) <= 1_500
    assert len(dataset.inventory_balances) == 166
    assert 1_000 <= len(dataset.inventory_movements) <= 1_600
    assert sum(customer.tenant_id == "tenant_aura" for customer in dataset.customers) == 180
    assert sum(order.tenant_id == "tenant_aura" for order in dataset.orders) == 500


def test_all_order_totals_reconcile() -> None:
    dataset = _dataset()
    lines_by_order = defaultdict(list)
    for line in dataset.order_lines:
        lines_by_order[line.order_id].append(line)

    for order in dataset.orders:
        assert sum(
            (line.net_amount for line in lines_by_order[order.order_id]),
            Decimal("0.00"),
        ) == order.subtotal_amount
        assert order.order_total_amount == (
            order.subtotal_amount
            - order.discount_amount
            + order.tax_amount
            + order.shipping_amount
        )


def test_inventory_balances_reconcile_to_movements_and_allocations() -> None:
    dataset = _dataset()
    movement_totals = defaultdict(int)
    allocated_totals = defaultdict(int)
    order_by_id = {order.order_id: order for order in dataset.orders}

    for movement in dataset.inventory_movements:
        movement_totals[
            (movement.tenant_id, movement.warehouse_id, movement.product_id)
        ] += movement.quantity_delta
    for line in dataset.order_lines:
        order = order_by_id[line.order_id]
        if order.order_status == OrderStatus.ALLOCATED:
            allocated_totals[(line.tenant_id, order.warehouse_id, line.product_id)] += line.quantity

    for balance in dataset.inventory_balances:
        key = (balance.tenant_id, balance.warehouse_id, balance.product_id)
        assert balance.on_hand_quantity == movement_totals[key]
        assert balance.allocated_quantity == allocated_totals[key]
        assert balance.available_quantity == balance.on_hand_quantity - balance.allocated_quantity


def test_customer_data_is_synthetic_and_uses_reserved_domains() -> None:
    dataset = _dataset()

    assert all(customer.email_alias.endswith(".example") for customer in dataset.customers)
    assert all("Customer" in customer.display_name for customer in dataset.customers)


def test_cross_tenant_order_customer_link_is_rejected() -> None:
    payload = _dataset().model_dump(mode="json")
    apex_customer_id = next(
        customer["customer_id"]
        for customer in payload["customers"]
        if customer["tenant_id"] == "tenant_apex"
    )
    aura_order = next(order for order in payload["orders"] if order["tenant_id"] == "tenant_aura")
    aura_order["customer_id"] = apex_customer_id

    with pytest.raises(ValidationError, match="same tenant"):
        CommerceInventoryDataset.model_validate(payload)


def test_unreconciled_inventory_balance_is_rejected() -> None:
    payload = _dataset().model_dump(mode="json")
    payload["inventory_balances"][0]["on_hand_quantity"] += 1
    payload["inventory_balances"][0]["available_quantity"] += 1

    with pytest.raises(ValidationError, match="does not reconcile to movements"):
        CommerceInventoryDataset.model_validate(payload)
