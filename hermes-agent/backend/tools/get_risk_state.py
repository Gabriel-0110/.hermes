"""get_risk_state — Read current risk policy state: kill-switch, limits, and live drawdown."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.models import RiskState
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool

logger = logging.getLogger(__name__)

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"
_LIMITS_KEY = "hermes:risk:limits"
_PEAK_EQUITY_KEY = "hermes:risk:equity_peak"
_GLOBAL_RISK_SCOPE = "__GLOBAL__"


def _load_risk_limits_from_database() -> tuple[dict[str, object] | None, dict[str, str] | None]:
    try:
        ensure_time_series_schema(get_engine())
        with session_scope() as session:
            rows = HermesTimeSeriesRepository(session).list_risk_limits()
    except Exception as exc:
        return None, {"error": str(exc)}

    if not rows:
        return None, None

    payload: dict[str, object] = {"symbol_limits": {}}
    for row in rows:
        scope = str(row.scope or "").upper()
        if scope == _GLOBAL_RISK_SCOPE:
            if row.max_position_usd is not None:
                payload["max_position_usd"] = row.max_position_usd
            elif row.max_notional_usd is not None:
                payload["max_position_usd"] = row.max_notional_usd
            if row.max_leverage is not None:
                payload["max_leverage"] = row.max_leverage
            if row.max_daily_loss_usd is not None:
                payload["max_daily_loss_usd"] = row.max_daily_loss_usd
            if row.drawdown_limit_pct is not None:
                payload["drawdown_limit_pct"] = row.drawdown_limit_pct
            if row.carry_trade_max_equity_pct is not None:
                payload["carry_trade_max_equity_pct"] = row.carry_trade_max_equity_pct
            continue

        symbol_limits = payload.setdefault("symbol_limits", {})
        if isinstance(symbol_limits, dict):
            symbol_limits[scope] = {
                "max_notional_usd": row.max_notional_usd if row.max_notional_usd is not None else row.max_position_usd,
                "max_leverage": row.max_leverage,
            }

    return payload, None


def _parse_peak_equity(value: object) -> float | None:
    if value in (None, "", b""):
        return None
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{"):
                parsed = json.loads(stripped)
                return float(parsed.get("equity") or 0) if parsed else None
            return float(stripped)
        if isinstance(value, dict):
            return float(value.get("equity") or 0)
        return float(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def get_risk_state(_: dict | None = None) -> dict:
    def _run() -> dict:
        redis = get_redis_client()
        warnings: list[str] = []
        providers = [provider_ok("REDIS")]

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
        max_leverage: float | None = None
        max_daily_loss_usd: float | None = None
        drawdown_limit_pct: float = 10.0
        carry_trade_max_equity_pct: float = 30.0
        symbol_limits: dict[str, dict[str, float | None]] = {}
        db_limits, db_error = _load_risk_limits_from_database()
        if db_error is None:
            providers.append(provider_ok("TIMESCALEDB", "Loaded persisted risk limits from the shared database."))
        elif db_error is not None:
            providers.append(provider_error("TIMESCALEDB", db_error["error"]))
        try:
            limits: dict[str, object] = db_limits or {}
            if not limits:
                limits_raw = redis.get(_LIMITS_KEY)
                limits = json.loads(limits_raw) if limits_raw else {}

            if limits:
                max_position_usd = _float_or_none(limits.get("max_position_usd"))
                max_leverage = _float_or_none(limits.get("max_leverage"))
                max_daily_loss_usd = _float_or_none(limits.get("max_daily_loss_usd"))
                drawdown_limit_pct = float(limits.get("drawdown_limit_pct", 10.0))
                raw_symbol_limits = limits.get("symbol_limits") or {}
                if isinstance(raw_symbol_limits, dict):
                    for symbol, symbol_limit in raw_symbol_limits.items():
                        if not isinstance(symbol_limit, dict):
                            continue
                        symbol_limits[str(symbol).upper()] = {
                            "max_notional_usd": _float_or_none(symbol_limit.get("max_notional_usd") or symbol_limit.get("max_position_usd")),
                            "max_leverage": _float_or_none(symbol_limit.get("max_leverage")),
                        }
                carry_trade_max_equity_pct = float(limits.get("carry_trade_max_equity_pct", 30.0))
        except Exception as exc:
            logger.warning("Failed to read risk limits from Redis: %s", exc)
            warnings.append("limits_read_failed")

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
                peak_equity_usd = _parse_peak_equity(peak_raw) if peak_raw else current_equity_usd
                if current_equity_usd > peak_equity_usd:
                    peak_equity_usd = current_equity_usd
                    redis.set(_PEAK_EQUITY_KEY, json.dumps({"equity": peak_equity_usd}))

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
            max_leverage=_float_or_none(max_leverage),
            max_daily_loss_usd=max_daily_loss_usd,
            drawdown_limit_pct=drawdown_limit_pct,
            carry_trade_max_equity_pct=carry_trade_max_equity_pct,
            symbol_limits=symbol_limits,
            current_equity_usd=current_equity_usd,
            peak_equity_usd=peak_equity_usd,
            current_drawdown_pct=current_drawdown_pct,
            warnings=warnings,
        )
        return envelope("get_risk_state", providers, state.model_dump(mode="json"))

    return run_tool("get_risk_state", _run)


def _float_or_none(value) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
