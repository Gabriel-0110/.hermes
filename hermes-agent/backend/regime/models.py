"""Market regime data models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MarketRegime(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"


class RegimeSnapshot(BaseModel):
    regime: MarketRegime = MarketRegime.UNKNOWN
    trend_slope_1h: float | None = None
    trend_slope_4h: float | None = None
    vol_of_vol: float | None = None
    vol_of_vol_p90: float | None = None
    breadth_pct: float | None = None
    universe_tag: str = "default"
    bar_close_ts: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)
