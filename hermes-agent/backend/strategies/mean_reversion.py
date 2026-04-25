"""Mean-reversion strategy scorer.

Identifies counter-trend opportunities using RSI extremes, price z-score
relative to the 20-period moving average, and Bollinger Band proximity.
"""

from __future__ import annotations

from typing import Any

from backend.strategies.chronos_scoring import get_chronos_alignment_score
from backend.strategies.funding import apply_funding_rate_modifier
from backend.strategies.performance_priors import scale_confidence_by_prior
from backend.strategies.registry import ScoredCandidate, STRATEGY_REGISTRY


_STRATEGY = STRATEGY_REGISTRY["mean_reversion"]


def score_mean_reversion(
    symbol: str,
    indicator_data: dict,
    regime: str = "unknown",
    funding_data: Any | None = None,
    timeframe: str = "4h",
) -> ScoredCandidate:
    """Score `symbol` with the mean-reversion strategy.

    Parameters
    ----------
    symbol:
        Clean symbol string (e.g. ``"ETH"``).
    indicator_data:
        ``data`` dict from a ``get_indicator_snapshot`` response.
    regime:
        Market regime string (used as a penalty/bonus modifier).
    """
    rsi = _f(indicator_data.get("rsi") or indicator_data.get("rsi_14"))
    close = _f(indicator_data.get("close") or indicator_data.get("price"))
    ma_20 = _f(indicator_data.get("ma_20") or indicator_data.get("sma_20") or indicator_data.get("ema_20"))
    atr = _f(indicator_data.get("atr") or indicator_data.get("atr_14"))
    # Bollinger bands (may or may not be present depending on provider)
    bb_upper = _f(indicator_data.get("bb_upper") or indicator_data.get("upper_band"))
    bb_lower = _f(indicator_data.get("bb_lower") or indicator_data.get("lower_band"))

    score = 0.0
    reasons: list[str] = []

    # RSI extremes — primary mean-reversion signal
    if rsi is not None:
        if rsi <= 25:
            score += 0.40
            reasons.append(f"RSI={rsi:.1f} (deeply oversold — strong reversion candidate)")
        elif rsi <= 30:
            score += 0.30
            reasons.append(f"RSI={rsi:.1f} (oversold — reversion candidate)")
        elif rsi <= 38:
            score += 0.10
            reasons.append(f"RSI={rsi:.1f} (mild oversold bias)")
        elif rsi >= 80:
            score -= 0.35
            reasons.append(f"RSI={rsi:.1f} (deeply overbought — short reversion candidate)")
        elif rsi >= 72:
            score -= 0.25
            reasons.append(f"RSI={rsi:.1f} (overbought — short reversion candidate)")
        elif rsi >= 65:
            score -= 0.10
            reasons.append(f"RSI={rsi:.1f} (mildly overbought)")
        else:
            score -= 0.05
            reasons.append(f"RSI={rsi:.1f} (neutral — no clear reversion signal)")

    # Price z-score relative to 20 MA (deviation as ATR multiples)
    if close is not None and ma_20 is not None and atr is not None and atr > 0:
        deviation = (close - ma_20) / atr
        if deviation <= -2.0:
            score += 0.25
            reasons.append(f"Price {deviation:.1f} ATR below 20MA (stretched low)")
        elif deviation <= -1.0:
            score += 0.10
            reasons.append(f"Price {deviation:.1f} ATR below 20MA (extended)")
        elif deviation >= 2.0:
            score -= 0.20
            reasons.append(f"Price {deviation:.1f} ATR above 20MA (stretched high)")
        elif deviation >= 1.0:
            score -= 0.10
            reasons.append(f"Price {deviation:.1f} ATR above 20MA (extended)")
    elif close is not None and ma_20 is not None:
        # Fallback: simple pct deviation
        pct = (close - ma_20) / ma_20 * 100
        if pct <= -5:
            score += 0.15
            reasons.append(f"Price {pct:.1f}% below 20MA (extended downside)")
        elif pct >= 8:
            score -= 0.15
            reasons.append(f"Price {pct:.1f}% above 20MA (extended upside)")

    # Bollinger Band proximity
    if close is not None and bb_lower is not None and bb_upper is not None:
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            pct_in_band = (close - bb_lower) / bb_range
            if pct_in_band <= 0.05:
                score += 0.20
                reasons.append("Price at/below lower Bollinger Band — mean-reversion buy signal")
            elif pct_in_band <= 0.15:
                score += 0.10
                reasons.append("Price near lower Bollinger Band")
            elif pct_in_band >= 0.95:
                score -= 0.20
                reasons.append("Price at/above upper Bollinger Band — mean-reversion sell signal")
            elif pct_in_band >= 0.85:
                score -= 0.10
                reasons.append("Price near upper Bollinger Band")

    # Regime modifier — mean reversion works better in ranging markets
    regime_lower = regime.lower()
    if "ranging" in regime_lower or "neutral" in regime_lower or "sideways" in regime_lower:
        score += 0.05
        reasons.append(f"Regime supports mean reversion: {regime}")
    elif "strong" in regime_lower and ("bull" in regime_lower or "bear" in regime_lower):
        # Strong trend reduces reversion probability
        score *= 0.7
        reasons.append(f"Caution: strong trend regime ({regime}) reduces reversion probability")

    # Funding carry/crowding modifier (small nudge, not standalone signal)
    score = apply_funding_rate_modifier(
        symbol=symbol,
        score=score,
        reasons=reasons,
        funding_data=funding_data,
    )

    if score >= 0.30:
        direction = "long"
    elif score <= -0.25:
        direction = "short"
    else:
        direction = "watch"

    raw_confidence = round(min(max(abs(score), 0.01), 0.95), 2)
    chronos = get_chronos_alignment_score(symbol, direction, interval=timeframe)
    confidence = round(min(max(raw_confidence * (0.5 + 0.5 * chronos.score), 0.01), 0.95), 2)
    confidence, prior = scale_confidence_by_prior(_STRATEGY.name, confidence)
    if prior.resolved_count and abs(prior.multiplier - 1.0) >= 0.02:
        reasons.append(
            f"Strategy prior adjusted confidence x{prior.multiplier:.2f} from {prior.resolved_count} resolved signals"
        )
    if chronos.error:
        reasons.append("Chronos forecast unavailable — applied neutral alignment weight")
    else:
        reasons.append(f"Chronos alignment {chronos.score:.2f} on {timeframe} / {chronos.horizon} bars")

    if not reasons:
        reasons = ["Insufficient indicator data"]

    return ScoredCandidate(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        chronos_score=chronos.score,
        sizing_hints={
            "atr": atr,
            "price": close,
            "timeframe": timeframe,
            "regime": regime,
        },
        rationale="; ".join(reasons),
        strategy_name=_STRATEGY.name,
        strategy_version=_STRATEGY.version,
    )


def _f(v: object) -> float | None:
    if v is None:
        return None
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
