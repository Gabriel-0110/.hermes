"""set_kill_switch — Activate or deactivate the trading kill switch stored in Redis."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.models import KillSwitchResult
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, provider_error, provider_ok, run_tool, validate

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"


class SetKillSwitchInput(BaseModel):
    active: bool
    reason: str | None = None


def set_kill_switch(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SetKillSwitchInput, payload)
        redis = get_redis_client()
        now = datetime.now(timezone.utc).isoformat()

        state = {
            "active": args.active,
            "reason": args.reason or ("kill switch activated" if args.active else "kill switch cleared"),
            "set_at": now,
        }
        redis.set(_KILL_SWITCH_KEY, json.dumps(state))

        result = KillSwitchResult(
            success=True,
            active=args.active,
            reason=state["reason"],
            set_at=now,
        )
        return envelope("set_kill_switch", [provider_ok("REDIS")], result.model_dump(mode="json"))

    return run_tool("set_kill_switch", _run)


class SetRiskLimitsInput(BaseModel):
    symbol: str | None = None
    max_position_usd: float | None = None
    max_notional_usd: float | None = None
    max_leverage: float | None = None
    max_daily_loss_usd: float | None = None
    drawdown_limit_pct: float | None = None
    carry_trade_max_equity_pct: float | None = None


_LIMITS_KEY = "hermes:risk:limits"
_GLOBAL_SCOPE = "global"


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip().upper()
    return normalized or None


def _limit_updates(args: SetRiskLimitsInput) -> dict[str, float]:
    updates: dict[str, float] = {}
    for key in (
        "max_position_usd",
        "max_notional_usd",
        "max_leverage",
        "max_daily_loss_usd",
        "drawdown_limit_pct",
        "carry_trade_max_equity_pct",
    ):
        value = getattr(args, key)
        if value is not None:
            updates[key] = value
    return updates


def _load_json_object(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    loaded = json.loads(raw)
    return loaded if isinstance(loaded, dict) else {}


def set_risk_limits(payload: dict) -> dict:
    """Persist risk limits to Redis and the shared DB."""
    def _run() -> dict:
        args = validate(SetRiskLimitsInput, payload)
        redis = get_redis_client()
        symbol = _normalize_symbol(args.symbol)
        scope = f"symbol:{symbol}" if symbol else _GLOBAL_SCOPE
        updates = _limit_updates(args)

        existing_raw = redis.get(_LIMITS_KEY)
        existing = _load_json_object(existing_raw)

        if symbol:
            symbol_limits = existing.setdefault("symbol_limits", {})
            if not isinstance(symbol_limits, dict):
                symbol_limits = {}
                existing["symbol_limits"] = symbol_limits
            saved = symbol_limits.setdefault(symbol, {})
            if not isinstance(saved, dict):
                saved = {}
                symbol_limits[symbol] = saved
            saved.update(updates)
        else:
            existing.update(updates)
            saved = existing

        redis.set(_LIMITS_KEY, json.dumps(existing))

        database_persisted = False
        providers = [provider_ok("REDIS")]
        warnings: list[str] = []
        try:
            ensure_time_series_schema(get_engine())
            with session_scope() as session:
                HermesTimeSeriesRepository(session).upsert_risk_limit(scope=scope, **updates)
            database_persisted = True
            providers.append(provider_ok("DB"))
        except Exception as exc:
            warnings.append("database_persist_failed")
            providers.append(provider_error("DB", str(exc)))

        return envelope(
            "set_risk_limits",
            providers,
            {
                "saved": saved,
                "scope": scope,
                "symbol": symbol,
                "database_persisted": database_persisted,
            },
            warnings=warnings,
        )

    return run_tool("set_risk_limits", _run)
