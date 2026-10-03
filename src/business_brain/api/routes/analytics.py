from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from business_brain.analytics.schemas import (
    FreightReconciliation,
    MarginVariance,
    OverdueInvoice,
    StockoutRisk,
)
from business_brain.analytics.service import (
    AnalyticsAccessDeniedError,
    GovernedAnalyticsService,
)
from business_brain.api.dependencies import get_analytics_service, get_auth_context
from business_brain.api.errors import (
    AnalyticsBadRequestError,
    AnalyticsForbiddenError,
    AnalyticsServiceUnavailableError,
)
from business_brain.security.context import AuthContext

router = APIRouter(tags=["analytics"])

Identifier = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_]+$", min_length=3, max_length=80)]


def _analytics_call(operation):
    try:
        return operation()
    except AnalyticsAccessDeniedError as exc:
        raise AnalyticsForbiddenError("This role cannot access the requested analytic") from exc
    except AnalyticsForbiddenError:
        raise
    except ValueError as exc:
        raise AnalyticsBadRequestError("Invalid analytics parameters") from exc
    except Exception as exc:
        raise AnalyticsServiceUnavailableError(
            "Business analytics are temporarily unavailable"
        ) from exc


@router.get("/stockout-risks", response_model=list[StockoutRisk])
def stockout_risks(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[GovernedAnalyticsService, Depends(get_analytics_service)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return _analytics_call(lambda: service.stockout_risks(auth, limit=limit))


@router.get(
    "/freight-reconciliation/{shipment_id}",
    response_model=FreightReconciliation | None,
)
def freight_reconciliation(
    shipment_id: Identifier,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[GovernedAnalyticsService, Depends(get_analytics_service)],
):
    return _analytics_call(lambda: service.freight_reconciliation(auth, shipment_id))


@router.get("/overdue-invoices", response_model=list[OverdueInvoice])
def overdue_invoices(
    as_of: Annotated[date, Query()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[GovernedAnalyticsService, Depends(get_analytics_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return _analytics_call(lambda: service.overdue_invoices(auth, as_of=as_of, limit=limit))


@router.get("/margin-variance", response_model=MarginVariance | None)
def margin_variance(
    region_id: Annotated[str, Query(pattern=r"^[a-z][a-z0-9_]+$")],
    earlier: Annotated[date, Query()],
    later: Annotated[date, Query()],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    service: Annotated[GovernedAnalyticsService, Depends(get_analytics_service)],
):
    return _analytics_call(
        lambda: service.margin_variance(
            auth,
            region_id=region_id,
            earlier=earlier,
            later=later,
        )
    )
