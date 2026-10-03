from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from business_brain.agent.schemas import RiskLevel, SupervisorIntent
from business_brain.data.finance_models import InvoiceNumber, PositiveMoney
from business_brain.data.models import CurrencyCode, Identifier, Money, Sku, StrictModel
from business_brain.security.context import UserRole

ShortText = Annotated[str, StringConstraints(min_length=3, max_length=160)]
MessageText = Annotated[str, StringConstraints(min_length=20, max_length=4_000)]
EmailAddress = Annotated[
    str,
    StringConstraints(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254),
]


class PurchaseOrderLineDraft(StrictModel):
    product_id: Identifier
    sku: Sku
    quantity: Annotated[int, Field(gt=0, le=100_000)]
    unit_cost: Money
    line_amount: Money

    @model_validator(mode="after")
    def reconcile_line(self) -> PurchaseOrderLineDraft:
        if self.line_amount != self.unit_cost * self.quantity:
            raise ValueError("purchase-order line amount does not reconcile")
        return self


class PurchaseOrderDraftPayload(StrictModel):
    supplier_id: Identifier
    warehouse_id: Identifier
    expected_delivery_date: date
    currency_code: CurrencyCode
    lines: Annotated[list[PurchaseOrderLineDraft], Field(min_length=1, max_length=50)]
    subtotal_amount: Money
    tax_amount: Money
    freight_amount: Money
    total_amount: Money
    notes: ShortText | None = None

    @model_validator(mode="after")
    def reconcile_totals(self) -> PurchaseOrderDraftPayload:
        if self.subtotal_amount != sum((line.line_amount for line in self.lines), Decimal(0)):
            raise ValueError("purchase-order subtotal does not reconcile")
        expected = self.subtotal_amount + self.tax_amount + self.freight_amount
        if self.total_amount != expected:
            raise ValueError("purchase-order total does not reconcile")
        return self


class CarrierDisputeDraftPayload(StrictModel):
    carrier_id: Identifier
    vendor_invoice_id: Identifier
    invoice_number: InvoiceNumber
    shipment_ids: Annotated[list[Identifier], Field(min_length=1, max_length=100)]
    currency_code: CurrencyCode
    billed_amount: Money
    expected_amount: Money
    sla_credit_amount: Money
    dispute_amount: PositiveMoney
    contract_clause_ids: Annotated[list[Identifier], Field(min_length=1, max_length=20)]
    statement: MessageText

    @model_validator(mode="after")
    def reconcile_dispute(self) -> CarrierDisputeDraftPayload:
        expected = self.billed_amount - self.expected_amount + self.sla_credit_amount
        if expected <= 0 or self.dispute_amount != expected:
            raise ValueError("carrier dispute amount does not reconcile")
        if len(self.shipment_ids) != len(set(self.shipment_ids)):
            raise ValueError("shipment_ids must be unique")
        return self


class PaymentReminderDraftPayload(StrictModel):
    supplier_id: Identifier
    vendor_invoice_id: Identifier
    invoice_number: InvoiceNumber
    due_date: date
    outstanding_amount: PositiveMoney
    currency_code: CurrencyCode
    recipient_name: ShortText
    subject: ShortText
    message: MessageText


class DelayAdvisoryDraftPayload(StrictModel):
    order_id: Identifier
    recipient_name: ShortText
    recipient_email: EmailAddress
    carrier_name: ShortText
    tracking_reference: Annotated[str, StringConstraints(min_length=3, max_length=100)]
    original_delivery_date: date
    estimated_delivery_date: date
    subject: ShortText
    message: MessageText

    @model_validator(mode="after")
    def validate_dates(self) -> DelayAdvisoryDraftPayload:
        if self.estimated_delivery_date < self.original_delivery_date:
            raise ValueError("estimated delivery cannot precede original delivery")
        return self


ActionPayload = (
    PurchaseOrderDraftPayload
    | CarrierDisputeDraftPayload
    | PaymentReminderDraftPayload
    | DelayAdvisoryDraftPayload
)


class ActionDraftArtifact(StrictModel):
    draft_id: Identifier
    tenant_id: Identifier
    action_type: SupervisorIntent
    risk_level: RiskLevel
    required_approver_roles: Annotated[list[UserRole], Field(min_length=1)]
    approval_required: Literal[True] = True
    submission_allowed: Literal[False] = False
    execution_status: Literal["draft"] = "draft"
    payload: ActionPayload

    @model_validator(mode="after")
    def payload_matches_action(self) -> ActionDraftArtifact:
        expected = ACTION_PAYLOAD_MODELS.get(self.action_type)
        if expected is None or not isinstance(self.payload, expected):
            raise ValueError("action payload does not match action_type")
        policy = get_action_policy(self.action_type)
        if self.risk_level != policy.risk_level:
            raise ValueError("risk_level does not match server policy")
        if tuple(self.required_approver_roles) != policy.approver_roles:
            raise ValueError("required approver roles do not match server policy")
        return self


ACTION_PAYLOAD_MODELS: dict[SupervisorIntent, type[StrictModel]] = {
    SupervisorIntent.DRAFT_PURCHASE_ORDER: PurchaseOrderDraftPayload,
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: CarrierDisputeDraftPayload,
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: PaymentReminderDraftPayload,
    SupervisorIntent.DRAFT_DELAY_ADVISORY: DelayAdvisoryDraftPayload,
}


@dataclass(frozen=True)
class ActionPolicy:
    risk_level: RiskLevel
    drafter_roles: frozenset[UserRole]
    approver_roles: tuple[UserRole, ...]


ACTION_POLICIES: dict[SupervisorIntent, ActionPolicy] = {
    SupervisorIntent.DRAFT_PURCHASE_ORDER: ActionPolicy(
        risk_level=RiskLevel.HIGH,
        drafter_roles=frozenset({UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER}),
        approver_roles=(UserRole.FOUNDER_CFO,),
    ),
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: ActionPolicy(
        risk_level=RiskLevel.HIGH,
        drafter_roles=frozenset({UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}),
        approver_roles=(UserRole.FOUNDER_CFO,),
    ),
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: ActionPolicy(
        risk_level=RiskLevel.MEDIUM,
        drafter_roles=frozenset({UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}),
        approver_roles=(UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT),
    ),
    SupervisorIntent.DRAFT_DELAY_ADVISORY: ActionPolicy(
        risk_level=RiskLevel.MEDIUM,
        drafter_roles=frozenset(
            {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER, UserRole.SUPPORT_INTERN}
        ),
        approver_roles=(UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER),
    ),
}


def get_action_policy(intent: SupervisorIntent) -> ActionPolicy:
    try:
        return ACTION_POLICIES[intent]
    except KeyError as exc:
        raise ValueError("intent is not a supported action") from exc


def validate_action_payload(intent: SupervisorIntent, value: object) -> ActionPayload:
    try:
        model = ACTION_PAYLOAD_MODELS[intent]
    except KeyError as exc:
        raise ValueError("intent is not a supported action") from exc
    return model.model_validate(value)
