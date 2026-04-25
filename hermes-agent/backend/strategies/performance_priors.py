"""Rolling Bayesian confidence priors for trading strategies."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow
from backend.db.session import get_engine

logger = logging.getLogger(__name__)

_CACHE_LOCK = Lock()
_PRIOR_CACHE: dict[tuple[str, str], tuple[float, "StrategyConfidencePrior"]] = {}


@dataclass(frozen=True, slots=True)
class StrategyConfidencePrior:
    strategy_name: str
    alpha: float
    beta: float
    posterior_mean: float
    multiplier: float
    resolved_count: int
    wins: int
    losses: int
    as_of: str | None = None


def strategy_prior_from_pnls(
    strategy_name: str,
    pnl_values: list[float],
    *,
    base_alpha: float = 2.0,
    base_beta: float = 2.0,
    as_of: str | None = None,
) -> StrategyConfidencePrior:
    wins = sum(1 for pnl in pnl_values if pnl > 0)
    losses = sum(1 for pnl in pnl_values if pnl <= 0)
    alpha = base_alpha + wins
    beta = base_beta + losses
    posterior_mean = alpha / (alpha + beta)
    multiplier = 0.75 + (posterior_mean * 0.5)
    return StrategyConfidencePrior(
        strategy_name=strategy_name,
        alpha=round(alpha, 4),
        beta=round(beta, 4),
        posterior_mean=round(posterior_mean, 4),
        multiplier=round(multiplier, 4),
        resolved_count=len(pnl_values),
        wins=wins,
        losses=losses,
        as_of=as_of,
    )


def get_strategy_prior(
    strategy_name: str,
    *,
    database_url: str | None = None,
    window: int = 200,
    ttl_seconds: int = 300,
) -> StrategyConfidencePrior:
    normalized = str(strategy_name or "").strip().lower()
    cache_key = (normalized, database_url or "")
    now = time.monotonic()

    with _CACHE_LOCK:
        cached = _PRIOR_CACHE.get(cache_key)
        if cached is not None and cached[0] > now:
            return cached[1]

    neutral = strategy_prior_from_pnls(normalized or "unknown", [])
    if not normalized:
        return neutral

    try:
        ensure_time_series_schema(get_engine(database_url=database_url))
        with session_scope(database_url=database_url) as session:
            statement = (
                select(StrategyEvaluationRow)
                .where(StrategyEvaluationRow.strategy_name == normalized)
                .where(StrategyEvaluationRow.resolved_at.is_not(None))
                .where(StrategyEvaluationRow.pnl_pct.is_not(None))
                .order_by(desc(StrategyEvaluationRow.resolved_at))
                .limit(max(1, min(window, 1000)))
            )
            rows = list(session.scalars(statement))
    except Exception as exc:
        logger.debug("strategy prior lookup failed for %s: %s", normalized, exc)
        return neutral

    pnl_values = [float(row.pnl_pct) for row in rows if row.pnl_pct is not None]
    as_of = None
    if rows and rows[0].resolved_at is not None:
        as_of = rows[0].resolved_at.astimezone(timezone.utc).isoformat()
    prior = strategy_prior_from_pnls(normalized, pnl_values, as_of=as_of)

    with _CACHE_LOCK:
        _PRIOR_CACHE[cache_key] = (now + max(ttl_seconds, 1), prior)

    return prior


def scale_confidence_by_prior(
    strategy_name: str,
    confidence: float,
    *,
    database_url: str | None = None,
) -> tuple[float, StrategyConfidencePrior]:
    prior = get_strategy_prior(strategy_name, database_url=database_url)
    scaled = round(min(max(float(confidence) * prior.multiplier, 0.01), 0.99), 2)
    return scaled, prior


def clear_strategy_prior_cache(strategy_name: str | None = None) -> None:
    normalized = str(strategy_name or "").strip().lower()
    with _CACHE_LOCK:
        if not normalized:
            _PRIOR_CACHE.clear()
            return
        for key in list(_PRIOR_CACHE):
            if key[0] == normalized:
                _PRIOR_CACHE.pop(key, None)