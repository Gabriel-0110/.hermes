"""Breakout strategy scorer.

Detects compressed volatility prior to potential expansion using ATR relative
to its rolling average, Bollinger Band width compression, volume surge, and
(optionally) order-book spread as a liquidity proxy.
"""

from __future__ import annotations

from typing import Any

from backend.strategies.funding import apply_funding_rate_modifier
from backend.strategies.performance_priors import scale_confidence_by_prior
from backend.strategies.registry import ScoredCandidate, STRATEGY_REGISTRY


_STRATEGY = STRATEGY_REGISTRY["breakout"]


def score_breakout(
    symbol: str,
    indicator_data: dict,
    ohlcv_bars: list[dict] | None = None,
    order_book_data: dict | None = None,
    regime: str = "unknown",
    funding_data: Any | None = None,
) -> ScoredCandidate:
    """Score `symbol` with the breakout strategy.

    Parameters
    ----------
    symbol:
        Clean symbol string (e.g. ``"SOL"``).
    indicator_data:
        ``data`` dict from a ``get_indicator_snapshot`` response.
    ohlcv_bars:
        Optional list of OHLCV bar dicts (newest last) for volume analysis.
        If None, volume compression check is skipped.
    order_book_data:
        Optional ``data`` dict from ``get_order_book`` for spread analysis.
        If None, liquidity check is skipped.
    regime:
        Market regime string.
    """
    atr = _f(indicator_data.get("atr") or indicator_data.get("atr_14"))
    close = _f(indicator_data.get("close") or indicator_data.get("price"))
    bb_upper = _f(indicator_data.get("bb_upper") or indicator_data.get("upper_band"))
    bb_lower = _f(indicator_data.get("bb_lower") or indicator_data.get("lower_band"))
    ma_20 = _f(indicator_data.get("ma_20") or indicator_data.get("sma_20") or indicator_data.get("ema_20"))

    score = 0.0
    reasons: list[str] = []

    # Bollinger Band width compression
    if bb_upper is not None and bb_lower is not None and ma_20 is not None and ma_20 > 0:
        bb_width_pct = (bb_upper - bb_lower) / ma_20 * 100
        if bb_width_pct < 2.0:
            score += 0.30
            reasons.append(f"BB width {bb_width_pct:.2f}% (tight squeeze — breakout setup)")
        elif bb_width_pct < 4.0:
            score += 0.15
            reasons.append(f"BB width {bb_width_pct:.2f}% (moderate compression)")
        elif bb_width_pct > 10.0:
            score -= 0.10
            reasons.append(f"BB width {bb_width_pct:.2f}% (already expanded — breakout may be late)")

    # ATR relative compression (if we have bars to compute average ATR)
    if atr is not None and ohlcv_bars and len(ohlcv_bars) >= 10:
        try:
            recent_ranges = [
                abs(_f(b.get("high", 0)) - _f(b.get("low", 0)))  # type: ignore[arg-type]
                for b in ohlcv_bars[-20:]
                if b.get("high") and b.get("low")
            ]
            if recent_ranges:
                avg_range = sum(recent_ranges) / len(recent_ranges)
                if avg_range > 0:
                    atr_ratio = atr / avg_range
                    if atr_ratio < 0.7:
                        score += 0.20
                        reasons.append(f"ATR {atr_ratio:.2f}x avg range (compressed — coiling)")
                    elif atr_ratio < 0.85:
                        score += 0.10
                        reasons.append(f"ATR {atr_ratio:.2f}x avg range (slightly compressed)")
                    elif atr_ratio > 1.5:
                        score -= 0.15
                        reasons.append(f"ATR {atr_ratio:.2f}x avg range (already expanding)")
        except Exception:
            pass

    # Volume surge detection (last bar vs 10-bar average)
    if ohlcv_bars and len(ohlcv_bars) >= 3:
        try:
            vols = [_f(b.get("volume")) for b in ohlcv_bars if b.get("volume") is not None]
            vols_clean = [v for v in vols if v is not None]
            if len(vols_clean) >= 3:
                avg_vol = sum(vols_clean[:-1]) / len(vols_clean[:-1])
                last_vol = vols_clean[-1]
                if avg_vol > 0:
                    vol_ratio = last_vol / avg_vol
                    if vol_ratio >= 2.0:
                        score += 0.25
                        reasons.append(f"Volume {vol_ratio:.1f}x average (surge — breakout fuel)")
                    elif vol_ratio >= 1.5:
                        score += 0.10
                        reasons.append(f"Volume {vol_ratio:.1f}x average (elevated)")
                    elif vol_ratio < 0.5:
                        score -= 0.10
                        reasons.append(f"Volume {vol_ratio:.1f}x average (dry — conviction unclear)")
        except Exception:
            pass

    # Order book spread as liquidity proxy (tight spread = breakout-ready)
    if order_book_data:
        spread_pct = _f(order_book_data.get("spread_pct"))
        imbalance = _f(order_book_data.get("imbalance"))
        if spread_pct is not None:
            if spread_pct < 0.05:
                score += 0.10
                reasons.append(f"Spread {spread_pct:.3f}% (tight — liquid breakout conditions)")
            elif spread_pct > 0.3:
                score -= 0.10
                reasons.append(f"Spread {spread_pct:.3f}% (wide — illiquid)")
        if imbalance is not None:
            if imbalance > 0.2:
                score += 0.10
                reasons.append(f"Order book bid-heavy (imbalance={imbalance:.2f}) — buy pressure")
            elif imbalance < -0.2:
                score -= 0.05
                reasons.append(f"Order book ask-heavy (imbalance={imbalance:.2f}) — sell pressure")

    # Regime modifier — breakouts work better in trending regimes
    regime_lower = regime.lower()
    if "bull" in regime_lower or "risk_on" in regime_lower:
        if score > 0:
            score += 0.05
            reasons.append(f"Bullish regime supports upside breakout: {regime}")
    elif "bear" in regime_lower or "risk_off" in regime_lower:
        score -= 0.05
        reasons.append(f"Bearish regime headwind for breakout: {regime}")

    # Funding carry/crowding modifier (small nudge, not standalone signal)
    score = apply_funding_rate_modifier(
        symbol=symbol,
        score=score,
        reasons=reasons,
        funding_data=funding_data,
    )

    confidence = round(min(max(score, 0.01), 0.95), 2)
    confidence, prior = scale_confidence_by_prior(_STRATEGY.name, confidence)
    if prior.resolved_count and abs(prior.multiplier - 1.0) >= 0.02:
        reasons.append(
            f"Strategy prior adjusted confidence x{prior.multiplier:.2f} from {prior.resolved_count} resolved signals"
        )

    if score >= 0.30:
        direction = "long"
    elif score <= -0.25:
        direction = "short"
    else:
        direction = "watch"

    if not reasons:
        reasons = ["Insufficient indicator data for breakout assessment"]

    return ScoredCandidate(
        symbol=symbol,
        direction=direction,
        confidence=confidence,
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
