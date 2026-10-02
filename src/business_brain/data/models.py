"""Strict canonical schemas for fixed enterprise reference data."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]+$")]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
CountryCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]
Sku = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]+$")]
Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2, ge=0)]


class RecordStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    SUPPORT = "support"
    OPERATIONS = "operations"
    ACCOUNTING = "accounting"
    EXECUTIVE = "executive"


class ServiceLevel(StrEnum):
    STANDARD = "standard"
    EXPEDITED = "expedited"
    SAME_DAY = "same_day"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("must be a valid IANA timezone") from exc
    return value


class Tenant(StrictModel):
    tenant_id: Identifier
    tenant_name: Annotated[str, StringConstraints(min_length=2, max_length=100)]
    default_currency_code: CurrencyCode
    timezone: str
    record_status: RecordStatus = RecordStatus.ACTIVE

    _timezone_is_valid = field_validator("timezone")(_validate_timezone)


class TenantEntity(StrictModel):
    tenant_id: Identifier


class Region(TenantEntity):
    region_id: Identifier
    region_name: Annotated[str, StringConstraints(min_length=2, max_length=80)]
    country_code: CountryCode
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS


class Product(TenantEntity):
    product_id: Identifier
    sku: Sku
    product_name: Annotated[str, StringConstraints(min_length=3, max_length=120)]
    category: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]+$")]
    unit_of_measure: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]{2,3}$")]
    list_price: Money
    standard_cost: Money
    currency_code: CurrencyCode
    reorder_point: Annotated[int, Field(ge=0)]
    safety_stock: Annotated[int, Field(ge=0)]
    record_status: RecordStatus = RecordStatus.ACTIVE
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_commercial_values(self) -> Product:
        if self.standard_cost >= self.list_price:
            raise ValueError("standard_cost must be below list_price")
        if self.safety_stock > self.reorder_point:
            raise ValueError("safety_stock must not exceed reorder_point")
        return self


class Warehouse(TenantEntity):
    warehouse_id: Identifier
    region_id: Identifier
    warehouse_name: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    country_code: CountryCode
    timezone: str
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    _timezone_is_valid = field_validator("timezone")(_validate_timezone)


class Supplier(TenantEntity):
    supplier_id: Identifier
    supplier_name: Annotated[str, StringConstraints(min_length=3, max_length=120)]
    payment_terms_days: Literal[30, 45, 60]
    lead_time_days: Annotated[int, Field(gt=0, le=180)]
    currency_code: CurrencyCode
    record_status: RecordStatus = RecordStatus.ACTIVE
    sensitivity: Literal[Sensitivity.ACCOUNTING] = Sensitivity.ACCOUNTING


class Carrier(TenantEntity):
    carrier_id: Identifier
    carrier_name: Annotated[str, StringConstraints(min_length=3, max_length=120)]
    service_level: ServiceLevel
    sla_delivery_days: Annotated[int, Field(gt=0, le=30)]
    record_status: RecordStatus = RecordStatus.ACTIVE
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS


class ReferenceCatalog(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generation_seed: Annotated[int, Field(ge=0)]
    tenants: list[Tenant]
    regions: list[Region]
    products: list[Product]
    warehouses: list[Warehouse]
    suppliers: list[Supplier]
    carriers: list[Carrier]

    @staticmethod
    def _require_unique(records: list[StrictModel], field: str) -> None:
        keys = [getattr(record, field) for record in records]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {field}")

    @model_validator(mode="after")
    def validate_catalog_integrity(self) -> ReferenceCatalog:
        entity_specs = (
            (self.tenants, "tenant_id"),
            (self.regions, "region_id"),
            (self.products, "product_id"),
            (self.warehouses, "warehouse_id"),
            (self.suppliers, "supplier_id"),
            (self.carriers, "carrier_id"),
        )
        for records, field in entity_specs:
            self._require_unique(records, field)

        tenant_by_id = {tenant.tenant_id: tenant for tenant in self.tenants}
        for records, _ in entity_specs[1:]:
            unknown_tenants = {record.tenant_id for record in records} - tenant_by_id.keys()
            if unknown_tenants:
                raise ValueError(f"unknown tenant references: {sorted(unknown_tenants)}")

        region_by_id = {region.region_id: region for region in self.regions}
        for warehouse in self.warehouses:
            region = region_by_id.get(warehouse.region_id)
            if region is None:
                raise ValueError(f"unknown region_id: {warehouse.region_id}")
            if region.tenant_id != warehouse.tenant_id:
                raise ValueError("warehouse and region must belong to the same tenant")
            if region.country_code != warehouse.country_code:
                raise ValueError("warehouse and region country codes must match")

        sku_keys = [(product.tenant_id, product.sku) for product in self.products]
        if len(sku_keys) != len(set(sku_keys)):
            raise ValueError("duplicate SKU within tenant")

        currency_by_tenant = {
            tenant.tenant_id: tenant.default_currency_code for tenant in self.tenants
        }
        monetary_records = [*self.products, *self.suppliers]
        for record in monetary_records:
            if record.currency_code != currency_by_tenant[record.tenant_id]:
                raise ValueError("reference currency must match tenant default currency")

        return self
