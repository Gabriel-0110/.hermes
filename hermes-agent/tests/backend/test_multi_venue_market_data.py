from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.event_bus.workers import run_funding_spread_watcher_once
from backend.models import FundingRateEntry, FundingRatesSnapshot, OrderBookLevel, OrderBookSnapshot
from backend.tools.get_funding_rates import get_funding_rates
from backend.tools.get_order_book import get_order_book


class _FundingClient:
    def __init__(self, provider_name: str, funding_rate: float) -> None:
        self.provider = SimpleNamespace(name=provider_name)
        self._funding_rate = funding_rate

    def get_funding_rates(self, symbols: list[str] | None = None, *, limit: int = 20) -> FundingRatesSnapshot:
        resolved_symbol = (symbols or ["BTCUSDT"])[0]
        return FundingRatesSnapshot(
            symbols=[
                FundingRateEntry(
                    symbol=resolved_symbol,
                    exchange=self.provider.name,
                    funding_rate=self._funding_rate,
                    mark_price=100_000.0,
                    index_price=99_950.0,
                )
            ],
            as_of="2026-04-24T00:00:00+00:00",
            source=f"{self.provider.name.lower()}_public",
        )


class _OrderBookClient:
    def __init__(self, provider_name: str, best_bid: float, best_ask: float) -> None:
        self.provider = SimpleNamespace(name=provider_name)
        self._best_bid = best_bid
        self._best_ask = best_ask

    def get_order_book(self, symbol: str, *, limit: int = 20) -> OrderBookSnapshot:
        spread = self._best_ask - self._best_bid
        spread_pct = spread / self._best_bid * 100
        return OrderBookSnapshot(
            symbol=symbol,
            exchange=self.provider.name,
            bids=[OrderBookLevel(price=self._best_bid, amount=1.0)],
            asks=[OrderBookLevel(price=self._best_ask, amount=1.0)],
            best_bid=self._best_bid,
            best_ask=self._best_ask,
            spread=spread,
            spread_pct=spread_pct,
            bid_depth_usd=self._best_bid,
            ask_depth_usd=self._best_ask,
            imbalance=0.0,
            as_of="2026-04-24T00:00:00+00:00",
        )


def test_get_funding_rates_routes_single_requested_venue(monkeypatch):
    monkeypatch.setitem(
        __import__("backend.integrations.derivatives.public_data", fromlist=["_PUBLIC_CLIENT_FACTORIES"])._PUBLIC_CLIENT_FACTORIES,
        "binance",
        lambda: _FundingClient("BINANCE", 0.0004),
    )

    response = get_funding_rates({"symbols": ["BTCUSDT"], "limit": 1, "venue": "binance"})

    assert response["meta"]["ok"] is True
    assert response["meta"]["providers"][0]["provider"] == "BINANCE"
    assert response["data"]["venue"] == "binance"
    assert response["data"]["symbols"][0]["exchange"] == "BINANCE"
    assert response["data"]["symbols"][0]["funding_rate"] == pytest.approx(0.0004)


def test_get_funding_rates_aggregates_spreads_across_venues(monkeypatch):
    registry = __import__("backend.integrations.derivatives.public_data", fromlist=["_PUBLIC_CLIENT_FACTORIES"])._PUBLIC_CLIENT_FACTORIES
    monkeypatch.setitem(registry, "bitmart", lambda: _FundingClient("BITMART_PUBLIC", 0.0001))
    monkeypatch.setitem(registry, "bybit", lambda: _FundingClient("BYBIT", 0.0004))

    response = get_funding_rates({"symbols": ["BTCUSDT"], "limit": 1, "venue": ["bitmart", "bybit"]})

    assert response["meta"]["ok"] is True
    data = response["data"]
    assert data["aggregated"] is True
    assert data["requested_venues"] == ["bitmart", "bybit"]
    assert data["symbols"][0]["symbol"] == "BTCUSDT"
    assert data["symbols"][0]["max_funding_venue"] == "bybit"
    assert data["symbols"][0]["min_funding_venue"] == "bitmart"
    assert data["symbols"][0]["funding_spread_8h"] == pytest.approx(0.0003)


def test_get_order_book_aggregates_best_bid_and_ask_across_venues(monkeypatch):
    registry = __import__("backend.integrations.derivatives.public_data", fromlist=["_PUBLIC_CLIENT_FACTORIES"])._PUBLIC_CLIENT_FACTORIES
    monkeypatch.setitem(registry, "binance", lambda: _OrderBookClient("BINANCE", 100.0, 101.0))
    monkeypatch.setitem(registry, "okx", lambda: _OrderBookClient("OKX", 100.5, 101.5))

    response = get_order_book({"symbol": "BTCUSDT", "limit": 5, "venue": "binance,okx"})

    assert response["meta"]["ok"] is True
    data = response["data"]
    assert data["aggregated"] is True
    assert data["best_bid"] == pytest.approx(100.5)
    assert data["best_bid_exchange"] == "OKX"
    assert data["best_ask"] == pytest.approx(101.0)
    assert data["best_ask_exchange"] == "BINANCE"
    assert len(data["venue_snapshots"]) == 2


def test_funding_spread_watcher_publishes_event_when_threshold_is_exceeded(monkeypatch):
    published: list[object] = []

    monkeypatch.setattr(
        "backend.tools.get_funding_rates.get_funding_rates",
        lambda payload: {
            "meta": {"ok": True},
            "data": {
                "aggregated": True,
                "requested_venues": ["binance", "bybit"],
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "funding_spread_8h": 0.00035,
                        "funding_spread_bps": 3.5,
                        "max_funding_venue": "binance",
                        "max_funding_exchange": "BINANCE",
                        "max_funding_rate": 0.00045,
                        "min_funding_venue": "bybit",
                        "min_funding_exchange": "BYBIT",
                        "min_funding_rate": 0.00010,
                        "venues": [],
                    }
                ],
            },
        },
    )
    monkeypatch.setattr(
        "backend.event_bus.publisher.publish_trading_event",
        lambda event: published.append(event) or SimpleNamespace(event=event, redis_id="1-0", stream="events:trading"),
    )

    result = run_funding_spread_watcher_once(symbols=["BTCUSDT"], venues=["binance", "bybit"], threshold=0.0002)

    assert len(result) == 1
    assert len(published) == 1
    assert published[0].event_type == "funding_spread_detected"
    assert published[0].payload["trade_hint"]["short_perp_venue"] == "binance"
    assert published[0].payload["trade_hint"]["long_perp_venue"] == "bybit"


def test_funding_spread_watcher_skips_subthreshold_spreads(monkeypatch):
    published: list[object] = []

    monkeypatch.setattr(
        "backend.tools.get_funding_rates.get_funding_rates",
        lambda payload: {
            "meta": {"ok": True},
            "data": {
                "aggregated": True,
                "requested_venues": ["binance", "okx"],
                "symbols": [{"symbol": "ETHUSDT", "funding_spread_8h": 0.0001}],
            },
        },
    )
    monkeypatch.setattr(
        "backend.event_bus.publisher.publish_trading_event",
        lambda event: published.append(event) or SimpleNamespace(event=event, redis_id="1-0", stream="events:trading"),
    )

    result = run_funding_spread_watcher_once(symbols=["ETHUSDT"], venues=["binance", "okx"], threshold=0.0002)

    assert result == []
    assert published == []
