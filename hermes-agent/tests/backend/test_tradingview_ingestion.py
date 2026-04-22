from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.tradingview.router import tradingview_router
from backend.tradingview.service import TradingViewIngestionService
from backend.tradingview.store import TradingViewStore
from backend.event_bus.models import TradingEvent


class FakeEventPublisher:
    def __init__(self):
        self.events: list[TradingEvent] = []

    def publish(self, event: TradingEvent):
        self.events.append(event)
        return None


def test_ingestion_service_normalizes_and_publishes_signal_event(tmp_path):
    publisher = FakeEventPublisher()
    service = TradingViewIngestionService(db_path=tmp_path / "state.db", event_publisher=publisher)
    result = service.ingest(
        body=json.dumps(
            {
                "symbol": "BTCUSDT",
                "timeframe": "15",
                "alert_name": "breakout",
                "strategy": "momentum_v1",
                "signal": "entry",
                "direction": "buy",
                "price": 65000,
                "exchange_secret": "should-not-survive",
            }
        ).encode("utf-8"),
        content_type="application/json",
    )

    assert result.alert.symbol == "BTCUSDT"
    assert result.alert.direction == "long"
    assert result.alert.processing_status == "signal_ready"
    assert "exchange_secret" in result.redacted_fields
    assert result.alert.payload["raw_payload"]["exchange_secret"] == "[REDACTED]"
    assert {event.event_type for event in result.internal_events} == {
        "tradingview_alert_received",
        "tradingview_signal_ready",
    }
    assert [event.event_type for event in publisher.events] == [
        "tradingview_alert_received",
        "tradingview_signal_ready",
    ]


def test_ingestion_service_stores_plain_text_raw_payload(tmp_path):
    service = TradingViewIngestionService(db_path=tmp_path / "state.db")
    result = service.ingest(
        body=b"plain text alert payload",
        content_type="text/plain",
    )

    assert result.alert.processing_status == "received"
    assert result.alert.payload["parse_mode"] == "raw_text"
    assert result.alert.payload["raw_payload"] == "plain text alert payload"


def test_tradingview_router_rejects_bad_secret_and_accepts_good_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGVIEW_WEBHOOK_SECRET", "shared-secret")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    app = FastAPI()
    app.include_router(tradingview_router)
    client = TestClient(app)

    bad = client.post("/webhooks/tradingview", headers={"X-TV-Secret": "wrong"}, json={"symbol": "ETHUSDT"})
    assert bad.status_code == 401

    good = client.post(
        "/webhooks/tradingview",
        headers={"X-TV-Secret": "shared-secret"},
        json={"symbol": "ETHUSDT", "signal": "entry", "direction": "sell"},
    )
    assert good.status_code == 200
    payload = good.json()
    assert payload["processing_status"] == "signal_ready"

    store = TradingViewStore(db_path=tmp_path / "state.db")
    alerts = store.list_alerts(limit=5, symbol="ETHUSDT")
    assert len(alerts) == 1
