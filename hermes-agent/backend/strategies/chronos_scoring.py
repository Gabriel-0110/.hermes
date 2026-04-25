"""Shared Chronos forecast caching and direction-alignment scoring for strategy scorers."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import ChronosForecastRow
from backend.db.session import get_engine
from backend.tools.get_forecast_projection import get_forecast_projection

logger = logging.getLogger(__name__)

_QUOTE_SUFFIXES = ("USDT", "USDC", "USD", "BTC", "ETH")


@dataclass(frozen=True, slots=True)
class ChronosScoreDetails:
    symbol: str
    interval: str
    horizon: int
    score: float
    direction: str
    latest_price: float | None = None
    median_price: float | None = None
    low_price: float | None = None
    high_price: float | None = None
    projected_return: float | None = None
    forecast_model: str | None = None
    cached: bool = False
    generated_at: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_chronos_alignment_score(
    symbol: str,
    direction: str,
    *,
    interval: str = "4h",
    horizon: int | None = None,
    database_url: str | None = None,
    max_age_minutes: int | None = None,
) -> ChronosScoreDetails:
    normalized_symbol = _storage_symbol(symbol)
    normalized_interval = str(interval or "4h").strip().lower() or "4h"
    effective_horizon = max(1, min(horizon or _default_horizon(normalized_interval), 60))
    effective_max_age = max(1, max_age_minutes or _default_cache_age_minutes(normalized_interval))
    now = datetime.now(UTC)

    try:
        ensure_time_series_schema(get_engine(database_url=database_url))
        with session_scope(database_url=database_url) as session:
            cutoff = now - timedelta(minutes=effective_max_age)
            cached = session.scalars(
                select(ChronosForecastRow)
                .where(ChronosForecastRow.symbol == normalized_symbol)
                .where(ChronosForecastRow.interval == normalized_interval)
                .where(ChronosForecastRow.horizon == effective_horizon)
                .where(ChronosForecastRow.forecast_time >= cutoff)
                .order_by(desc(ChronosForecastRow.forecast_time))
                .limit(1)
            ).first()

            if cached is None:
                cached = _persist_forecast(
                    session,
                    symbol=symbol,
                    normalized_symbol=normalized_symbol,
                    interval=normalized_interval,
                    horizon=effective_horizon,
                    generated_at=now,
                )
                was_cached = False
            else:
                was_cached = True

        return _details_from_row(cached, direction=direction, cached=was_cached)
    except Exception as exc:
        logger.warning("chronos scoring failed for %s %s: %s", normalized_symbol, normalized_interval, exc)
        return ChronosScoreDetails(
            symbol=normalized_symbol,
            interval=normalized_interval,
            horizon=effective_horizon,
            score=0.5,
            direction=str(direction or "watch"),
            cached=False,
            generated_at=now.isoformat(),
            error=str(exc),
        )


def _persist_forecast(
    session,
    *,
    symbol: str,
    normalized_symbol: str,
    interval: str,
    horizon: int,
    generated_at: datetime,
) -> ChronosForecastRow:
    response = get_forecast_projection(
        {
            "symbol": _forecast_symbol(symbol),
            "interval": interval,
            "history_limit": _history_limit(interval, horizon),
            "horizon": horizon,
        }
    )
    if not bool((response or {}).get("meta", {}).get("ok")):
        detail = (response or {}).get("data", {}).get("detail") if isinstance((response or {}).get("data"), dict) else None
        raise RuntimeError(detail or f"get_forecast_projection failed for {normalized_symbol}")

    data = response.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected Chronos projection payload for {normalized_symbol}")

    latest_price = _float_or_none(data.get("last_close"))
    median_price = _float_or_none(data.get("final_median"))
    low_price = _float_or_none(data.get("final_low"))
    high_price = _float_or_none(data.get("final_high"))
    projected_return = None
    if latest_price not in (None, 0.0) and median_price is not None:
        projected_return = (median_price - latest_price) / latest_price

    row = ChronosForecastRow(
        forecast_time=generated_at,
        symbol=normalized_symbol,
        interval=interval,
        horizon=horizon,
        latest_price=latest_price,
        median_price=median_price,
        low_price=low_price,
        high_price=high_price,
        projected_return=projected_return,
        forecast_model=str(data.get("forecast_model") or "unknown"),
        payload_json=data,
    )
    session.add(row)
    session.flush()
    return row


def _details_from_row(row: ChronosForecastRow, *, direction: str, cached: bool) -> ChronosScoreDetails:
    projected_return = row.projected_return
    score = _alignment_score(projected_return, direction)
    return ChronosScoreDetails(
        symbol=row.symbol,
        interval=row.interval,
        horizon=row.horizon,
        score=score,
        direction=str(direction or "watch"),
        latest_price=row.latest_price,
        median_price=row.median_price,
        low_price=row.low_price,
        high_price=row.high_price,
        projected_return=projected_return,
        forecast_model=row.forecast_model,
        cached=cached,
        generated_at=row.forecast_time.astimezone(UTC).isoformat(),
    )


def _alignment_score(projected_return: float | None, direction: str) -> float:
    normalized_direction = str(direction or "watch").strip().lower()
    if normalized_direction not in {"long", "short"}:
        return 0.5
    if projected_return is None:
        return 0.5

    magnitude = min(abs(projected_return) / 0.03, 1.0)
    if abs(projected_return) < 0.001:
        return 0.5

    aligned = (projected_return > 0 and normalized_direction == "long") or (
        projected_return < 0 and normalized_direction == "short"
    )
    score = (0.5 + 0.5 * magnitude) if aligned else max(0.0, 0.5 - 0.5 * magnitude)
    return round(score, 4)


def _default_horizon(interval: str) -> int:
    minutes = _interval_minutes(interval)
    if minutes is None or minutes <= 0:
        return 6
    return max(1, min(int(round((24 * 60) / minutes)), 60))


def _default_cache_age_minutes(interval: str) -> int:
    minutes = _interval_minutes(interval)
    if minutes is None or minutes <= 0:
        return 60
    return max(15, min(minutes, 240))


def _history_limit(interval: str, horizon: int) -> int:
    minutes = _interval_minutes(interval)
    if minutes is None or minutes <= 0:
        return 120
    base = max(horizon * 6, int(round((14 * 24 * 60) / minutes)))
    return max(40, min(base, 500))


def _interval_minutes(interval: str) -> int | None:
    token = str(interval or "").strip().lower()
    if not token:
        return None
    try:
        if token.endswith("m"):
            return int(token[:-1])
        if token.endswith("h"):
            return int(token[:-1]) * 60
        if token.endswith("d"):
            return int(token[:-1]) * 24 * 60
    except ValueError:
        return None
    return None


def _forecast_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    if not raw:
        return raw
    if "/" in raw:
        return raw
    for quote in _QUOTE_SUFFIXES:
        if raw.endswith(quote) and len(raw) > len(quote):
            return f"{raw[:-len(quote)]}/{quote}"
    return f"{raw}/USD"


def _storage_symbol(symbol: str) -> str:
    return "".join(ch for ch in str(symbol or "").upper() if ch.isalnum())


def _float_or_none(value) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
