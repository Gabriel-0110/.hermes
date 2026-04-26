"""get_risk_state — Read current risk policy state: kill-switch, limits, and live drawdown."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.models import RiskLimitRow
from backend.db.session import get_engine
from backend.models import RiskState
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, provider_ok, run_tool

logger = logging.getLogger(__name__)

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"
_LIMITS_KEY = "hermes:risk:limits"
_PEAK_EQUITY_KEY = "hermes:risk:equity_peak"
_GLOBAL_SCOPE = "global"


def _load_json_object(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def _row_limits(row: RiskLimitRow) -> dict[str, float | None]:
    return {
        "max_position_usd": row.max_position_usd,
        "max_notional_usd": row.max_notional_usd,
        "max_leverage": row.max_leverage,
        "max_daily_loss_usd": row.max_daily_loss_usd,
        "drawdown_limit_pct": row.drawdown_limit_pct,
        "carry_trade_max_equity_pct": row.carry_trade_max_equity_pct,
    }


def _apply_global_limits(
    values: dict[str, float | None],
    *,
    max_position_usd: float | None,
    max_daily_loss_usd: float | None,
    drawdown_limit_pct: float,
    carry_trade_max_equity_pct: float,
) -> tuple[float | None, float | None, float, float]:
    if values.get("max_position_usd") is not None:
        max_position_usd = values["max_position_usd"]
    if values.get("max_daily_loss_usd") is not None:
        max_daily_loss_usd = values["max_daily_loss_usd"]
    if values.get("drawdown_limit_pct") is not None:
        drawdown_limit_pct = float(values["drawdown_limit_pct"])
    if values.get("carry_trade_max_equity_pct") is not None:
        carry_trade_max_equity_pct = float(values["carry_trade_max_equity_pct"])
    return max_position_usd, max_daily_loss_usd, drawdown_limit_pct, carry_trade_max_equity_pct


def get_risk_state(_: dict | None = None) -> dict:
    def _run() -> dict:
        redis = get_redis_client()
        warnings: list[str] = []

        # --- Kill switch ---
        kill_switch_active = False
        kill_switch_reason: str | None = None
        kill_switch_set_at: str | None = None
        try:
            ks_raw = redis.get(_KILL_SWITCH_KEY)
            if ks_raw:
                ks = json.loads(ks_raw)
                kill_switch_active = bool(ks.get("active", False))
                kill_switch_reason = ks.get("reason")
                kill_switch_set_at = ks.get("set_at")
        except Exception as exc:
            logger.warning("Failed to read kill switch from Redis: %s", exc)
            warnings.append("kill_switch_read_failed")

        # --- Risk limits ---
        max_position_usd: float | None = None
        max_daily_loss_usd: float | None = None
        drawdown_limit_pct: float = 10.0
        carry_trade_max_equity_pct: float = 30.0
        symbol_limits: dict[str, dict[str, Any]] = {}
        try:
            limits_raw = redis.get(_LIMITS_KEY)
            limits = _load_json_object(limits_raw)
            max_position_usd = limits.get("max_position_usd")
            max_daily_loss_usd = limits.get("max_daily_loss_usd")
            drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 10.0))
            carry_trade_max_equity_pct = float(limits.get("carry_trade_max_equity_pct", 30.0))
            redis_symbol_limits = limits.get("symbol_limits", {})
            if isinstance(redis_symbol_limits, dict):
                symbol_limits = {
                    str(symbol).upper(): values
                    for symbol, values in redis_symbol_limits.items()
                    if isinstance(values, dict)
                }
        except Exception as exc:
            logger.warning("Failed to read risk limits from Redis: %s", exc)
            warnings.append("limits_read_failed")

        try:
            ensure_time_series_schema(get_engine())
            with session_scope() as session:
                db_limits = HermesTimeSeriesRepository(session).list_risk_limits()
            for row in db_limits:
                values = _row_limits(row)
                if row.scope == _GLOBAL_SCOPE:
                    (
                        max_position_usd,
                        max_daily_loss_usd,
                        drawdown_limit_pct,
                        carry_trade_max_equity_pct,
                    ) = _apply_global_limits(
                        values,
                        max_position_usd=max_position_usd,
                        max_daily_loss_usd=max_daily_loss_usd,
                        drawdown_limit_pct=drawdown_limit_pct,
                        carry_trade_max_equity_pct=carry_trade_max_equity_pct,
                    )
                elif row.scope.startswith("symbol:"):
                    symbol = row.scope.removeprefix("symbol:").upper()
                    if symbol:
                        symbol_limits[symbol] = values
        except Exception as exc:
            logger.warning("Failed to read risk limits from DB: %s", exc)
            warnings.append("database_limits_read_failed")

        # --- Drawdown from portfolio state ---
        current_equity_usd: float | None = None
        peak_equity_usd: float | None = None
        current_drawdown_pct: float | None = None
        try:
            from backend.tools.get_portfolio_state import get_portfolio_state

            portfolio = get_portfolio_state({})
            current_equity_usd = portfolio.get("data", {}).get("total_equity_usd")

            if current_equity_usd is not None:
                # Update peak if higher than recorded
                peak_raw = redis.get(_PEAK_EQUITY_KEY)
                peak_equity_usd = float(peak_raw) if peak_raw else current_equity_usd
                if current_equity_usd > peak_equity_usd:
                    peak_equity_usd = current_equity_usd
                    redis.set(_PEAK_EQUITY_KEY, str(peak_equity_usd))

                if peak_equity_usd and peak_equity_usd > 0:
                    current_drawdown_pct = round((peak_equity_usd - current_equity_usd) / peak_equity_usd * 100, 2)

                if current_drawdown_pct is not None and current_drawdown_pct >= drawdown_limit_pct:
                    warnings.append(f"drawdown_limit_breached: {current_drawdown_pct:.1f}% >= {drawdown_limit_pct:.1f}%")
        except Exception as exc:
            logger.warning("Failed to compute drawdown: %s", exc)
            warnings.append("drawdown_compute_failed")

        state = RiskState(
            kill_switch_active=kill_switch_active,
            kill_switch_reason=kill_switch_reason,
            kill_switch_set_at=kill_switch_set_at,
            max_position_usd=max_position_usd,
            max_daily_loss_usd=max_daily_loss_usd,
            drawdown_limit_pct=drawdown_limit_pct,
            carry_trade_max_equity_pct=carry_trade_max_equity_pct,
            current_equity_usd=current_equity_usd,
            peak_equity_usd=peak_equity_usd,
            current_drawdown_pct=current_drawdown_pct,
            warnings=warnings,
        )
        data = state.model_dump(mode="json")
        data["symbol_limits"] = symbol_limits
        return envelope("get_risk_state", [provider_ok("REDIS")], data)

    return run_tool("get_risk_state", _run)
