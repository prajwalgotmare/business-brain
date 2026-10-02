from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_brain.data import ReferenceCatalog, build_reference_catalog


def test_reference_catalog_has_locked_tenant_and_entity_counts() -> None:
    catalog = build_reference_catalog()

    assert {tenant.tenant_id for tenant in catalog.tenants} == {
        "tenant_aura",
        "tenant_apex",
    }
    assert sum(product.tenant_id == "tenant_aura" for product in catalog.products) == 50
    assert sum(product.tenant_id == "tenant_apex" for product in catalog.products) == 8
    assert sum(warehouse.tenant_id == "tenant_aura" for warehouse in catalog.warehouses) == 3
    assert sum(carrier.tenant_id == "tenant_aura" for carrier in catalog.carriers) == 3


def test_reference_catalog_round_trips_through_json_contract() -> None:
    catalog = build_reference_catalog()

    restored = ReferenceCatalog.model_validate_json(catalog.model_dump_json())

    assert restored == catalog
    assert restored.generation_seed == 20261003


def test_product_commercial_rules_are_valid() -> None:
    catalog = build_reference_catalog()

    assert all(product.standard_cost < product.list_price for product in catalog.products)
    assert all(product.safety_stock <= product.reorder_point for product in catalog.products)
    assert all(product.currency_code == "USD" for product in catalog.products)
    assert len({(product.tenant_id, product.sku) for product in catalog.products}) == len(
        catalog.products
    )


def test_cross_tenant_warehouse_region_reference_is_rejected() -> None:
    payload = build_reference_catalog().model_dump(mode="json")
    payload["warehouses"][0]["region_id"] = "reg_apx_east"

    with pytest.raises(ValidationError, match="same tenant"):
        ReferenceCatalog.model_validate(payload)


def test_unknown_tenant_reference_is_rejected() -> None:
    payload = build_reference_catalog().model_dump(mode="json")
    payload["carriers"][0]["tenant_id"] = "tenant_unknown"

    with pytest.raises(ValidationError, match="unknown tenant"):
        ReferenceCatalog.model_validate(payload)


def test_invalid_product_margin_is_rejected() -> None:
    payload = build_reference_catalog().model_dump(mode="json")
    payload["products"][0]["standard_cost"] = Decimal("999.00")

    with pytest.raises(ValidationError, match="standard_cost"):
        ReferenceCatalog.model_validate(payload)
