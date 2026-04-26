"""Strategy registry — named strategy definitions and scorer lookup helpers."""

from __future__ import annotations

from typing import Callable, Literal

from pydantic import BaseModel


class StrategyDefinition(BaseModel):
    """Metadata for a named trading strategy."""

    name: str
    strategy_type: Literal["momentum", "mean_reversion", "breakout", "carry"]
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


StrategyScorer = Callable[..., ScoredCandidate]


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
    "delta_neutral_carry": StrategyDefinition(
        name="delta_neutral_carry",
        strategy_type="carry",
        description=(
            "Delta-neutral funding harvest strategy: buy spot while shorting the matching perpetual "
            "when funding is sufficiently negative and the spot/perp basis stays tight."
        ),
        version="1.0.0",
        timeframes=["8h"],
        universe_filter="large_cap",
        min_confidence=0.0,
    ),
    "whale_follower": StrategyDefinition(
        name="whale_follower",
        strategy_type="momentum",
        description=(
            "Smart-money whale-flow following strategy: monitors on-chain accumulation events from "
            "labeled high-conviction wallets. Triggers on fresh accumulation above $50k threshold "
            "across BTC, ETH, SOL, XRP, ADA, and AVAX. Scores by accumulation size, unique wallet "
            "count, trade count, wallet profit/win-rate priors, and macro regime alignment."
        ),
        version="1.0.0",
        timeframes=["30m"],
        universe_filter="large_cap",
        min_confidence=0.25,
    ),
}


def resolve_strategy_name(*candidates: str | None) -> str | None:
    """Resolve free-form strategy labels to canonical registry keys."""

    for candidate in candidates:
        resolved = _normalize_strategy_name(candidate)
        if resolved is not None:
            return resolved
    return None


def resolve_strategy_definition(*candidates: str | None) -> StrategyDefinition | None:
    """Resolve free-form labels directly to a registered strategy definition."""

    strategy_name = resolve_strategy_name(*candidates)
    if strategy_name is None:
        return None
    return STRATEGY_REGISTRY.get(strategy_name)


def get_strategy_scorer(strategy_name: str) -> StrategyScorer:
    """Return the scorer callable for a registered strategy name."""

    normalized = resolve_strategy_name(strategy_name)
    if normalized is None:
        raise ValueError(
            f"Unknown strategy {strategy_name!r}. Available: {sorted(STRATEGY_REGISTRY)}"
        )

    if normalized == "momentum":
        from backend.strategies.momentum import score_momentum

        return score_momentum
    if normalized == "mean_reversion":
        from backend.strategies.mean_reversion import score_mean_reversion

        return score_mean_reversion
    if normalized == "breakout":
        from backend.strategies.breakout import score_breakout

        return score_breakout
    if normalized == "whale_follower":
        from backend.strategies.whale_follower import score_whale_follower

        return score_whale_follower

    raise ValueError(
        f"No scorer registered for strategy {strategy_name!r}. Available: {sorted(STRATEGY_REGISTRY)}"
    )


def _normalize_strategy_name(value: str | None) -> str | None:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None

    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in STRATEGY_REGISTRY:
        return normalized
    if "momentum" in normalized:
        return "momentum"
    if "breakout" in normalized:
        return "breakout"
    if "mean" in normalized and ("reversion" in normalized or "revert" in normalized):
        return "mean_reversion"
    if "carry" in normalized:
        return "delta_neutral_carry"
    return None
