"""set_kill_switch — Activate or deactivate the trading kill switch stored in Redis."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel

from backend.models import KillSwitchResult
from backend.redis_client import get_redis_client
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

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
    max_position_usd: float | None = None
    max_daily_loss_usd: float | None = None
    drawdown_limit_pct: float | None = None


_LIMITS_KEY = "hermes:risk:limits"


def set_risk_limits(payload: dict) -> dict:
    """Persist position limits and drawdown cap to Redis."""
    def _run() -> dict:
        args = validate(SetRiskLimitsInput, payload)
        redis = get_redis_client()

        existing_raw = redis.get(_LIMITS_KEY)
        existing = json.loads(existing_raw) if existing_raw else {}

        if args.max_position_usd is not None:
            existing["max_position_usd"] = args.max_position_usd
        if args.max_daily_loss_usd is not None:
            existing["max_daily_loss_usd"] = args.max_daily_loss_usd
        if args.drawdown_limit_pct is not None:
            existing["drawdown_limit_pct"] = args.drawdown_limit_pct

        redis.set(_LIMITS_KEY, json.dumps(existing))
        return envelope("set_risk_limits", [provider_ok("REDIS")], {"saved": existing})

    return run_tool("set_risk_limits", _run)
