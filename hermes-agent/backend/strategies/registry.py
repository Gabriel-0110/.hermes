"""Strategy registry — named strategy definitions and the shared ScoredCandidate model."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StrategyDefinition(BaseModel):
    """Metadata for a named trading strategy."""

    name: str
    strategy_type: Literal["momentum", "mean_reversion", "breakout"]
    description: str
    version: str = "1.0.0"
    timeframes: list[str]
    universe_filter: str = "all"  # "all" | "large_cap" | "defi" etc.
    min_confidence: float = 0.25


class ScoredCandidate(BaseModel):
    """Output of a strategy scorer for a single symbol."""

    symbol: str
    direction: Literal["long", "short", "watch"]
    confidence: float
    rationale: str
    strategy_name: str
    strategy_version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Registry — add new strategies here
# ---------------------------------------------------------------------------

STRATEGY_REGISTRY: dict[str, StrategyDefinition] = {
    "momentum": StrategyDefinition(
        name="momentum",
        strategy_type="momentum",
        description=(
            "Trend-following strategy: scores by RSI momentum zone, price vs moving averages, "
            "golden/death-cross alignment, MACD histogram direction, and macro regime bias. "
            "Favours assets in established uptrends with supportive macro conditions."
        ),
        version="1.1.0",
        timeframes=["1h", "4h", "1d"],
        universe_filter="all",
        min_confidence=0.25,
    ),
    "mean_reversion": StrategyDefinition(
        name="mean_reversion",
        strategy_type="mean_reversion",
        description=(
            "Counter-trend strategy: identifies oversold/overbought conditions using RSI extremes, "
            "price z-score relative to 20-period MA, and Bollinger Band proximity. "
            "Best suited to range-bound or correcting markets."
        ),
        version="1.0.0",
        timeframes=["1h", "4h"],
        universe_filter="all",
        min_confidence=0.25,
    ),
    "breakout": StrategyDefinition(
        name="breakout",
        strategy_type="breakout",
        description=(
            "Momentum breakout strategy: detects compressed volatility followed by expansion. "
            "Scores by ATR relative to 20-period ATR average, Bollinger Band width compression, "
            "volume surge above average, and order-book spread tightness as liquidity proxy."
        ),
        version="1.0.0",
        timeframes=["4h", "1d"],
        universe_filter="all",
        min_confidence=0.25,
    ),
}
