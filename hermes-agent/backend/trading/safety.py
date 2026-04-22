"""Centralized execution safety guards for trading order placement."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from backend.integrations.execution.mode import current_trading_mode, live_trading_blockers
from backend.redis_client import get_redis_client

_KILL_SWITCH_KEY = "hermes:risk:kill_switch"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class ExecutionSafetyDecision:
    execution_mode: str
    blockers: list[str] = field(default_factory=list)
    approval_required: bool = False
    kill_switch_active: bool = False
    kill_switch_reason: str | None = None

    @property
    def live_allowed(self) -> bool:
        return self.execution_mode == "live" and not self.blockers and not self.approval_required


def get_kill_switch_state() -> dict[str, object]:
    try:
        raw = get_redis_client().get(_KILL_SWITCH_KEY)
        if not raw:
            return {"active": False, "reason": None}
        payload = json.loads(raw)
        return {
            "active": bool(payload.get("active")),
            "reason": payload.get("reason"),
        }
    except Exception:
        return {"active": False, "reason": None}


def approval_required() -> bool:
    return _truthy(os.getenv("HERMES_REQUIRE_APPROVAL"))


def evaluate_execution_safety(*, approval_id: str | None = None) -> ExecutionSafetyDecision:
    mode = current_trading_mode()
    blockers = list(live_trading_blockers()) if mode == "live" else []

    kill_switch = get_kill_switch_state()
    kill_switch_active = bool(kill_switch.get("active"))
    kill_switch_reason = str(kill_switch.get("reason") or "") or None
    if kill_switch_active:
        blockers.append(
            "Kill switch is active."
            + (f" Reason: {kill_switch_reason}" if kill_switch_reason else "")
        )

    requires_approval = mode == "live" and approval_required() and not approval_id

    return ExecutionSafetyDecision(
        execution_mode="live" if mode == "live" else "paper",
        blockers=blockers,
        approval_required=requires_approval,
        kill_switch_active=kill_switch_active,
        kill_switch_reason=kill_switch_reason,
    )
