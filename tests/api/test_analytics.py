from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from business_brain.analytics.schemas import StockoutRisk
from business_brain.analytics.service import AnalyticsAccessDeniedError
from business_brain.api.dependencies import get_analytics_service
from business_brain.main import app

HEADERS = {
    "X-Tenant-ID": "tenant_aura",
    "X-User-ID": "demo-logistics",
    "X-Role": "logistics_manager",
}


class StubService:
    def __init__(self, error=None) -> None:
        self.error = error
        self.calls = []

    def stockout_risks(self, auth, *, limit=20):
        self.calls.append((auth, limit))
        if self.error:
            raise self.error
        return [
            StockoutRisk(
                product_id="prd_aur_006",
                sku="AUR-SKN-006",
                warehouse_id="wh_aur_west",
                snapshot_at=datetime(2026, 9, 21, 23, 59, 59, tzinfo=UTC),
                available_quantity=2,
                reorder_point=59,
                demand_14d=7,
                projected_demand_7d=Decimal("3.50"),
                delayed_inbound_quantity=213,
            )
        ]


def test_stockout_endpoint_uses_authenticated_tenant() -> None:
    service = StubService()
    app.dependency_overrides[get_analytics_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/analytics/stockout-risks?limit=5",
                headers=HEADERS,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()[0]["product_id"] == "prd_aur_006"
    assert service.calls[0][0].tenant_id == "tenant_aura"
    assert service.calls[0][1] == 5


def test_forbidden_analytic_returns_sanitized_403() -> None:
    service = StubService(AnalyticsAccessDeniedError("internal role policy detail"))
    app.dependency_overrides[get_analytics_service] = lambda: service
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/analytics/stockout-risks", headers=HEADERS)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "analytics_forbidden"
    assert "internal role policy" not in response.text


def test_invalid_margin_dates_are_rejected_by_service_boundary() -> None:
    class MarginService:
        def margin_variance(self, *args, **kwargs):
            raise ValueError("later week must be after earlier week")

    app.dependency_overrides[get_analytics_service] = lambda: MarginService()
    cfo_headers = HEADERS | {"X-Role": "founder_cfo"}
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                "/api/v1/analytics/margin-variance",
                headers=cfo_headers,
                params={
                    "region_id": "reg_aur_west",
                    "earlier": date(2026, 8, 24).isoformat(),
                    "later": date(2026, 8, 17).isoformat(),
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "analytics_bad_request"
