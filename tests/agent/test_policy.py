import pytest

from business_brain.agent.policy import authorize_decision
from business_brain.agent.schemas import (
    AgentRoute,
    RiskLevel,
    SupervisorDecision,
    SupervisorIntent,
)
from business_brain.security.context import UserRole


def decision(intent: SupervisorIntent, route: AgentRoute) -> SupervisorDecision:
    return SupervisorDecision(
        route=route,
        intent=intent,
        risk_level=RiskLevel.LOW,
        rationale="test",
        confidence=1,
    )


@pytest.mark.parametrize(
    ("intent", "route", "role"),
    [
        (SupervisorIntent.STOCKOUT_RISK, AgentRoute.SQL_ANALYTICS, UserRole.LOGISTICS_MANAGER),
        (
            SupervisorIntent.FREIGHT_RECONCILIATION,
            AgentRoute.SQL_ANALYTICS,
            UserRole.STAFF_ACCOUNTANT,
        ),
        (
            SupervisorIntent.MARGIN_ANALYSIS,
            AgentRoute.SQL_ANALYTICS,
            UserRole.FOUNDER_CFO,
        ),
        (
            SupervisorIntent.DRAFT_DELAY_ADVISORY,
            AgentRoute.ACTION_DRAFTING,
            UserRole.SUPPORT_INTERN,
        ),
    ],
)
def test_allowed_role_intent_combinations(intent, route, role) -> None:
    assert authorize_decision(decision(intent, route), role).allowed is True


def test_sensitive_finance_intent_is_denied_to_support_intern() -> None:
    result = authorize_decision(
        decision(SupervisorIntent.MARGIN_ANALYSIS, AgentRoute.SQL_ANALYTICS),
        UserRole.SUPPORT_INTERN,
    )

    assert result.allowed is False
    assert result.error_code == "policy_denied"


def test_model_cannot_pair_an_intent_with_a_different_route() -> None:
    result = authorize_decision(
        decision(SupervisorIntent.MARGIN_ANALYSIS, AgentRoute.ACTION_DRAFTING),
        UserRole.FOUNDER_CFO,
    )

    assert result.allowed is False
    assert result.error_code == "route_intent_mismatch"
