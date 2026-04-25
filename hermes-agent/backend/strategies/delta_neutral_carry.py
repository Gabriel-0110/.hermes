"""Delta-neutral carry strategy for negative BitMart perpetual funding."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from backend.trading.bot_runner import StrategyBotRunner, paired_proposal_from_legs
from backend.trading.models import TradeProposal, TradeProposalLeg

logger = logging.getLogger(__name__)

SUPPORTED_SYMBOLS = ("ETH", "SOL", "BTC", "XRP")
FUNDING_THRESHOLD = -0.00012  # -0.012% per 8h
BASIS_THRESHOLD = 0.004       # 0.4%
DELTA_TOLERANCE_USD = 5.0


def _to_float(value: Any) -> float | None:
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


def _fetch_funding_snapshot(symbols: list[str]) -> list[dict[str, Any]]:
    from backend.tools.get_funding_rates import get_funding_rates

    response = get_funding_rates(
        {
            "symbols": [f"{symbol}USDT" for symbol in symbols],
            "limit": max(len(symbols), 1),
        }
    )
    data = response.get("data") or {}
    entries = data.get("symbols") if isinstance(data, Mapping) else []
    return [entry for entry in entries if isinstance(entry, Mapping)]


def _basis(mark_price: float, index_price: float) -> float:
    if index_price <= 0:
        return 0.0
    return abs(mark_price - index_price) / index_price


def _pair_amounts(size_usd: float, *, spot_price: float, perp_price: float) -> tuple[float, float, float]:
    if size_usd <= 0 or spot_price <= 0 or perp_price <= 0:
        raise ValueError("size_usd, spot_price, and perp_price must be positive")

    spot_amount = size_usd / spot_price
    perp_amount = size_usd / perp_price
    delta_usd = abs((spot_amount * spot_price) - (perp_amount * perp_price))
    if delta_usd > DELTA_TOLERANCE_USD:
        scale = DELTA_TOLERANCE_USD / delta_usd
        spot_amount *= scale
        perp_amount *= scale
        delta_usd = abs((spot_amount * spot_price) - (perp_amount * perp_price))
    return spot_amount, perp_amount, delta_usd


def build_carry_proposal(
    *,
    base_symbol: str,
    funding_rate: float,
    mark_price: float,
    index_price: float,
    size_usd: float,
    source_agent: str,
    strategy_id: str,
) -> TradeProposal:
    basis_value = _basis(mark_price, index_price)
    spot_amount, perp_amount, delta_usd = _pair_amounts(
        size_usd,
        spot_price=index_price,
        perp_price=mark_price,
    )

    rationale = (
        f"[delta_neutral_carry] funding={funding_rate * 100:.4f}% / 8h, "
        f"basis={basis_value * 100:.3f}%, delta_estimate=${delta_usd:.2f}; "
        f"buy spot and short perp to harvest negative funding with tight basis."
    )

    return paired_proposal_from_legs(
        symbol=f"{base_symbol}USDT",
        source_agent=source_agent,
        requested_size_usd=size_usd,
        rationale=rationale,
        strategy_id=strategy_id,
        strategy_template_id="delta_neutral_carry",
        timeframe="8h",
        legs=[
            TradeProposalLeg(
                symbol=f"{base_symbol}/USDT",
                side="buy",
                order_type="market",
                requested_size_usd=size_usd,
                amount=spot_amount,
                venue="bitmart",
                account_type="spot",
                metadata={"leg_role": "spot_long", "carry_trade": True},
            ),
            TradeProposalLeg(
                symbol=f"{base_symbol}USDT",
                side="sell",
                order_type="market",
                requested_size_usd=size_usd,
                amount=perp_amount,
                venue="bitmart",
                account_type="swap",
                position_side="short",
                metadata={"leg_role": "perp_short", "carry_trade": True},
            ),
        ],
        metadata={
            "carry_trade": True,
            "carry_trade_max_equity_pct": 30.0,
            "paired_action": "enter",
            "base_symbol": base_symbol,
            "funding_rate": funding_rate,
            "basis_pct": basis_value * 100,
            "spot_price": index_price,
            "perp_mark_price": mark_price,
            "delta_estimate_usd": delta_usd,
        },
    )


def find_carry_proposals(
    *,
    universe: Iterable[str] | None,
    size_usd: float,
    source_agent: str,
    strategy_id: str,
) -> list[TradeProposal]:
    proposals: list[TradeProposal] = []
    for entry in _fetch_funding_snapshot(_normalize_universe(universe)):
        symbol = str(entry.get("symbol") or "").upper()
        base_symbol = symbol.replace("USDT", "")
        funding_rate = _to_float(entry.get("funding_rate"))
        mark_price = _to_float(entry.get("mark_price"))
        index_price = _to_float(entry.get("index_price"))

        if base_symbol not in SUPPORTED_SYMBOLS:
            continue
        if funding_rate is None or funding_rate > FUNDING_THRESHOLD:
            continue
        if mark_price is None or index_price is None or mark_price <= 0 or index_price <= 0:
            logger.debug("delta_neutral_carry: missing price context for %s", base_symbol)
            continue

        basis_value = _basis(mark_price, index_price)
        if basis_value >= BASIS_THRESHOLD:
            logger.info(
                "delta_neutral_carry: skipping %s funding=%.5f basis=%.4f",
                base_symbol,
                funding_rate,
                basis_value,
            )
            continue

        proposals.append(
            build_carry_proposal(
                base_symbol=base_symbol,
                funding_rate=funding_rate,
                mark_price=mark_price,
                index_price=index_price,
                size_usd=size_usd,
                source_agent=source_agent,
                strategy_id=strategy_id,
            )
        )

    return proposals


class DeltaNeutralCarryBotRunner(StrategyBotRunner):
    """Runner that emits paired spot/perp carry proposals."""

    strategy_id = "delta_neutral_carry/v1.0"
    source_agent = "delta_neutral_carry_bot"
    default_size_usd = 150.0
    min_confidence = 0.0

    def scan(self, universe: list[str]) -> list[TradeProposal]:
        return find_carry_proposals(
            universe=universe or SUPPORTED_SYMBOLS,
            size_usd=self.default_size_usd,
            source_agent=self.source_agent,
            strategy_id=self.strategy_id,
        )