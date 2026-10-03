from decimal import Decimal

import pytest
from pydantic import ValidationError

from business_brain.agent.actions import (
    ACTION_PAYLOAD_MODELS,
    ActionDraftArtifact,
    CarrierDisputeDraftPayload,
    DelayAdvisoryDraftPayload,
    PaymentReminderDraftPayload,
    PurchaseOrderDraftPayload,
    get_action_policy,
    validate_action_payload,
)
from business_brain.agent.schemas import RiskLevel, SupervisorIntent
from business_brain.security.context import UserRole


def payloads() -> dict[SupervisorIntent, dict]:
    return {
        SupervisorIntent.DRAFT_PURCHASE_ORDER: {
            "supplier_id": "sup_aur_packaging",
            "warehouse_id": "wh_aur_west",
            "expected_delivery_date": "2026-10-15",
            "currency_code": "USD",
            "lines": [
                {
                    "product_id": "prd_aur_006",
                    "sku": "AUR-SKN-006",
                    "quantity": 300,
                    "unit_cost": "11.37",
                    "line_amount": "3411.00",
                }
            ],
            "subtotal_amount": "3411.00",
            "tax_amount": "0.00",
            "freight_amount": "125.00",
            "total_amount": "3536.00",
            "notes": "Replenishment for West warehouse",
        },
        SupervisorIntent.DRAFT_CARRIER_DISPUTE: {
            "carrier_id": "car_aur_fedex",
            "vendor_invoice_id": "vin_aur_00034",
            "invoice_number": "FRT-AUR-00034",
            "shipment_ids": ["shp_aur_000021"],
            "currency_code": "USD",
            "billed_amount": "40.35",
            "expected_amount": "22.35",
            "sla_credit_amount": "2.24",
            "dispute_amount": "20.24",
            "contract_clause_ids": ["clause_sla_credit_4_2"],
            "statement": "We dispute the overbilling and request the contractual SLA credit.",
        },
        SupervisorIntent.DRAFT_PAYMENT_REMINDER: {
            "supplier_id": "sup_aur_skincare",
            "vendor_invoice_id": "vin_aur_00010",
            "invoice_number": "INV-AUR-00010",
            "due_date": "2026-09-16",
            "outstanding_amount": "7619.40",
            "currency_code": "USD",
            "recipient_name": "Accounts Receivable Team",
            "subject": "Payment settlement reminder for INV-AUR-00010",
            "message": "Please confirm settlement details for the outstanding invoice balance.",
        },
        SupervisorIntent.DRAFT_DELAY_ADVISORY: {
            "order_id": "ord_aur_00012",
            "recipient_name": "Aura Customer",
            "recipient_email": "customer@example.com",
            "carrier_name": "FedEx",
            "tracking_reference": "TRACK-AUR-00012",
            "original_delivery_date": "2026-09-18",
            "estimated_delivery_date": "2026-09-22",
            "subject": "Update about your delayed Aura order",
            "message": "Your order is delayed in transit. We apologize and will keep you updated.",
        },
    }


@pytest.mark.parametrize(
    ("intent", "expected_model"),
    [
        (SupervisorIntent.DRAFT_PURCHASE_ORDER, PurchaseOrderDraftPayload),
        (SupervisorIntent.DRAFT_CARRIER_DISPUTE, CarrierDisputeDraftPayload),
        (SupervisorIntent.DRAFT_PAYMENT_REMINDER, PaymentReminderDraftPayload),
        (SupervisorIntent.DRAFT_DELAY_ADVISORY, DelayAdvisoryDraftPayload),
    ],
)
def test_all_action_payloads_are_strict_and_typed(intent, expected_model) -> None:
    payload = validate_action_payload(intent, payloads()[intent])

    assert isinstance(payload, expected_model)
    assert ACTION_PAYLOAD_MODELS[intent] is expected_model


@pytest.mark.parametrize("intent", list(payloads()))
def test_server_policy_builds_non_submittable_artifacts(intent) -> None:
    policy = get_action_policy(intent)
    artifact = ActionDraftArtifact(
        draft_id="draft_0123456789abcdef",
        tenant_id="tenant_aura",
        action_type=intent,
        risk_level=policy.risk_level,
        required_approver_roles=list(policy.approver_roles),
        payload=validate_action_payload(intent, payloads()[intent]),
    )

    assert artifact.approval_required is True
    assert artifact.submission_allowed is False
    assert artifact.execution_status == "draft"


def test_high_risk_actions_require_founder_cfo_approval() -> None:
    for intent in (
        SupervisorIntent.DRAFT_PURCHASE_ORDER,
        SupervisorIntent.DRAFT_CARRIER_DISPUTE,
    ):
        policy = get_action_policy(intent)
        assert policy.risk_level == RiskLevel.HIGH
        assert policy.approver_roles == (UserRole.FOUNDER_CFO,)


def test_medium_risk_actions_have_operational_approvers() -> None:
    reminder = get_action_policy(SupervisorIntent.DRAFT_PAYMENT_REMINDER)
    advisory = get_action_policy(SupervisorIntent.DRAFT_DELAY_ADVISORY)

    assert reminder.risk_level == RiskLevel.MEDIUM
    assert UserRole.STAFF_ACCOUNTANT in reminder.approver_roles
    assert advisory.risk_level == RiskLevel.MEDIUM
    assert UserRole.LOGISTICS_MANAGER in advisory.approver_roles


def test_purchase_order_rejects_unreconciled_totals_and_extra_fields() -> None:
    invalid_total = payloads()[SupervisorIntent.DRAFT_PURCHASE_ORDER] | {
        "total_amount": "1.00"
    }
    with pytest.raises(ValidationError, match="does not reconcile"):
        PurchaseOrderDraftPayload.model_validate(invalid_total)

    extra = payloads()[SupervisorIntent.DRAFT_PURCHASE_ORDER] | {"approved": True}
    with pytest.raises(ValidationError, match="Extra inputs"):
        PurchaseOrderDraftPayload.model_validate(extra)


def test_dispute_amount_must_equal_overbilling_plus_sla_credit() -> None:
    invalid = payloads()[SupervisorIntent.DRAFT_CARRIER_DISPUTE] | {
        "dispute_amount": Decimal("18.00")
    }

    with pytest.raises(ValidationError, match="does not reconcile"):
        CarrierDisputeDraftPayload.model_validate(invalid)


def test_delay_advisory_rejects_invalid_email_and_date_regression() -> None:
    invalid = payloads()[SupervisorIntent.DRAFT_DELAY_ADVISORY] | {
        "recipient_email": "not-an-email",
        "estimated_delivery_date": "2026-09-10",
    }

    with pytest.raises(ValidationError):
        DelayAdvisoryDraftPayload.model_validate(invalid)


def test_model_cannot_override_server_owned_artifact_fields() -> None:
    injected = payloads()[SupervisorIntent.DRAFT_PAYMENT_REMINDER] | {
        "risk_level": "low",
        "submission_allowed": True,
    }

    with pytest.raises(ValidationError, match="Extra inputs"):
        validate_action_payload(SupervisorIntent.DRAFT_PAYMENT_REMINDER, injected)
