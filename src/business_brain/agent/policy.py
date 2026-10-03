from dataclasses import dataclass

from business_brain.agent.schemas import AgentRoute, SupervisorDecision, SupervisorIntent
from business_brain.security.context import UserRole
from business_brain.security.policy import Capability, role_has_capability


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    error_code: str | None = None


_INTENT_CAPABILITIES: dict[SupervisorIntent, Capability | None] = {
    SupervisorIntent.STOCKOUT_RISK: Capability.ANALYTICS_STOCKOUT,
    SupervisorIntent.FREIGHT_RECONCILIATION: Capability.ANALYTICS_FREIGHT,
    SupervisorIntent.SUPPLIER_TERMS: Capability.DOCUMENT_SUPPLIER_TERMS,
    SupervisorIntent.OVERDUE_INVOICES: Capability.ANALYTICS_OVERDUE_INVOICES,
    SupervisorIntent.MARGIN_ANALYSIS: Capability.ANALYTICS_MARGIN,
    SupervisorIntent.DRAFT_PURCHASE_ORDER: Capability.DRAFT_PURCHASE_ORDER,
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: Capability.DRAFT_CARRIER_DISPUTE,
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: Capability.DRAFT_PAYMENT_REMINDER,
    SupervisorIntent.DRAFT_DELAY_ADVISORY: Capability.DRAFT_DELAY_ADVISORY,
    SupervisorIntent.GENERAL_DOCUMENT_QUESTION: Capability.DOCUMENT_SEARCH,
    SupervisorIntent.GENERAL_CONVERSATION: Capability.BASIC_ASSISTANT,
    SupervisorIntent.UNSUPPORTED: None,
}

_EXPECTED_ROUTES: dict[SupervisorIntent, AgentRoute] = {
    SupervisorIntent.STOCKOUT_RISK: AgentRoute.SQL_ANALYTICS,
    SupervisorIntent.FREIGHT_RECONCILIATION: AgentRoute.SQL_ANALYTICS,
    SupervisorIntent.SUPPLIER_TERMS: AgentRoute.DOCUMENT_RETRIEVAL,
    SupervisorIntent.OVERDUE_INVOICES: AgentRoute.SQL_ANALYTICS,
    SupervisorIntent.MARGIN_ANALYSIS: AgentRoute.SQL_ANALYTICS,
    SupervisorIntent.DRAFT_PURCHASE_ORDER: AgentRoute.ACTION_DRAFTING,
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: AgentRoute.ACTION_DRAFTING,
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: AgentRoute.ACTION_DRAFTING,
    SupervisorIntent.DRAFT_DELAY_ADVISORY: AgentRoute.ACTION_DRAFTING,
    SupervisorIntent.GENERAL_DOCUMENT_QUESTION: AgentRoute.DOCUMENT_RETRIEVAL,
    SupervisorIntent.GENERAL_CONVERSATION: AgentRoute.DIRECT_RESPONSE,
    SupervisorIntent.UNSUPPORTED: AgentRoute.REFUSE,
}


def authorize_decision(decision: SupervisorDecision, role: UserRole) -> PolicyDecision:
    """Validate the model's proposed route against immutable application policy."""
    if decision.route != _EXPECTED_ROUTES[decision.intent]:
        return PolicyDecision(allowed=False, error_code="route_intent_mismatch")
    capability = _INTENT_CAPABILITIES[decision.intent]
    if capability is None or not role_has_capability(role, capability):
        return PolicyDecision(allowed=False, error_code="policy_denied")
    return PolicyDecision(allowed=True)
