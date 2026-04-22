from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from hermes_api.core.config import get_settings
from hermes_api.core.security import require_api_key
from hermes_api.main import app as hermes_app


def _build_test_client() -> TestClient:
    app = FastAPI()

    @app.post("/protected")
    async def protected(_: None = Depends(require_api_key)) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_protected_route_fails_closed_when_no_key_and_no_bypass(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("HERMES_API_DEV_BYPASS_AUTH", raising=False)
    get_settings.cache_clear()

    client = _build_test_client()
    response = client.post("/protected")

    assert response.status_code == 503
    assert "Operator authentication is not configured" in response.json()["detail"]


def test_protected_route_allows_explicit_dev_bypass(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_API_DEV_BYPASS_AUTH", "true")
    get_settings.cache_clear()

    client = _build_test_client()
    response = client.post("/protected")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_production_ignores_dev_bypass_without_api_key(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_API_DEV_BYPASS_AUTH", "true")
    get_settings.cache_clear()

    client = _build_test_client()
    response = client.post("/protected")

    assert response.status_code == 503


def test_protected_route_requires_matching_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HERMES_API_KEY", "super-secret-token")
    monkeypatch.delenv("HERMES_API_DEV_BYPASS_AUTH", raising=False)
    get_settings.cache_clear()

    client = _build_test_client()

    unauthorized = client.post("/protected")
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/protected",
        headers={"Authorization": "Bearer super-secret-token"},
    )
    assert authorized.status_code == 200
    assert authorized.json() == {"ok": True}


def test_mutating_product_routes_fail_closed_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    monkeypatch.delenv("HERMES_API_DEV_BYPASS_AUTH", raising=False)
    get_settings.cache_clear()

    client = TestClient(hermes_app)

    responses = [
        client.post(
            "/api/v1/risk/kill-switch/activate",
            json={"reason": "test", "operator": "tester"},
        ),
        client.post("/api/v1/portfolio/sync"),
        client.post(
            "/api/v1/execution/approvals/test-approval/approve",
            json={"operator": "tester"},
        ),
    ]

    for response in responses:
        assert response.status_code == 503
        assert "Operator authentication is not configured" in response.json()["detail"]


def test_mutating_product_routes_require_bearer_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HERMES_API_KEY", "super-secret-token")
    monkeypatch.delenv("HERMES_API_DEV_BYPASS_AUTH", raising=False)
    get_settings.cache_clear()

    client = TestClient(hermes_app)

    responses = [
        client.post(
            "/api/v1/risk/kill-switch/activate",
            json={"reason": "test", "operator": "tester"},
        ),
        client.post("/api/v1/portfolio/sync"),
        client.post(
            "/api/v1/execution/approvals/test-approval/approve",
            json={"operator": "tester"},
        ),
    ]

    for response in responses:
        assert response.status_code == 401
        assert "Invalid or missing API key" in response.json()["detail"]


def test_execution_place_requires_explicit_live_unlock(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HERMES_API_KEY", "super-secret-token")
    monkeypatch.setenv("HERMES_TRADING_MODE", "live")
    monkeypatch.setenv("HERMES_ENABLE_LIVE_TRADING", "false")
    monkeypatch.delenv("HERMES_API_DEV_BYPASS_AUTH", raising=False)
    get_settings.cache_clear()

    client = TestClient(hermes_app)
    response = client.post(
        "/api/v1/execution/place",
        json={"symbol": "BTC/USDT", "side": "buy", "order_type": "market", "amount": 0.01},
        headers={"Authorization": "Bearer super-secret-token"},
    )

    assert response.status_code == 403
    detail = response.json()["detail"]
    assert detail["message"] == "Live execution is blocked."
    assert any("HERMES_ENABLE_LIVE_TRADING=true" in item for item in detail["blockers"])
