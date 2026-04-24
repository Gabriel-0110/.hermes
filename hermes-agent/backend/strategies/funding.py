"""Funding-rate context helpers for strategy scorers.

Funding sign convention used here follows the common perpetual-swap convention
already documented in ``BitMartPublicClient``:
- positive funding: longs pay shorts -> shorts receive carry
- negative funding: shorts pay longs -> longs receive carry

The helper treats funding as a small carry/crowding modifier, never as a
standalone signal. It nudges an existing long/short bias by a capped amount and
adds an auditable rationale fragment.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def apply_funding_rate_modifier(
    *,
    symbol: str,
    score: float,
    reasons: list[str],
    funding_data: Any | None,
    max_bonus: float = 0.08,
    max_penalty: float = 0.06,
    threshold: float = 0.0001,
) -> float:
    """Return ``score`` adjusted by funding carry/crowding context.

    ``funding_data`` may be a plain mapping like ``{"BTC": -0.0003}``, a
    mapping keyed by ``BTCUSDT``, or a tool response / model dump containing a
    ``symbols`` list with ``symbol`` and ``funding_rate`` fields.
    """

    rate = extract_funding_rate(symbol, funding_data)
    if rate is None or abs(rate) < threshold or score == 0:
        return score

    adjustment = min(max(abs(rate) * 100.0, 0.02), max_bonus)
    penalty = min(max(abs(rate) * 75.0, 0.015), max_penalty)

    # Positive score = long bias. Negative score = short bias.
    if score > 0:
        if rate < 0:
            score += adjustment
            reasons.append(f"Funding {rate * 100:.4f}% favors longs (shorts pay)")
        else:
            score -= penalty
            reasons.append(f"Funding {rate * 100:.4f}% is crowded-long headwind (longs pay)")
    else:
        if rate > 0:
            score -= adjustment
            reasons.append(f"Funding {rate * 100:.4f}% favors shorts (longs pay)")
        else:
            score += penalty
            reasons.append(f"Funding {rate * 100:.4f}% is short-carry headwind (shorts pay)")

    return score


def extract_funding_rate(symbol: str, funding_data: Any | None) -> float | None:
    """Extract a funding rate for ``symbol`` from common payload shapes."""

    if funding_data is None:
        return None

    clean = _clean_symbol(symbol)
    keys = {clean, f"{clean}USDT", f"{clean}/USDT", f"{clean}/USD"}

    if isinstance(funding_data, Mapping):
        # Tool envelope / snapshot shape.
        if "data" in funding_data:
            nested = extract_funding_rate(symbol, funding_data.get("data"))
            if nested is not None:
                return nested
        if "symbols" in funding_data:
            nested = extract_funding_rate(symbol, funding_data.get("symbols"))
            if nested is not None:
                return nested
        for key in keys:
            if key in funding_data:
                return _to_float(funding_data.get(key))
        # Some callers pass one entry directly.
        entry_symbol = funding_data.get("symbol")
        if entry_symbol and _clean_symbol(str(entry_symbol)) == clean:
            return _to_float(funding_data.get("funding_rate") or funding_data.get("rate"))

    if isinstance(funding_data, list | tuple):
        for item in funding_data:
            if isinstance(item, Mapping):
                entry_symbol = item.get("symbol")
                if entry_symbol and _clean_symbol(str(entry_symbol)) == clean:
                    return _to_float(item.get("funding_rate") or item.get("rate"))

    return None


def _clean_symbol(symbol: str) -> str:
    return symbol.upper().replace("/USDT", "").replace("/USD", "").replace("USDT", "").replace("USD", "")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
