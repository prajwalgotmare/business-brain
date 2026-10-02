"""Deterministic outbound and inbound logistics generator."""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from business_brain.data.commerce_generator import GENERATED_AT, SNAPSHOT_AT
from business_brain.data.commerce_models import CommerceInventoryDataset, OrderStatus
from business_brain.data.logistics_models import (
    CarrierManifestEntry,
    CarrierSlaFact,
    DeliveryException,
    EventSource,
    ExceptionStatus,
    LogisticsDataset,
    Shipment,
    ShipmentDirection,
    ShipmentItem,
    ShipmentStatus,
    SlaEvaluationBasis,
    SlaStatus,
    TrackingEvent,
    TrackingEventType,
    validate_logistics_against_sources,
)
from business_brain.data.models import Carrier, Product, ReferenceCatalog, Warehouse

LOGISTICS_DATA_SEED = 20261005
DELAY_REASONS = ("carrier_capacity", "sortation_error", "weather", "address_issue")
PENALTY_ELIGIBLE_REASONS = {"carrier_capacity", "sortation_error"}


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _weight(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _prefix(tenant_id: str) -> str:
    return "aur" if tenant_id == "tenant_aura" else "apx"


class _LogisticsBuilder:
    def __init__(self, *, tenant_id: str, rng: random.Random) -> None:
        self.tenant_id = tenant_id
        self.prefix = _prefix(tenant_id)
        self.rng = rng
        self.shipments: list[Shipment] = []
        self.items: list[ShipmentItem] = []
        self.events: list[TrackingEvent] = []
        self.sla_facts: list[CarrierSlaFact] = []
        self.exceptions: list[DeliveryException] = []
        self.manifests: list[CarrierManifestEntry] = []
        self._shipment_sequence = 1
        self._item_sequence = 1
        self._event_sequence = 1
        self._exception_sequence = 1

    def _next_shipment_id(self) -> str:
        value = f"shp_{self.prefix}_{self._shipment_sequence:06d}"
        self._shipment_sequence += 1
        return value

    def _add_event(
        self,
        *,
        shipment_id: str,
        event_time,
        event_type: TrackingEventType,
        location_code: str,
        reason_code: str | None = None,
        event_source: EventSource = EventSource.CARRIER_WEBHOOK,
    ) -> TrackingEvent:
        sequence = self._event_sequence
        event = TrackingEvent(
            tracking_event_id=f"tev_{self.prefix}_{sequence:07d}",
            tenant_id=self.tenant_id,
            shipment_id=shipment_id,
            event_time=event_time,
            event_type=event_type,
            location_code=location_code,
            reason_code=reason_code,
            event_source=event_source,
            raw_event_id=f"raw_{self.prefix}_{sequence:07d}",
        )
        self._event_sequence += 1
        self.events.append(event)
        return event

    def add_shipment(
        self,
        *,
        direction: ShipmentDirection,
        carrier: Carrier,
        items: list[tuple[Product, int]],
        destination_region_id: str,
        shipped_at,
        status: ShipmentStatus,
        is_delayed: bool,
        delay_reason: str | None,
        order_id: str | None = None,
        purchase_order_id: str | None = None,
        origin_warehouse_id: str | None = None,
        destination_warehouse_id: str | None = None,
    ) -> None:
        shipment_id = self._next_shipment_id()
        tracking_number = f"TRK-{self.prefix.upper()}-{self._shipment_sequence - 1:08d}"
        promised_at = shipped_at + timedelta(days=carrier.sla_delivery_days)
        delivered_at = None
        if status == ShipmentStatus.DELIVERED:
            if is_delayed:
                delivered_at = min(
                    promised_at + timedelta(hours=self.rng.randint(8, 60)), SNAPSHOT_AT
                )
            else:
                delivered_at = min(
                    shipped_at + timedelta(hours=carrier.sla_delivery_days * 18), SNAPSHOT_AT
                )
        total_quantity = sum(quantity for _, quantity in items)
        if direction == ShipmentDirection.OUTBOUND:
            charge = _money(Decimal("7.50") + Decimal(total_quantity) * Decimal("1.35"))
        else:
            charge = _money(Decimal("72.00") + Decimal(total_quantity) * Decimal("0.18"))

        shipment = Shipment(
            shipment_id=shipment_id,
            tenant_id=self.tenant_id,
            shipment_direction=direction,
            order_id=order_id,
            purchase_order_id=purchase_order_id,
            carrier_id=carrier.carrier_id,
            origin_warehouse_id=origin_warehouse_id,
            destination_warehouse_id=destination_warehouse_id,
            destination_region_id=destination_region_id,
            tracking_number=tracking_number,
            shipped_at=shipped_at,
            promised_delivery_at=promised_at,
            delivered_at=delivered_at,
            shipment_status=status,
            freight_charge_amount=charge,
            currency_code="USD",
        )
        self.shipments.append(shipment)

        for product, quantity in items:
            received = quantity if status == ShipmentStatus.DELIVERED else 0
            self.items.append(
                ShipmentItem(
                    shipment_item_id=f"sit_{self.prefix}_{self._item_sequence:07d}",
                    tenant_id=self.tenant_id,
                    shipment_id=shipment_id,
                    product_id=product.product_id,
                    expected_quantity=quantity,
                    received_quantity=received,
                )
            )
            self._item_sequence += 1

        location_prefix = f"US-{self.prefix.upper()}"
        self._add_event(
            shipment_id=shipment_id,
            event_time=shipped_at,
            event_type=TrackingEventType.PICKED_UP,
            location_code=f"{location_prefix}-ORIGIN",
        )
        departed_at = min(shipped_at + timedelta(hours=4), SNAPSHOT_AT)
        self._add_event(
            shipment_id=shipment_id,
            event_time=departed_at,
            event_type=TrackingEventType.DEPARTED,
            location_code=f"{location_prefix}-HUB-01",
            event_source=EventSource.BATCH_MANIFEST,
        )

        delay_event = None
        if is_delayed and delay_reason is not None:
            delay_at = min(max(departed_at, promised_at - timedelta(hours=4)), SNAPSHOT_AT)
            delay_event = self._add_event(
                shipment_id=shipment_id,
                event_time=delay_at,
                event_type=TrackingEventType.DELAY,
                location_code=f"{location_prefix}-HUB-02",
                reason_code=delay_reason,
            )

        if delivered_at is not None:
            self._add_event(
                shipment_id=shipment_id,
                event_time=delivered_at,
                event_type=TrackingEventType.DELIVERED,
                location_code=f"{location_prefix}-DEST",
            )
        elif not is_delayed:
            arrived_at = min(departed_at + timedelta(hours=16), SNAPSHOT_AT)
            self._add_event(
                shipment_id=shipment_id,
                event_time=arrived_at,
                event_type=TrackingEventType.ARRIVED,
                location_code=f"{location_prefix}-HUB-02",
            )

        if delivered_at is not None:
            delay_minutes = max(0, int((delivered_at - promised_at).total_seconds() // 60))
            evaluation_basis = SlaEvaluationBasis.DELIVERED
        else:
            delay_minutes = max(0, int((SNAPSHOT_AT - promised_at).total_seconds() // 60))
            evaluation_basis = SlaEvaluationBasis.AS_OF_SNAPSHOT
        if delay_minutes > 0:
            sla_status = SlaStatus.BREACHED
        elif delivered_at is not None:
            sla_status = SlaStatus.ON_TIME
        else:
            sla_status = SlaStatus.PENDING
        penalty_eligible = bool(
            sla_status == SlaStatus.BREACHED and delay_reason in PENALTY_ELIGIBLE_REASONS
        )
        provisional_credit = (
            _money(charge * Decimal("0.10")) if penalty_eligible else Decimal("0.00")
        )
        self.sla_facts.append(
            CarrierSlaFact(
                carrier_sla_fact_id=f"sla_{self.prefix}_{self._shipment_sequence - 1:06d}",
                tenant_id=self.tenant_id,
                shipment_id=shipment_id,
                carrier_id=carrier.carrier_id,
                promised_delivery_at=promised_at,
                actual_delivery_at=delivered_at,
                evaluated_at=SNAPSHOT_AT,
                evaluation_basis=evaluation_basis,
                sla_status=sla_status,
                delay_minutes=delay_minutes,
                penalty_eligible=penalty_eligible,
                provisional_credit_amount=provisional_credit,
                currency_code="USD",
            )
        )

        if delay_event is not None and delay_reason is not None:
            resolved = delivered_at is not None
            self.exceptions.append(
                DeliveryException(
                    delivery_exception_id=(
                        f"dex_{self.prefix}_{self._exception_sequence:06d}"
                    ),
                    tenant_id=self.tenant_id,
                    shipment_id=shipment_id,
                    tracking_event_id=delay_event.tracking_event_id,
                    reason_code=delay_reason,
                    opened_at=delay_event.event_time,
                    resolved_at=delivered_at if resolved else None,
                    exception_status=(
                        ExceptionStatus.RESOLVED if resolved else ExceptionStatus.OPEN
                    ),
                    customer_impact=direction == ShipmentDirection.OUTBOUND,
                )
            )
            self._exception_sequence += 1

        base_charge = _money(charge / Decimal("1.12"))
        fuel_surcharge = charge - base_charge
        self.manifests.append(
            CarrierManifestEntry(
                manifest_entry_id=f"mft_{self.prefix}_{self._shipment_sequence - 1:06d}",
                tenant_id=self.tenant_id,
                shipment_id=shipment_id,
                carrier_id=carrier.carrier_id,
                tracking_number=tracking_number,
                service_level=carrier.service_level,
                reported_weight_kg=_weight(
                    Decimal(total_quantity) * (
                        Decimal("0.65")
                        if direction == ShipmentDirection.OUTBOUND
                        else Decimal("1.80")
                    )
                ),
                base_charge_amount=base_charge,
                fuel_surcharge_amount=fuel_surcharge,
                reported_charge_amount=charge,
                currency_code="USD",
                manifest_date=shipped_at,
                delivery_status=status,
            )
        )


def _outbound_shipments(
    builder: _LogisticsBuilder,
    *,
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
) -> None:
    products = {product.product_id: product for product in catalog.products}
    carriers = [
        carrier for carrier in catalog.carriers if carrier.tenant_id == builder.tenant_id
    ]
    customers = {customer.customer_id: customer for customer in commerce.customers}
    lines_by_order = defaultdict(list)
    for line in commerce.order_lines:
        lines_by_order[line.order_id].append(line)
    shipment_times_by_order = defaultdict(list)
    for movement in commerce.inventory_movements:
        if movement.movement_type == "shipment":
            shipment_times_by_order[movement.reference_id].append(movement.occurred_at)

    eligible_orders = [
        order
        for order in commerce.orders
        if order.tenant_id == builder.tenant_id
        and order.order_status in {OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    ]
    for order in eligible_orders:
        carrier = builder.rng.choice(carriers)
        shipped_at = min(shipment_times_by_order[order.order_id])
        if order.order_status in {OrderStatus.DELIVERED, OrderStatus.RETURNED}:
            status = ShipmentStatus.DELIVERED
        else:
            status = builder.rng.choices(
                [ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED], weights=[72, 28], k=1
            )[0]
        is_delayed = (
            builder.rng.random() < 0.19
            if status == ShipmentStatus.DELIVERED
            else status == ShipmentStatus.DELAYED
        )
        reason = builder.rng.choice(DELAY_REASONS) if is_delayed else None
        builder.add_shipment(
            direction=ShipmentDirection.OUTBOUND,
            carrier=carrier,
            items=[
                (products[line.product_id], line.quantity)
                for line in lines_by_order[order.order_id]
            ],
            destination_region_id=customers[order.customer_id].region_id,
            shipped_at=shipped_at,
            status=status,
            is_delayed=is_delayed,
            delay_reason=reason,
            order_id=order.order_id,
            origin_warehouse_id=order.warehouse_id,
        )


def _inbound_shipments(
    builder: _LogisticsBuilder,
    *,
    catalog: ReferenceCatalog,
    count: int,
) -> None:
    products = [
        product for product in catalog.products if product.tenant_id == builder.tenant_id
    ]
    carriers = [
        carrier for carrier in catalog.carriers if carrier.tenant_id == builder.tenant_id
    ]
    warehouses: list[Warehouse] = [
        warehouse for warehouse in catalog.warehouses if warehouse.tenant_id == builder.tenant_id
    ]
    for sequence in range(1, count + 1):
        warehouse = warehouses[(sequence - 1) % len(warehouses)]
        carrier = builder.rng.choice(carriers)
        shipped_at = SNAPSHOT_AT - timedelta(days=builder.rng.randint(1, 18), hours=12)
        status = builder.rng.choices(
            [ShipmentStatus.DELIVERED, ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELAYED],
            weights=[55, 25, 20],
            k=1,
        )[0]
        is_delayed = status == ShipmentStatus.DELAYED or (
            status == ShipmentStatus.DELIVERED and builder.rng.random() < 0.22
        )
        reason = builder.rng.choice(DELAY_REASONS) if is_delayed else None
        selected_products = builder.rng.sample(
            products, k=min(builder.rng.randint(1, 3), len(products))
        )
        builder.add_shipment(
            direction=ShipmentDirection.INBOUND,
            carrier=carrier,
            items=[(product, builder.rng.randint(60, 180)) for product in selected_products],
            destination_region_id=warehouse.region_id,
            shipped_at=shipped_at,
            status=status,
            is_delayed=is_delayed,
            delay_reason=reason,
            purchase_order_id=f"po_{builder.prefix}_{sequence:05d}",
            destination_warehouse_id=warehouse.warehouse_id,
        )


def build_logistics_dataset(
    catalog: ReferenceCatalog,
    commerce: CommerceInventoryDataset,
) -> LogisticsDataset:
    """Build carrier logs and SLA facts connected to commerce and reference data."""

    builders = (
        _LogisticsBuilder(tenant_id="tenant_aura", rng=random.Random(LOGISTICS_DATA_SEED)),
        _LogisticsBuilder(tenant_id="tenant_apex", rng=random.Random(LOGISTICS_DATA_SEED + 1)),
    )
    for builder in builders:
        _outbound_shipments(builder, catalog=catalog, commerce=commerce)
        _inbound_shipments(
            builder,
            catalog=catalog,
            count=24 if builder.tenant_id == "tenant_aura" else 6,
        )

    dataset = LogisticsDataset(
        generation_seed=LOGISTICS_DATA_SEED,
        generated_at=GENERATED_AT + timedelta(minutes=5),
        snapshot_at=SNAPSHOT_AT,
        shipments=[shipment for builder in builders for shipment in builder.shipments],
        shipment_items=[item for builder in builders for item in builder.items],
        tracking_events=[event for builder in builders for event in builder.events],
        carrier_sla_facts=[fact for builder in builders for fact in builder.sla_facts],
        delivery_exceptions=[
            exception for builder in builders for exception in builder.exceptions
        ],
        carrier_manifest_entries=[
            manifest for builder in builders for manifest in builder.manifests
        ],
    )
    validate_logistics_against_sources(dataset, catalog, commerce)
    return dataset
