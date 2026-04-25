"""Momentum strategy scorer.

Scores a symbol based on RSI momentum zone, price vs moving averages,
golden/death-cross alignment, MACD histogram direction, and regime alignment.
"""

from __future__ import annotations

from typing import Any

from backend.strategies.chronos_scoring import get_chronos_alignment_score
from backend.strategies.funding import apply_funding_rate_modifier
from backend.strategies.performance_priors import scale_confidence_by_prior
from backend.strategies.registry import ScoredCandidate, STRATEGY_REGISTRY


_STRATEGY = STRATEGY_REGISTRY["momentum"]


def score_momentum(
    symbol: str,
    indicator_data: dict,
    regime: str = "unknown",
    funding_data: Any | None = None,
    timeframe: str = "4h",
) -> ScoredCandidate:
    """Score `symbol` with the momentum strategy.

    Parameters
    ----------
    symbol:
        Clean symbol string (e.g. ``"BTC"``).
    indicator_data:
        ``data`` dict from a ``get_indicator_snapshot`` response.
    regime:
        Market regime string from ``get_market_overview`` (e.g. ``"bullish"``).
    """
    rsi = _f(indicator_data.get("rsi") or indicator_data.get("rsi_14"))
    ma_20 = _f(indicator_data.get("ma_20") or indicator_data.get("sma_20") or indicator_data.get("ema_20"))
    ma_50 = _f(indicator_data.get("ma_50") or indicator_data.get("sma_50") or indicator_data.get("ema_50"))
    close = _f(indicator_data.get("close") or indicator_data.get("price"))
    macd_hist = _f(indicator_data.get("macd_histogram") or indicator_data.get("macd_hist"))

    score = 0.0
    reasons: list[str] = []

    # RSI momentum zone
    if rsi is not None:
        if 55 < rsi < 70:
            score += 0.25
            reasons.append(f"RSI={rsi:.1f} (bullish momentum zone)")
        elif 70 <= rsi < 80:
            score += 0.05
            reasons.append(f"RSI={rsi:.1f} (high momentum, watch overbought)")
        elif rsi >= 80:
            score -= 0.15
            reasons.append(f"RSI={rsi:.1f} (overbought — momentum exhaustion risk)")
        elif 45 <= rsi <= 55:
            score += 0.05
            reasons.append(f"RSI={rsi:.1f} (mid-range — weak momentum)")
        elif 30 < rsi < 45:
            score -= 0.15
            reasons.append(f"RSI={rsi:.1f} (below midline — bearish bias)")
        else:
            score -= 0.25
            reasons.append(f"RSI={rsi:.1f} (oversold — momentum against entry)")

    # Price vs 20 MA
    if close is not None and ma_20 is not None:
        if close > ma_20:
            pct = (close - ma_20) / ma_20 * 100
            score += 0.20
            reasons.append(f"Price {pct:.1f}% above 20MA — uptrend support")
        else:
            pct = (ma_20 - close) / ma_20 * 100
            score -= 0.15
            reasons.append(f"Price {pct:.1f}% below 20MA — downtrend signal")

    # MA alignment (golden / death cross)
    if ma_20 is not None and ma_50 is not None:
        if ma_20 > ma_50:
            score += 0.15
            reasons.append("20MA > 50MA — golden cross alignment")
        else:
            score -= 0.10
            reasons.append("20MA < 50MA — death cross bias")

    # MACD histogram direction
    if macd_hist is not None:
        if macd_hist > 0:
            score += 0.10
            reasons.append(f"MACD histogram +{macd_hist:.4f} (bullish)")
        else:
            score -= 0.05
            reasons.append(f"MACD histogram {macd_hist:.4f} (bearish)")

    # Macro regime bonus
    regime_lower = regime.lower()
    if ("bull" in regime_lower or "risk_on" in regime_lower) and score > 0:
        score += 0.10
        reasons.append(f"Regime aligned: {regime}")
    elif "bear" in regime_lower or "risk_off" in regime_lower:
        score -= 0.05
        reasons.append(f"Regime headwind: {regime}")

    # Funding carry/crowding modifier (small nudge, not standalone signal)
    score = apply_funding_rate_modifier(
        symbol=symbol,
        score=score,
        reasons=reasons,
        funding_data=funding_data,
    )

    if score >= 0.35:
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
            "atr": _f(indicator_data.get("atr") or indicator_data.get("atr_14")),
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
