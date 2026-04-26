"""Exit management — trailing stops, time stops, and adverse-excursion stops.

Periodic worker that evaluates open positions against their exit parameters
and triggers exits or bracket modifications when thresholds are breached.
All exit triggers emit observability events prefixed with ``exit_trigger_``.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_MIN_MODIFICATION_BPS = 10.0


class PositionExitState(BaseModel):
    """Tracks per-position state for exit management."""

    symbol: str
    side: str
    entry_price: float
    opened_at: str
    peak_price: float | None = None
    trough_price: float | None = None
    trailing_stop_distance_bps: float | None = None
    time_stop_minutes: float | None = None
    max_adverse_excursion_bps: float | None = None
    current_sl_trigger: float | None = None
    bracket_order_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExitTrigger(BaseModel):
    """Result of evaluating exit conditions for a position."""

    symbol: str
    trigger_type: str  # trailing_stop, time_stop, max_adverse_excursion
    should_exit: bool = False
    should_modify_bracket: bool = False
    new_trigger_price: float | None = None
    reason: str = ""
    detail: dict[str, Any] = Field(default_factory=dict)


def update_peak_trough(
    state: PositionExitState,
    mark_price: float,
) -> PositionExitState:
    if state.side == "buy":
        if state.peak_price is None or mark_price > state.peak_price:
            state.peak_price = mark_price
        if state.trough_price is None or mark_price < state.trough_price:
            state.trough_price = mark_price
    else:
        if state.trough_price is None or mark_price < state.trough_price:
            state.trough_price = mark_price
        if state.peak_price is None or mark_price > state.peak_price:
            state.peak_price = mark_price
    return state


def evaluate_trailing_stop(
    state: PositionExitState,
    mark_price: float,
) -> ExitTrigger:
    if state.trailing_stop_distance_bps is None:
        return ExitTrigger(symbol=state.symbol, trigger_type="trailing_stop")

    state = update_peak_trough(state, mark_price)

    if state.side == "buy":
        if state.peak_price is None:
            return ExitTrigger(symbol=state.symbol, trigger_type="trailing_stop")
        new_sl = state.peak_price * (1 - state.trailing_stop_distance_bps / 10_000)
        should_exit = mark_price <= new_sl
        should_modify = False
        if not should_exit and state.current_sl_trigger is not None:
            drift_bps = abs(new_sl - state.current_sl_trigger) / state.entry_price * 10_000
            should_modify = new_sl > state.current_sl_trigger and drift_bps > _MIN_MODIFICATION_BPS
        elif not should_exit and state.current_sl_trigger is None:
            should_modify = True
    else:
        if state.trough_price is None:
            return ExitTrigger(symbol=state.symbol, trigger_type="trailing_stop")
        new_sl = state.trough_price * (1 + state.trailing_stop_distance_bps / 10_000)
        should_exit = mark_price >= new_sl
        should_modify = False
        if not should_exit and state.current_sl_trigger is not None:
            drift_bps = abs(new_sl - state.current_sl_trigger) / state.entry_price * 10_000
            should_modify = new_sl < state.current_sl_trigger and drift_bps > _MIN_MODIFICATION_BPS
        elif not should_exit and state.current_sl_trigger is None:
            should_modify = True

    return ExitTrigger(
        symbol=state.symbol,
        trigger_type="trailing_stop",
        should_exit=should_exit,
        should_modify_bracket=should_modify,
        new_trigger_price=new_sl,
        reason=f"trailing_stop at {new_sl:.2f}" if should_exit else "",
        detail={
            "peak_price": state.peak_price,
            "trough_price": state.trough_price,
            "new_sl": new_sl,
            "current_sl_trigger": state.current_sl_trigger,
            "mark_price": mark_price,
        },
    )


def evaluate_time_stop(
    state: PositionExitState,
    now: datetime | None = None,
) -> ExitTrigger:
    if state.time_stop_minutes is None:
        return ExitTrigger(symbol=state.symbol, trigger_type="time_stop")

    now = now or datetime.now(UTC)
    try:
        opened = datetime.fromisoformat(state.opened_at)
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return ExitTrigger(symbol=state.symbol, trigger_type="time_stop")

    elapsed_minutes = (now - opened).total_seconds() / 60.0
    should_exit = elapsed_minutes > state.time_stop_minutes

    return ExitTrigger(
        symbol=state.symbol,
        trigger_type="time_stop",
        should_exit=should_exit,
        reason=f"time_stop after {elapsed_minutes:.1f}m (limit {state.time_stop_minutes}m)" if should_exit else "",
        detail={
            "opened_at": state.opened_at,
            "elapsed_minutes": round(elapsed_minutes, 2),
            "time_stop_minutes": state.time_stop_minutes,
        },
    )


def evaluate_adverse_excursion(
    state: PositionExitState,
    mark_price: float,
) -> ExitTrigger:
    if state.max_adverse_excursion_bps is None:
        return ExitTrigger(symbol=state.symbol, trigger_type="max_adverse_excursion")

    if state.entry_price <= 0:
        return ExitTrigger(symbol=state.symbol, trigger_type="max_adverse_excursion")

    if state.side == "buy":
        excursion_bps = (state.entry_price - mark_price) / state.entry_price * 10_000
    else:
        excursion_bps = (mark_price - state.entry_price) / state.entry_price * 10_000

    should_exit = excursion_bps > state.max_adverse_excursion_bps

    return ExitTrigger(
        symbol=state.symbol,
        trigger_type="max_adverse_excursion",
        should_exit=should_exit,
        reason=f"adverse excursion {excursion_bps:.1f} bps > limit {state.max_adverse_excursion_bps} bps" if should_exit else "",
        detail={
            "entry_price": state.entry_price,
            "mark_price": mark_price,
            "excursion_bps": round(excursion_bps, 2),
            "max_adverse_excursion_bps": state.max_adverse_excursion_bps,
            "side": state.side,
        },
    )


def evaluate_all_exits(
    state: PositionExitState,
    mark_price: float,
    now: datetime | None = None,
) -> list[ExitTrigger]:
    triggers: list[ExitTrigger] = []

    trailing = evaluate_trailing_stop(state, mark_price)
    if trailing.should_exit or trailing.should_modify_bracket:
        triggers.append(trailing)

    time_trigger = evaluate_time_stop(state, now)
    if time_trigger.should_exit:
        triggers.append(time_trigger)

    adverse = evaluate_adverse_excursion(state, mark_price)
    if adverse.should_exit:
        triggers.append(adverse)

    return triggers


def record_exit_trigger_event(
    trigger: ExitTrigger,
    *,
    observability_service: Any | None = None,
) -> None:
    if observability_service is None:
        try:
            from backend.observability.service import get_observability_service
            observability_service = get_observability_service()
        except Exception:
            return

    event_type = f"exit_trigger_{trigger.trigger_type}"
    status = "triggered" if trigger.should_exit else "modification_pending"

    try:
        observability_service.record_execution_event(
            event_type=event_type,
            status=status,
            symbol=trigger.symbol,
            payload={
                "trigger_type": trigger.trigger_type,
                "should_exit": trigger.should_exit,
                "should_modify_bracket": trigger.should_modify_bracket,
                "new_trigger_price": trigger.new_trigger_price,
                "reason": trigger.reason,
                **trigger.detail,
            },
        )
    except Exception as exc:
        logger.debug("Failed to record exit trigger event: %s", exc)
