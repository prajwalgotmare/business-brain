from dataclasses import dataclass

from business_brain.agent.actions import ACTION_POLICIES
from business_brain.agent.schemas import AgentRoute, SupervisorDecision, SupervisorIntent
from business_brain.security.context import UserRole


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    error_code: str | None = None


_ALLOWED_ROLES: dict[SupervisorIntent, frozenset[UserRole]] = {
    SupervisorIntent.STOCKOUT_RISK: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.LOGISTICS_MANAGER}
    ),
    SupervisorIntent.FREIGHT_RECONCILIATION: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    SupervisorIntent.SUPPLIER_TERMS: frozenset({UserRole.FOUNDER_CFO}),
    SupervisorIntent.OVERDUE_INVOICES: frozenset(
        {UserRole.FOUNDER_CFO, UserRole.STAFF_ACCOUNTANT}
    ),
    SupervisorIntent.MARGIN_ANALYSIS: frozenset({UserRole.FOUNDER_CFO}),
    SupervisorIntent.DRAFT_PURCHASE_ORDER: ACTION_POLICIES[
        SupervisorIntent.DRAFT_PURCHASE_ORDER
    ].drafter_roles,
    SupervisorIntent.DRAFT_CARRIER_DISPUTE: ACTION_POLICIES[
        SupervisorIntent.DRAFT_CARRIER_DISPUTE
    ].drafter_roles,
    SupervisorIntent.DRAFT_PAYMENT_REMINDER: ACTION_POLICIES[
        SupervisorIntent.DRAFT_PAYMENT_REMINDER
    ].drafter_roles,
    SupervisorIntent.DRAFT_DELAY_ADVISORY: ACTION_POLICIES[
        SupervisorIntent.DRAFT_DELAY_ADVISORY
    ].drafter_roles,
    SupervisorIntent.GENERAL_DOCUMENT_QUESTION: frozenset(UserRole),
    SupervisorIntent.GENERAL_CONVERSATION: frozenset(UserRole),
    SupervisorIntent.UNSUPPORTED: frozenset(),
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
    if role not in _ALLOWED_ROLES[decision.intent]:
        return PolicyDecision(allowed=False, error_code="policy_denied")
    return PolicyDecision(allowed=True)
