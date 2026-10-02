"""Validated shipment, tracking, manifest, exception, and SLA contracts."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus
from business_brain.data.models import (
    CurrencyCode,
    Identifier,
    Money,
    ReferenceCatalog,
    Sensitivity,
    ServiceLevel,
    StrictModel,
    TenantEntity,
)

TrackingNumber = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{8,40}$")]


class ShipmentDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class ShipmentStatus(StrEnum):
    LABEL_CREATED = "label_created"
    IN_TRANSIT = "in_transit"
    DELAYED = "delayed"
    DELIVERED = "delivered"
    EXCEPTION = "exception"
    CANCELLED = "cancelled"


class TrackingEventType(StrEnum):
    PICKED_UP = "picked_up"
    DEPARTED = "departed"
    ARRIVED = "arrived"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELAY = "delay"
    EXCEPTION = "exception"


class EventSource(StrEnum):
    CARRIER_WEBHOOK = "carrier_webhook"
    BATCH_MANIFEST = "batch_manifest"


class SlaStatus(StrEnum):
    PENDING = "pending"
    ON_TIME = "on_time"
    BREACHED = "breached"


class SlaEvaluationBasis(StrEnum):
    DELIVERED = "delivered"
    AS_OF_SNAPSHOT = "as_of_snapshot"


class ExceptionStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class Shipment(TenantEntity):
    shipment_id: Identifier
    shipment_direction: ShipmentDirection
    order_id: Identifier | None = None
    purchase_order_id: Identifier | None = None
    carrier_id: Identifier
    origin_warehouse_id: Identifier | None = None
    destination_warehouse_id: Identifier | None = None
    destination_region_id: Identifier
    tracking_number: TrackingNumber
    shipped_at: AwareDatetime
    promised_delivery_at: AwareDatetime
    delivered_at: AwareDatetime | None = None
    shipment_status: ShipmentStatus
    freight_charge_amount: Money
    currency_code: CurrencyCode
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_direction_and_dates(self) -> Shipment:
        if self.promised_delivery_at <= self.shipped_at:
            raise ValueError("promised_delivery_at must be after shipped_at")
        if self.shipment_direction == ShipmentDirection.OUTBOUND:
            if self.order_id is None or self.purchase_order_id is not None:
                raise ValueError("outbound shipment must reference only an order")
            if self.origin_warehouse_id is None or self.destination_warehouse_id is not None:
                raise ValueError("outbound shipment requires only an origin warehouse")
        else:
            if self.purchase_order_id is None or self.order_id is not None:
                raise ValueError("inbound shipment must reference only a purchase order")
            if self.destination_warehouse_id is None or self.origin_warehouse_id is not None:
                raise ValueError("inbound shipment requires only a destination warehouse")
        if self.shipment_status == ShipmentStatus.DELIVERED:
            if self.delivered_at is None:
                raise ValueError("delivered shipment requires delivered_at")
        elif self.delivered_at is not None:
            raise ValueError("undelivered shipment cannot have delivered_at")
        if self.delivered_at is not None and self.delivered_at < self.shipped_at:
            raise ValueError("delivered_at cannot precede shipped_at")
        return self


class ShipmentItem(TenantEntity):
    shipment_item_id: Identifier
    shipment_id: Identifier
    product_id: Identifier
    expected_quantity: Annotated[int, Field(gt=0)]
    received_quantity: Annotated[int, Field(ge=0)]
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_received_quantity(self) -> ShipmentItem:
        if self.received_quantity > self.expected_quantity:
            raise ValueError("received_quantity cannot exceed expected_quantity")
        return self


class TrackingEvent(TenantEntity):
    tracking_event_id: Identifier
    shipment_id: Identifier
    event_time: AwareDatetime
    event_type: TrackingEventType
    location_code: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9-]{3,40}$")]
    reason_code: Identifier | None = None
    event_source: EventSource
    raw_event_id: Identifier
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_reason_code(self) -> TrackingEvent:
        if self.event_type in {TrackingEventType.DELAY, TrackingEventType.EXCEPTION}:
            if self.reason_code is None:
                raise ValueError("delay and exception events require a reason_code")
        elif self.reason_code is not None:
            raise ValueError("reason_code is only allowed for delay or exception events")
        return self


class CarrierSlaFact(TenantEntity):
    carrier_sla_fact_id: Identifier
    shipment_id: Identifier
    carrier_id: Identifier
    promised_delivery_at: AwareDatetime
    actual_delivery_at: AwareDatetime | None = None
    evaluated_at: AwareDatetime
    evaluation_basis: SlaEvaluationBasis
    sla_status: SlaStatus
    delay_minutes: Annotated[int, Field(ge=0)]
    penalty_eligible: bool
    provisional_credit_amount: Money
    currency_code: CurrencyCode
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_sla_result(self) -> CarrierSlaFact:
        breached = self.sla_status == SlaStatus.BREACHED
        if breached != (self.delay_minutes > 0):
            raise ValueError("SLA status and delay_minutes do not agree")
        if not self.penalty_eligible and self.provisional_credit_amount != Decimal("0.00"):
            raise ValueError("ineligible SLA fact cannot carry a provisional credit")
        if self.penalty_eligible and not breached:
            raise ValueError("only breached shipments can be penalty eligible")
        return self


class DeliveryException(TenantEntity):
    delivery_exception_id: Identifier
    shipment_id: Identifier
    tracking_event_id: Identifier
    reason_code: Identifier
    opened_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    exception_status: ExceptionStatus
    customer_impact: bool
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_resolution(self) -> DeliveryException:
        if self.exception_status == ExceptionStatus.RESOLVED:
            if self.resolved_at is None:
                raise ValueError("resolved exception requires resolved_at")
        elif self.resolved_at is not None:
            raise ValueError("open exception cannot have resolved_at")
        if self.resolved_at is not None and self.resolved_at < self.opened_at:
            raise ValueError("resolved_at cannot precede opened_at")
        return self


class CarrierManifestEntry(TenantEntity):
    manifest_entry_id: Identifier
    shipment_id: Identifier
    carrier_id: Identifier
    tracking_number: TrackingNumber
    service_level: ServiceLevel
    reported_weight_kg: Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
    base_charge_amount: Money
    fuel_surcharge_amount: Money
    reported_charge_amount: Money
    currency_code: CurrencyCode
    manifest_date: AwareDatetime
    delivery_status: ShipmentStatus
    sensitivity: Literal[Sensitivity.OPERATIONS] = Sensitivity.OPERATIONS

    @model_validator(mode="after")
    def validate_reported_charge(self) -> CarrierManifestEntry:
        if self.reported_charge_amount != self.base_charge_amount + self.fuel_surcharge_amount:
            raise ValueError("reported charge does not reconcile")
        return self


class LogisticsDataset(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    generation_seed: Annotated[int, Field(ge=0)]
    generated_at: AwareDatetime
    snapshot_at: AwareDatetime
    shipments: list[Shipment]
    shipment_items: list[ShipmentItem]
    tracking_events: list[TrackingEvent]
    carrier_sla_facts: list[CarrierSlaFact]
    delivery_exceptions: list[DeliveryException]
    carrier_manifest_entries: list[CarrierManifestEntry]

    @staticmethod
    def _require_unique(records: list[StrictModel], field: str) -> None:
        keys = [getattr(record, field) for record in records]
        if len(keys) != len(set(keys)):
            raise ValueError(f"duplicate {field}")

    @model_validator(mode="after")
    def validate_internal_relationships(self) -> LogisticsDataset:
        specs = (
            (self.shipments, "shipment_id"),
            (self.shipment_items, "shipment_item_id"),
            (self.tracking_events, "tracking_event_id"),
            (self.carrier_sla_facts, "carrier_sla_fact_id"),
            (self.delivery_exceptions, "delivery_exception_id"),
            (self.carrier_manifest_entries, "manifest_entry_id"),
        )
        for records, field in specs:
            self._require_unique(records, field)

        shipment_by_id = {shipment.shipment_id: shipment for shipment in self.shipments}
        events_by_shipment: dict[str, list[TrackingEvent]] = defaultdict(list)
        event_by_id: dict[str, TrackingEvent] = {}
        items_by_shipment: dict[str, list[ShipmentItem]] = defaultdict(list)

        for item in self.shipment_items:
            shipment = shipment_by_id.get(item.shipment_id)
            if shipment is None or shipment.tenant_id != item.tenant_id:
                raise ValueError("shipment item must reference a shipment in the same tenant")
            items_by_shipment[item.shipment_id].append(item)

        for event in self.tracking_events:
            shipment = shipment_by_id.get(event.shipment_id)
            if shipment is None or shipment.tenant_id != event.tenant_id:
                raise ValueError("tracking event must reference a shipment in the same tenant")
            if event.event_time < shipment.shipped_at or event.event_time > self.snapshot_at:
                raise ValueError("tracking event is outside the permitted shipment window")
            events_by_shipment[event.shipment_id].append(event)
            event_by_id[event.tracking_event_id] = event

        for shipment in self.shipments:
            if not items_by_shipment[shipment.shipment_id]:
                raise ValueError("every shipment requires at least one item")
            events = sorted(
                events_by_shipment[shipment.shipment_id],
                key=lambda event: event.event_time,
            )
            if not events:
                raise ValueError("every shipment requires tracking events")
            delivered_events = [
                event for event in events if event.event_type == TrackingEventType.DELIVERED
            ]
            if shipment.shipment_status == ShipmentStatus.DELIVERED:
                if len(delivered_events) != 1:
                    raise ValueError("delivered shipment requires one delivered event")
                if delivered_events[0].event_time != shipment.delivered_at:
                    raise ValueError("delivered event must match shipment delivered_at")
            elif delivered_events:
                raise ValueError("undelivered shipment cannot have a delivered event")

        sla_by_shipment = {fact.shipment_id: fact for fact in self.carrier_sla_facts}
        manifest_by_shipment = {
            entry.shipment_id: entry for entry in self.carrier_manifest_entries
        }
        if set(sla_by_shipment) != set(shipment_by_id):
            raise ValueError("every shipment requires exactly one SLA fact")
        if set(manifest_by_shipment) != set(shipment_by_id):
            raise ValueError("every shipment requires exactly one manifest entry")

        for shipment_id, shipment in shipment_by_id.items():
            fact = sla_by_shipment[shipment_id]
            manifest = manifest_by_shipment[shipment_id]
            if fact.tenant_id != shipment.tenant_id or fact.carrier_id != shipment.carrier_id:
                raise ValueError("SLA fact must match shipment tenant and carrier")
            if fact.promised_delivery_at != shipment.promised_delivery_at:
                raise ValueError("SLA promise must match shipment promise")
            if fact.actual_delivery_at != shipment.delivered_at:
                raise ValueError("SLA actual delivery must match shipment delivery")
            if manifest.tenant_id != shipment.tenant_id:
                raise ValueError("manifest entry must match shipment tenant")
            if manifest.tracking_number != shipment.tracking_number:
                raise ValueError("manifest tracking number must match shipment")
            if manifest.reported_charge_amount != shipment.freight_charge_amount:
                raise ValueError("manifest charge must match shipment freight charge")

        for exception in self.delivery_exceptions:
            shipment = shipment_by_id.get(exception.shipment_id)
            event = event_by_id.get(exception.tracking_event_id)
            if shipment is None or event is None:
                raise ValueError("delivery exception references unknown shipment or event")
            if shipment.tenant_id != exception.tenant_id or event.tenant_id != exception.tenant_id:
                raise ValueError("delivery exception references must remain in tenant")
            if event.event_type not in {TrackingEventType.DELAY, TrackingEventType.EXCEPTION}:
                raise ValueError("delivery exception must reference a delay or exception event")
            if event.reason_code != exception.reason_code:
                raise ValueError("delivery exception reason must match tracking event")

        if self.generated_at < self.snapshot_at:
            raise ValueError("generated_at cannot precede snapshot_at")
        return self


def validate_logistics_against_sources(
    dataset: LogisticsDataset,
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
) -> None:
    """Validate cross-domain foreign keys, tenant boundaries, and outbound quantities."""

    carrier_by_id = {carrier.carrier_id: carrier for carrier in catalog.carriers}
    region_by_id = {region.region_id: region for region in catalog.regions}
    product_by_id = {product.product_id: product for product in catalog.products}
    warehouse_by_id = {warehouse.warehouse_id: warehouse for warehouse in catalog.warehouses}
    order_by_id = {order.order_id: order for order in commerce.orders}
    customer_by_id = {customer.customer_id: customer for customer in commerce.customers}
    lines_by_order: dict[str, list] = defaultdict(list)
    for line in commerce.order_lines:
        lines_by_order[line.order_id].append(line)

    shipment_by_id = {shipment.shipment_id: shipment for shipment in dataset.shipments}
    items_by_shipment: dict[str, list[ShipmentItem]] = defaultdict(list)
    for item in dataset.shipment_items:
        product = product_by_id.get(item.product_id)
        if product is None or product.tenant_id != item.tenant_id:
            raise ValueError("shipment product must exist in the same tenant")
        items_by_shipment[item.shipment_id].append(item)

    for shipment in dataset.shipments:
        carrier = carrier_by_id.get(shipment.carrier_id)
        region = region_by_id.get(shipment.destination_region_id)
        if carrier is None or carrier.tenant_id != shipment.tenant_id:
            raise ValueError("shipment carrier must exist in the same tenant")
        if region is None or region.tenant_id != shipment.tenant_id:
            raise ValueError("shipment destination region must exist in the same tenant")

        if shipment.shipment_direction == ShipmentDirection.OUTBOUND:
            order = order_by_id.get(shipment.order_id or "")
            if order is None or order.tenant_id != shipment.tenant_id:
                raise ValueError("outbound shipment order must exist in the same tenant")
            if order.order_status not in {
                OrderStatus.SHIPPED,
                OrderStatus.DELIVERED,
                OrderStatus.RETURNED,
            }:
                raise ValueError("outbound shipment cannot reference an unshipped order")
            if order.warehouse_id != shipment.origin_warehouse_id:
                raise ValueError("outbound shipment origin must match order warehouse")
            customer = customer_by_id[order.customer_id]
            if customer.region_id != shipment.destination_region_id:
                raise ValueError("outbound destination must match customer region")
            expected = {
                line.product_id: line.quantity for line in lines_by_order[order.order_id]
            }
            actual = {
                item.product_id: item.expected_quantity
                for item in items_by_shipment[shipment.shipment_id]
            }
            if actual != expected:
                raise ValueError("outbound shipment items must match order lines")
        else:
            warehouse = warehouse_by_id.get(shipment.destination_warehouse_id or "")
            if warehouse is None or warehouse.tenant_id != shipment.tenant_id:
                raise ValueError("inbound destination warehouse must exist in the same tenant")
            if warehouse.region_id != shipment.destination_region_id:
                raise ValueError("inbound warehouse and destination region must match")
            expected_prefix = "po_aur_" if shipment.tenant_id == "tenant_aura" else "po_apx_"
            if not (shipment.purchase_order_id or "").startswith(expected_prefix):
                raise ValueError("inbound purchase-order reference uses an invalid tenant prefix")

    if any(event.event_time > dataset.snapshot_at for event in dataset.tracking_events):
        raise ValueError("tracking event cannot occur after the logistics snapshot")

    for manifest in dataset.carrier_manifest_entries:
        shipment = shipment_by_id[manifest.shipment_id]
        carrier = carrier_by_id[manifest.carrier_id]
        if carrier.service_level != manifest.service_level:
            raise ValueError("manifest service level must match carrier service level")
        if manifest.currency_code != shipment.currency_code:
            raise ValueError("manifest currency must match shipment currency")
