"""Concrete bot runners for the built-in Hermes strategies.

Each runner wires a strategy scorer from ``backend.strategies`` to live
market data tools and submits proposals through the shared execution pipeline.

Runners are registered in ``BOT_RUNNER_REGISTRY`` so the
``run_strategy_cycle`` tool can look them up by name.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.strategies.breakout import score_breakout
from backend.strategies.mean_reversion import score_mean_reversion
from backend.strategies.momentum import score_momentum
from backend.strategies.registry import ScoredCandidate
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


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

BOT_RUNNER_REGISTRY: dict[str, type[StrategyBotRunner]] = {
    "momentum": MomentumBotRunner,
    "mean_reversion": MeanReversionBotRunner,
    "breakout": BreakoutBotRunner,
}
"""Named registry of built-in bot runners.

Lookup by strategy name to instantiate the runner::

    from backend.strategies.runners import BOT_RUNNER_REGISTRY
    RunnerCls = BOT_RUNNER_REGISTRY["momentum"]
    runner = RunnerCls()
    results = runner.run_cycle(["BTC", "ETH"])
"""
