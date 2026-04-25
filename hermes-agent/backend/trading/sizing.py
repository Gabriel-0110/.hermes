"""Volatility-targeted trade sizing helpers."""

from __future__ import annotations

from math import sqrt


def vol_target_size(
    symbol: str,
    risk_budget_usd: float,
    atr: float | None,
    *,
    price: float | None = None,
    holding_period_hours: float = 4.0,
    min_size_usd: float = 25.0,
    max_size_usd: float | None = None,
) -> float:
    """Convert a USD risk budget into a volatility-scaled USD notional.

    The helper keeps the prompt-required signature (`symbol`, `risk_budget_usd`,
    `atr`) while accepting optional price/time-horizon context so ATR can be
    normalized into a per-dollar volatility estimate.
    """

    del symbol  # reserved for future venue/symbol-specific sizing rules

    budget = max(float(risk_budget_usd or 0.0), 0.0)
    if budget <= 0:
        return 0.0

    atr_value = float(atr or 0.0)
    if atr_value <= 0:
        size = budget
    elif price is not None and float(price) > 0:
        normalized_vol = (atr_value / float(price)) * sqrt(max(float(holding_period_hours or 1.0), 1.0))
        size = budget if normalized_vol <= 0 else budget / normalized_vol
    else:
        size = budget / atr_value

    if max_size_usd is not None:
        size = min(size, max(float(max_size_usd), 0.0))
    size = max(size, max(float(min_size_usd), 0.0))
    return round(size, 2)