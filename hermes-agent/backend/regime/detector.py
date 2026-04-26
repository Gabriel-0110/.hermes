"""Market regime detector — classifies the current market environment.

Uses price-derived signals only (no LLM calls). Designed for the policy
engine hot path: fast, deterministic, and fail-closed (returns UNKNOWN on
any error so the caller can reject with regime_unknown).

Signals:
  - Trend slope: linear regression of log-close over last N bars on 1h and 4h.
    Agreement between timeframes → trend_up / trend_down.
  - Vol-of-vol: rolling stdev of 1h ATR/price. Above P90 → high_vol.
  - If neither trend nor high_vol triggers → range.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from .models import MarketRegime, RegimeSnapshot

logger = logging.getLogger(__name__)

_TREND_SLOPE_THRESHOLD = 0.0005
_VOL_OF_VOL_P90_DEFAULT = 0.03
_CACHE_TTL_SECONDS = 300


def _log_closes(candles: list[dict[str, Any]]) -> list[float]:
    closes: list[float] = []
    for c in candles:
        close = c.get("close")
        if close is not None and float(close) > 0:
            closes.append(math.log(float(close)))
    return closes


def _linreg_slope(values: list[float]) -> float | None:
    n = len(values)
    if n < 3:
        return None
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = 0.0
    denominator = 0.0
    for i, y in enumerate(values):
        dx = i - x_mean
        numerator += dx * (y - y_mean)
        denominator += dx * dx
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _atr_values(candles: list[dict[str, Any]]) -> list[float]:
    atrs: list[float] = []
    prev_close: float | None = None
    for c in candles:
        high = float(c.get("high") or c.get("close", 0))
        low = float(c.get("low") or c.get("close", 0))
        close = float(c.get("close", 0))
        if close <= 0:
            prev_close = close
            continue
        if prev_close is not None and prev_close > 0:
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        else:
            tr = high - low
        atrs.append(tr / close)
        prev_close = close
    return atrs


def _vol_of_vol(candles_1h: list[dict[str, Any]], window: int = 20) -> tuple[float | None, float | None]:
    atrs = _atr_values(candles_1h)
    if len(atrs) < window:
        return None, None
    recent = atrs[-window:]
    mean = sum(recent) / len(recent)
    variance = sum((x - mean) ** 2 for x in recent) / len(recent)
    stdev = math.sqrt(variance)

    if len(atrs) >= 100:
        all_stdevs: list[float] = []
        for i in range(window, len(atrs) + 1):
            w = atrs[i - window:i]
            m = sum(w) / len(w)
            v = sum((x - m) ** 2 for x in w) / len(w)
            all_stdevs.append(math.sqrt(v))
        all_stdevs.sort()
        p90_idx = int(len(all_stdevs) * 0.90)
        p90 = all_stdevs[min(p90_idx, len(all_stdevs) - 1)]
    else:
        p90 = _VOL_OF_VOL_P90_DEFAULT

    return stdev, p90


def detect_regime(
    candles_1h: list[dict[str, Any]],
    candles_4h: list[dict[str, Any]],
    *,
    universe_tag: str = "default",
    bar_close_ts: str | None = None,
    breadth_pct: float | None = None,
) -> RegimeSnapshot:
    slope_1h = _linreg_slope(_log_closes(candles_1h))
    slope_4h = _linreg_slope(_log_closes(candles_4h))

    vov, vov_p90 = _vol_of_vol(candles_1h)

    if vov is not None and vov_p90 is not None and vov > vov_p90:
        regime = MarketRegime.HIGH_VOL
    elif slope_1h is not None and slope_4h is not None:
        if slope_1h > _TREND_SLOPE_THRESHOLD and slope_4h > _TREND_SLOPE_THRESHOLD:
            regime = MarketRegime.TREND_UP
        elif slope_1h < -_TREND_SLOPE_THRESHOLD and slope_4h < -_TREND_SLOPE_THRESHOLD:
            regime = MarketRegime.TREND_DOWN
        else:
            regime = MarketRegime.RANGE
    else:
        regime = MarketRegime.UNKNOWN

    return RegimeSnapshot(
        regime=regime,
        trend_slope_1h=slope_1h,
        trend_slope_4h=slope_4h,
        vol_of_vol=vov,
        vol_of_vol_p90=vov_p90,
        breadth_pct=breadth_pct,
        universe_tag=universe_tag,
        bar_close_ts=bar_close_ts,
    )


def get_cached_regime(*, universe_tag: str = "default") -> RegimeSnapshot | None:
    try:
        from backend.redis_client import get_redis_client
        client = get_redis_client()
        raw = client.get(f"hermes:regime:{universe_tag}")
        if raw:
            return RegimeSnapshot.model_validate_json(raw)
    except Exception:
        logger.debug("Redis regime cache miss or unavailable for %s", universe_tag)
    return None


def cache_regime(snapshot: RegimeSnapshot) -> None:
    try:
        from backend.redis_client import get_redis_client
        client = get_redis_client()
        key = f"hermes:regime:{snapshot.universe_tag}"
        client.set(key, snapshot.model_dump_json(), ex=_CACHE_TTL_SECONDS)
    except Exception:
        logger.debug("Failed to cache regime snapshot for %s", snapshot.universe_tag)


def get_current_regime(*, universe_tag: str = "default") -> RegimeSnapshot:
    cached = get_cached_regime(universe_tag=universe_tag)
    if cached is not None:
        return cached
    return RegimeSnapshot(regime=MarketRegime.UNKNOWN, universe_tag=universe_tag)
