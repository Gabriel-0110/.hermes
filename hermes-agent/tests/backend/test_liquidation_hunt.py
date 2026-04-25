from __future__ import annotations

from types import SimpleNamespace

from backend.models import LiquidationZonesSnapshot, RecentTradesSnapshot, TradeRecord
from backend.strategies.liquidation_hunt import LiquidationHuntBotRunner, find_liquidation_hunt_proposals


def test_liquidation_hunt_runner_emits_long_proposal(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_liquidation_snapshot",
        lambda symbol: LiquidationZonesSnapshot(
            symbol=f"{symbol}USDT",
            total_longs_liquidated_usd=25_000_000.0,
            dominant_side="longs",
            open_interest_usd=110_000_000.0,
        ),
    )
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_recent_trade_context",
        lambda symbol: RecentTradesSnapshot(
            symbol=f"{symbol}USDT",
            exchange="bitmart_futures",
            trades=[TradeRecord(price=97.5, size=10.0, side="sell", timestamp="2026-04-25T00:00:00+00:00")],
            vwap=100.0,
        ),
    )
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_indicator_snapshot",
        lambda symbol: {"atr": 1.0, "atr_14": 1.0},
    )

    runner = LiquidationHuntBotRunner()
    runner.default_size_usd = 90.0

    proposals = runner.scan(["BTC", "ETH"])

    assert len(proposals) == 2
    proposal = proposals[0]
    assert proposal.symbol == "BTCUSDT"
    assert proposal.side == "buy"
    assert proposal.take_profit_price == 100.0
    assert proposal.stop_loss_price == 96.5
    assert proposal.metadata["liquidation_hunt"] is True


def test_liquidation_hunt_uses_open_interest_proxy_when_needed(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_liquidation_snapshot",
        lambda symbol: LiquidationZonesSnapshot(
            symbol=f"{symbol}USDT",
            dominant_side="longs",
            open_interest_usd=21_500_000.0,
        ),
    )
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_recent_trade_context",
        lambda symbol: RecentTradesSnapshot(
            symbol=f"{symbol}USDT",
            exchange="bitmart_futures",
            trades=[TradeRecord(price=48.0, size=12.0, side="sell", timestamp="2026-04-25T00:00:00+00:00")],
            vwap=50.5,
        ),
    )
    monkeypatch.setattr(
        "backend.strategies.liquidation_hunt._fetch_indicator_snapshot",
        lambda symbol: {"atr": 1.1},
    )

    proposals = find_liquidation_hunt_proposals(
        universe=["SOL"],
        size_usd=80.0,
        source_agent="liquidation_hunt_bot",
        strategy_id="liquidation_hunt/v1.0",
    )

    assert len(proposals) == 1
    assert proposals[0].metadata["liquidation_value_source"] == "open_interest_proxy"