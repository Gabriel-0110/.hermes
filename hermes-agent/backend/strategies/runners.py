"""Concrete bot runners for the built-in Hermes strategies.

Each runner wires a strategy scorer from ``backend.strategies`` to live
market data tools and submits proposals through the shared execution pipeline.

Runners are registered in ``BOT_RUNNER_REGISTRY`` so the
``run_strategy_cycle`` tool can look them up by name.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.strategies.delta_neutral_carry import DeltaNeutralCarryBotRunner
from backend.strategies.liquidation_hunt import LiquidationHuntBotRunner
from backend.strategies.breakout import score_breakout
from backend.strategies.mean_reversion import score_mean_reversion
from backend.strategies.momentum import score_momentum
from backend.strategies.registry import ScoredCandidate
from backend.trading.sizing import vol_target_size
from backend.trading.bot_runner import StrategyBotRunner

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared data-fetching helpers
# ---------------------------------------------------------------------------


def _fetch_indicators(symbol: str) -> dict[str, Any]:
    """Return ``data`` dict from ``get_indicator_snapshot`` for *symbol*."""
    try:
        from backend.tools.get_indicator_snapshot import get_indicator_snapshot  # type: ignore[import]

        resp = get_indicator_snapshot({"symbol": symbol})
        return resp.get("data") or {}
    except Exception as exc:
        logger.warning("runners: get_indicator_snapshot failed for %s: %s", symbol, exc)
        return {}


def _fetch_regime() -> str:
    """Return current macro regime string from ``get_market_overview``."""
    try:
        from backend.tools.get_market_overview import get_market_overview  # type: ignore[import]

        resp = get_market_overview({})
        return resp.get("data", {}).get("regime", "unknown") or "unknown"
    except Exception as exc:
        logger.warning("runners: get_market_overview failed: %s", exc)
        return "unknown"


def _fetch_ohlcv(symbol: str, timeframe: str = "4h", limit: int = 30) -> list[dict]:
    """Return OHLCV bar list from ``get_ohlcv`` for *symbol*."""
    try:
        from backend.tools.get_ohlcv import get_ohlcv  # type: ignore[import]

        resp = get_ohlcv({"symbol": symbol, "timeframe": timeframe, "limit": limit})
        return resp.get("data", {}).get("bars") or resp.get("data") or []
    except Exception as exc:
        logger.warning("runners: get_ohlcv failed for %s: %s", symbol, exc)
        return []


def _fetch_funding_rates(universe: list[str]) -> dict[str, float]:
    """Return symbol→funding_rate map for *universe* using public derivatives data."""
    try:
        from backend.tools.get_funding_rates import get_funding_rates  # type: ignore[import]

        symbols = [s.upper().replace("/", "").replace("USD", "USDT") for s in universe]
        normalized = [s if s.endswith("USDT") else f"{s}USDT" for s in symbols]
        resp = get_funding_rates({"symbols": normalized, "limit": max(len(normalized), 1)})
        data = resp.get("data", {}) if resp.get("ok") or "data" in resp else {}
        entries = data.get("symbols", []) if isinstance(data, dict) else []
        out: dict[str, float] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            symbol = str(entry.get("symbol") or "").upper()
            try:
                rate = float(entry.get("funding_rate"))
            except (TypeError, ValueError):
                continue
            clean = symbol.replace("USDT", "").replace("USD", "")
            out[clean] = rate
            out[symbol] = rate
        return out
    except Exception as exc:
        logger.warning("runners: get_funding_rates failed for %s: %s", universe, exc)
        return {}


def _portfolio_risk_budget_usd(*, fallback_usd: float, risk_fraction: float = 0.02) -> tuple[float, float | None]:
    try:
        from backend.tools.get_portfolio_state import get_portfolio_state  # type: ignore[import]

        response = get_portfolio_state({})
        data = response.get("data") if isinstance(response, dict) else {}
        equity = None
        if isinstance(data, dict):
            equity = data.get("total_equity_usd") or data.get("total_value_usd")
        if equity is not None:
            equity_float = float(equity)
            return round(max(equity_float * risk_fraction, fallback_usd), 2), equity_float
    except Exception as exc:
        logger.debug("runners: get_portfolio_state sizing lookup failed: %s", exc)
    return float(fallback_usd), None


def _timeframe_to_hours(value: str | None, *, default: float) -> float:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    try:
        if normalized.endswith("m"):
            return max(float(normalized[:-1]) / 60.0, 0.25)
        if normalized.endswith("h"):
            return max(float(normalized[:-1]), 0.25)
        if normalized.endswith("d"):
            return max(float(normalized[:-1]) * 24.0, 1.0)
    except ValueError:
        return default
    return default


def _vol_target_candidate_size(candidate: ScoredCandidate, *, fallback_usd: float, default_holding_hours: float) -> float:
    hints = candidate.sizing_hints or {}
    atr = hints.get("atr")
    price = hints.get("price")
    timeframe_hours = _timeframe_to_hours(hints.get("timeframe"), default=default_holding_hours)
    risk_budget_usd, equity_usd = _portfolio_risk_budget_usd(fallback_usd=fallback_usd)
    max_size_usd = equity_usd * 0.25 if equity_usd is not None else None
    return vol_target_size(
        candidate.symbol,
        risk_budget_usd,
        float(atr) if atr is not None else None,
        price=float(price) if price is not None else None,
        holding_period_hours=timeframe_hours,
        min_size_usd=fallback_usd,
        max_size_usd=max_size_usd,
    )


# ---------------------------------------------------------------------------
# Momentum runner
# ---------------------------------------------------------------------------


class MomentumBotRunner(StrategyBotRunner):
    """Trend-following bot runner using the built-in momentum scorer.

    Scans each symbol in *universe* for RSI momentum zone, MA alignment,
    MACD direction, and regime bias.  Submits long proposals for high-scoring
    assets.

    Configuration (override as class attributes or per-instance)::

        runner = MomentumBotRunner()
        runner.default_size_usd = 100.0
        runner.min_confidence = 0.30
        results = runner.run_cycle(["BTC", "ETH", "SOL"])
    """

    strategy_id = "momentum/v1.1"
    source_agent = "momentum_bot"
    default_size_usd = 50.0
    min_confidence = 0.30

    def scan(self, universe: list[str]) -> list[ScoredCandidate]:
        regime = _fetch_regime()
        funding_data = _fetch_funding_rates(universe)
        candidates: list[ScoredCandidate] = []
        for symbol in universe:
            indicators = _fetch_indicators(symbol)
            candidate = score_momentum(symbol, indicators, regime=regime, funding_data=funding_data)
            logger.debug(
                "momentum_runner: symbol=%s direction=%s confidence=%.2f",
                symbol,
                candidate.direction,
                candidate.confidence,
            )
            candidates.append(candidate)
        return candidates

    def timeframe_for_candidate(self, candidate: ScoredCandidate) -> str | None:
        return "4h"

    def size_for_candidate(self, candidate: ScoredCandidate) -> float:
        return _vol_target_candidate_size(candidate, fallback_usd=self.default_size_usd, default_holding_hours=4.0)


# ---------------------------------------------------------------------------
# Mean-reversion runner
# ---------------------------------------------------------------------------


class MeanReversionBotRunner(StrategyBotRunner):
    """Counter-trend bot runner using the built-in mean-reversion scorer.

    Scans for oversold/overbought conditions using RSI extremes, z-score, and
    Bollinger Band proximity.  Proposes entries against short-term exhaustion.
    """

    strategy_id = "mean_reversion/v1.0"
    source_agent = "mean_reversion_bot"
    default_size_usd = 40.0
    min_confidence = 0.30

    def scan(self, universe: list[str]) -> list[ScoredCandidate]:
        funding_data = _fetch_funding_rates(universe)
        candidates: list[ScoredCandidate] = []
        for symbol in universe:
            indicators = _fetch_indicators(symbol)
            candidate = score_mean_reversion(symbol, indicators, funding_data=funding_data)
            logger.debug(
                "mean_reversion_runner: symbol=%s direction=%s confidence=%.2f",
                symbol,
                candidate.direction,
                candidate.confidence,
            )
            candidates.append(candidate)
        return candidates

    def timeframe_for_candidate(self, candidate: ScoredCandidate) -> str | None:
        return "1h"

    def size_for_candidate(self, candidate: ScoredCandidate) -> float:
        return _vol_target_candidate_size(candidate, fallback_usd=self.default_size_usd, default_holding_hours=1.0)


# ---------------------------------------------------------------------------
# Breakout runner
# ---------------------------------------------------------------------------


class BreakoutBotRunner(StrategyBotRunner):
    """Volatility-breakout bot runner using the built-in breakout scorer.

    Detects compressed volatility prior to potential expansion using ATR,
    Bollinger Band width, and volume surge.  Requires a regime scan for
    the strongest setups.
    """

    strategy_id = "breakout/v1.0"
    source_agent = "breakout_bot"
    default_size_usd = 50.0
    min_confidence = 0.30

    def scan(self, universe: list[str]) -> list[ScoredCandidate]:
        regime = _fetch_regime()
        funding_data = _fetch_funding_rates(universe)
        candidates: list[ScoredCandidate] = []
        for symbol in universe:
            indicators = _fetch_indicators(symbol)
            ohlcv = _fetch_ohlcv(symbol, timeframe="4h", limit=30)
            candidate = score_breakout(symbol, indicators, ohlcv_bars=ohlcv, regime=regime, funding_data=funding_data)
            logger.debug(
                "breakout_runner: symbol=%s direction=%s confidence=%.2f",
                symbol,
                candidate.direction,
                candidate.confidence,
            )
            candidates.append(candidate)
        return candidates

    def timeframe_for_candidate(self, candidate: ScoredCandidate) -> str | None:
        return "4h"

    def size_for_candidate(self, candidate: ScoredCandidate) -> float:
        return _vol_target_candidate_size(candidate, fallback_usd=self.default_size_usd, default_holding_hours=4.0)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BOT_RUNNER_REGISTRY: dict[str, type[StrategyBotRunner]] = {
    "momentum": MomentumBotRunner,
    "mean_reversion": MeanReversionBotRunner,
    "breakout": BreakoutBotRunner,
    "delta_neutral_carry": DeltaNeutralCarryBotRunner,
    "liquidation_hunt": LiquidationHuntBotRunner,
}
"""Named registry of built-in bot runners.

Lookup by strategy name to instantiate the runner::

    from backend.strategies.runners import BOT_RUNNER_REGISTRY
    RunnerCls = BOT_RUNNER_REGISTRY["momentum"]
    runner = RunnerCls()
    results = runner.run_cycle(["BTC", "ETH"])
"""
