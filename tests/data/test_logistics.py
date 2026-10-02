from collections import defaultdict
from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_brain.data import (
    LogisticsDataset,
    build_commerce_inventory_dataset,
    build_logistics_dataset,
    build_reference_catalog,
)
from business_brain.data.logistics_models import (
    ShipmentDirection,
    ShipmentStatus,
    SlaStatus,
    TrackingEventType,
)


def _dataset() -> LogisticsDataset:
    catalog = build_reference_catalog()
    return build_logistics_dataset(catalog, build_commerce_inventory_dataset(catalog))


def test_logistics_dataset_has_outbound_and_inbound_shipments() -> None:
    dataset = _dataset()

    outbound = [
        shipment
        for shipment in dataset.shipments
        if shipment.shipment_direction == ShipmentDirection.OUTBOUND
    ]
    inbound = [
        shipment
        for shipment in dataset.shipments
        if shipment.shipment_direction == ShipmentDirection.INBOUND
    ]
    assert len(outbound) > 400
    assert len(inbound) == 30
    assert sum(shipment.tenant_id == "tenant_aura" for shipment in inbound) == 24
    assert sum(shipment.tenant_id == "tenant_apex" for shipment in inbound) == 6
    assert len(dataset.carrier_sla_facts) == len(dataset.shipments)
    assert len(dataset.carrier_manifest_entries) == len(dataset.shipments)


def test_delivered_shipments_have_matching_delivery_events() -> None:
    dataset = _dataset()
    events_by_shipment = defaultdict(list)
    for event in dataset.tracking_events:
        events_by_shipment[event.shipment_id].append(event)

    for shipment in dataset.shipments:
        delivered_events = [
            event
            for event in events_by_shipment[shipment.shipment_id]
            if event.event_type == TrackingEventType.DELIVERED
        ]
        if shipment.shipment_status == ShipmentStatus.DELIVERED:
            assert len(delivered_events) == 1
            assert delivered_events[0].event_time == shipment.delivered_at
        else:
            assert delivered_events == []


def test_sla_breaches_and_provisional_credits_reconcile() -> None:
    dataset = _dataset()

    assert any(fact.sla_status == SlaStatus.BREACHED for fact in dataset.carrier_sla_facts)
    assert any(fact.penalty_eligible for fact in dataset.carrier_sla_facts)
    for fact in dataset.carrier_sla_facts:
        if fact.penalty_eligible:
            assert fact.sla_status == SlaStatus.BREACHED
            assert fact.provisional_credit_amount > Decimal("0.00")
        else:
            assert fact.provisional_credit_amount == Decimal("0.00")


def test_manifest_charges_reconcile_to_shipments() -> None:
    dataset = _dataset()
    shipment_by_id = {shipment.shipment_id: shipment for shipment in dataset.shipments}

    for manifest in dataset.carrier_manifest_entries:
        shipment = shipment_by_id[manifest.shipment_id]
        assert manifest.reported_charge_amount == shipment.freight_charge_amount
        assert manifest.reported_charge_amount == (
            manifest.base_charge_amount + manifest.fuel_surcharge_amount
        )


def test_cross_tenant_shipment_item_is_rejected() -> None:
    payload = _dataset().model_dump(mode="json")
    aura_item = next(
        item for item in payload["shipment_items"] if item["tenant_id"] == "tenant_aura"
    )
    apex_shipment = next(
        shipment
        for shipment in payload["shipments"]
        if shipment["tenant_id"] == "tenant_apex"
    )
    aura_item["shipment_id"] = apex_shipment["shipment_id"]

    with pytest.raises(ValidationError, match="same tenant"):
        LogisticsDataset.model_validate(payload)


def test_missing_delivered_event_is_rejected() -> None:
    payload = _dataset().model_dump(mode="json")
    delivered_shipment = next(
        shipment for shipment in payload["shipments"] if shipment["shipment_status"] == "delivered"
    )
    payload["tracking_events"] = [
        event
        for event in payload["tracking_events"]
        if not (
            event["shipment_id"] == delivered_shipment["shipment_id"]
            and event["event_type"] == "delivered"
        )
    ]

    with pytest.raises(ValidationError, match="delivered event"):
        LogisticsDataset.model_validate(payload)
