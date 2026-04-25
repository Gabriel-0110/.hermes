"""Liquidation-hunt mean-reversion strategy.

Looks for liquidation-style downside flushes in BTC/ETH/SOL and buys sharp
dislocations once price stretches materially below short-horizon VWAP.

BitMart public data does not expose a full force-orders feed, so this strategy
prefers explicit ``total_longs_liquidated_usd`` values when they are present
and otherwise falls back to a conservative open-interest proxy when the
dominant side is clearly long.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from backend.models import LiquidationZonesSnapshot, RecentTradesSnapshot
from backend.trading.bot_runner import StrategyBotRunner
from backend.trading.models import TradeProposal

logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS = ("BTC", "ETH", "SOL")
LIQUIDATION_THRESHOLD_USD = 20_000_000.0
VWAP_DEVIATION_ATR = 2.0


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_universe(universe: Iterable[str] | None) -> list[str]:
    requested = {
        str(symbol or "").upper().replace("/USDT", "").replace("USDT", "").strip()
        for symbol in (universe or SUPPORTED_SYMBOLS)
    }
    return [symbol for symbol in SUPPORTED_SYMBOLS if symbol in requested]


def _fetch_liquidation_snapshot(base_symbol: str) -> LiquidationZonesSnapshot:
    from backend.tools.get_liquidation_zones import get_liquidation_zones

    response = get_liquidation_zones({"symbol": f"{base_symbol}USDT", "limit": 25})
    data = response.get("data") or {}
    return LiquidationZonesSnapshot.model_validate(data)


def _fetch_recent_trade_context(base_symbol: str) -> RecentTradesSnapshot:
    from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient

    client = BitMartPublicClient()
    return client.get_recent_trades(f"{base_symbol}USDT", limit=100)


def _fetch_indicator_snapshot(base_symbol: str) -> dict[str, Any]:
    from backend.tools.get_indicator_snapshot import get_indicator_snapshot

    response = get_indicator_snapshot({"symbol": base_symbol, "interval": "1h"})
    return response.get("data") or {}


def _last_trade_price(snapshot: RecentTradesSnapshot) -> float | None:
    trades = snapshot.trades or []
    if trades:
        return _float_or_none(trades[0].price)
    return None


def _resolve_long_liquidation_value(snapshot: LiquidationZonesSnapshot) -> tuple[float | None, bool]:
    explicit = _float_or_none(snapshot.total_longs_liquidated_usd)
    if explicit is not None:
        return explicit, False

    dominant_side = str(snapshot.dominant_side or "").lower()
    if dominant_side == "longs":
        proxy = _float_or_none(snapshot.open_interest_usd)
        if proxy is not None:
            return proxy, True

    return None, False


def build_liquidation_hunt_proposal(
    *,
    base_symbol: str,
    last_price: float,
    vwap: float,
    atr: float,
    liquidation_value_usd: float,
    used_proxy: bool,
    source_agent: str,
    strategy_id: str,
    size_usd: float,
) -> TradeProposal:
    stop_loss = max(last_price - atr, 0.0) if atr > 0 else None
    liquidation_label = "open-interest proxy" if used_proxy else "observed long liquidations"
    deviation_atr = (vwap - last_price) / atr if atr > 0 else 0.0

    rationale = (
        f"[liquidation_hunt] {liquidation_label}={liquidation_value_usd:,.0f} USD; "
        f"price={last_price:.4f} vs VWAP={vwap:.4f}; deviation={deviation_atr:.2f} ATR. "
        "Entering a long mean-reversion recovery toward VWAP after a downside flush."
    )

    return TradeProposal(
        source_agent=source_agent,
        symbol=f"{base_symbol}USDT",
        side="buy",
        order_type="market",
        requested_size_usd=size_usd,
        rationale=rationale,
        strategy_id=strategy_id,
        strategy_template_id="liquidation_hunt",
        timeframe="5m",
        stop_loss_price=stop_loss,
        take_profit_price=vwap,
        metadata={
            "liquidation_hunt": True,
            "liquidation_value_usd": liquidation_value_usd,
            "liquidation_value_source": "open_interest_proxy" if used_proxy else "explicit_liquidations",
            "entry_price": last_price,
            "vwap": vwap,
            "atr": atr,
            "vwap_deviation_atr": deviation_atr,
        },
    )


def find_liquidation_hunt_proposals(
    *,
    universe: Iterable[str] | None,
    size_usd: float,
    source_agent: str,
    strategy_id: str,
) -> list[TradeProposal]:
    proposals: list[TradeProposal] = []

    for base_symbol in _normalize_universe(universe):
        liquidation_snapshot = _fetch_liquidation_snapshot(base_symbol)
        liquidation_value_usd, used_proxy = _resolve_long_liquidation_value(liquidation_snapshot)
        if liquidation_value_usd is None or liquidation_value_usd < LIQUIDATION_THRESHOLD_USD:
            continue

        trade_context = _fetch_recent_trade_context(base_symbol)
        last_price = _last_trade_price(trade_context)
        vwap = _float_or_none(trade_context.vwap)
        indicators = _fetch_indicator_snapshot(base_symbol)
        atr = _float_or_none(indicators.get("atr") or indicators.get("atr_14"))

        if last_price is None or vwap is None or atr is None or atr <= 0:
            logger.debug(
                "liquidation_hunt: missing price context for %s (last=%s vwap=%s atr=%s)",
                base_symbol,
                last_price,
                vwap,
                atr,
            )
            continue

        deviation_atr = (vwap - last_price) / atr
        if deviation_atr < VWAP_DEVIATION_ATR:
            logger.info(
                "liquidation_hunt: skipping %s liquidation=%s deviation_atr=%.2f",
                base_symbol,
                liquidation_value_usd,
                deviation_atr,
            )
            continue

        proposals.append(
            build_liquidation_hunt_proposal(
                base_symbol=base_symbol,
                last_price=last_price,
                vwap=vwap,
                atr=atr,
                liquidation_value_usd=liquidation_value_usd,
                used_proxy=used_proxy,
                source_agent=source_agent,
                strategy_id=strategy_id,
                size_usd=size_usd,
            )
        )

    return proposals


class LiquidationHuntBotRunner(StrategyBotRunner):
    """Runner that hunts forced downside flushes for quick mean-reversion longs."""

    strategy_id = "liquidation_hunt/v1.0"
    source_agent = "liquidation_hunt_bot"
    default_size_usd = 75.0
    min_confidence = 0.0

    def scan(self, universe: list[str]) -> list[TradeProposal]:
        return find_liquidation_hunt_proposals(
            universe=universe or SUPPORTED_SYMBOLS,
            size_usd=self.default_size_usd,
            source_agent=self.source_agent,
            strategy_id=self.strategy_id,
        )