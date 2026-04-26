"""Tests for exit management — trailing stops, time stops, adverse excursion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.trading.exit_manager import (
    ExitTrigger,
    PositionExitState,
    _MIN_MODIFICATION_BPS,
    evaluate_adverse_excursion,
    evaluate_all_exits,
    evaluate_time_stop,
    evaluate_trailing_stop,
    record_exit_trigger_event,
    update_peak_trough,
)


# ---------------------------------------------------------------------------
# Peak/trough tracking
# ---------------------------------------------------------------------------


def test_update_peak_trough_long_new_high() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z", peak_price=66000.0, trough_price=64000.0,
    )
    state = update_peak_trough(state, 67000.0)
    assert state.peak_price == 67000.0
    assert state.trough_price == 64000.0


def test_update_peak_trough_long_new_low() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z", peak_price=66000.0, trough_price=64000.0,
    )
    state = update_peak_trough(state, 63000.0)
    assert state.peak_price == 66000.0
    assert state.trough_price == 63000.0


def test_update_peak_trough_short_new_low() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="sell", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z", peak_price=66000.0, trough_price=64000.0,
    )
    state = update_peak_trough(state, 63000.0)
    assert state.trough_price == 63000.0


def test_update_peak_trough_initializes_none() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
    )
    state = update_peak_trough(state, 66000.0)
    assert state.peak_price == 66000.0
    assert state.trough_price == 66000.0


# ---------------------------------------------------------------------------
# Trailing stop
# ---------------------------------------------------------------------------


def test_trailing_stop_ratchets_up_only_for_longs() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        peak_price=66000.0,
        current_sl_trigger=65200.0,
    )
    trigger = evaluate_trailing_stop(state, mark_price=66500.0)

    expected_sl = 66500.0 * (1 - 100.0 / 10_000)
    assert not trigger.should_exit
    assert trigger.should_modify_bracket
    assert trigger.new_trigger_price is not None
    assert trigger.new_trigger_price > state.current_sl_trigger


def test_trailing_stop_fires_when_price_drops_below() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        peak_price=67000.0,
    )
    new_sl = 67000.0 * (1 - 100.0 / 10_000)
    trigger = evaluate_trailing_stop(state, mark_price=new_sl - 1.0)

    assert trigger.should_exit
    assert trigger.trigger_type == "trailing_stop"


def test_trailing_stop_no_modify_when_drift_too_small() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        peak_price=65010.0,
        current_sl_trigger=65000.0 * (1 - 100.0 / 10_000),
    )
    trigger = evaluate_trailing_stop(state, mark_price=65010.0)

    assert not trigger.should_exit
    assert not trigger.should_modify_bracket


def test_trailing_stop_short_ratchets_down() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="sell", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        trough_price=63000.0,
        current_sl_trigger=64000.0,
    )
    trigger = evaluate_trailing_stop(state, mark_price=62500.0)

    expected_sl = 62500.0 * (1 + 100.0 / 10_000)
    assert not trigger.should_exit
    assert trigger.should_modify_bracket
    assert trigger.new_trigger_price is not None
    assert trigger.new_trigger_price < state.current_sl_trigger


def test_trailing_stop_short_fires() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="sell", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        trough_price=63000.0,
    )
    new_sl = 63000.0 * (1 + 100.0 / 10_000)
    trigger = evaluate_trailing_stop(state, mark_price=new_sl + 1.0)

    assert trigger.should_exit


def test_trailing_stop_no_config_returns_no_action() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
    )
    trigger = evaluate_trailing_stop(state, mark_price=66000.0)

    assert not trigger.should_exit
    assert not trigger.should_modify_bracket


def test_trailing_stop_first_tick_sets_modify() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        peak_price=66000.0,
    )
    trigger = evaluate_trailing_stop(state, mark_price=66000.0)

    assert not trigger.should_exit
    assert trigger.should_modify_bracket
    assert trigger.new_trigger_price is not None


# ---------------------------------------------------------------------------
# Time stop
# ---------------------------------------------------------------------------


def test_time_stop_fires_after_limit() -> None:
    opened = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at=opened.isoformat(),
        time_stop_minutes=60.0,
    )
    now = opened + timedelta(minutes=61)
    trigger = evaluate_time_stop(state, now=now)

    assert trigger.should_exit
    assert trigger.trigger_type == "time_stop"
    assert "61" in trigger.reason


def test_time_stop_does_not_fire_before_limit() -> None:
    opened = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at=opened.isoformat(),
        time_stop_minutes=60.0,
    )
    now = opened + timedelta(minutes=30)
    trigger = evaluate_time_stop(state, now=now)

    assert not trigger.should_exit


def test_time_stop_no_config() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
    )
    trigger = evaluate_time_stop(state)
    assert not trigger.should_exit


# ---------------------------------------------------------------------------
# Adverse excursion
# ---------------------------------------------------------------------------


def test_adverse_excursion_fires_for_long() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        max_adverse_excursion_bps=200.0,
    )
    drop_price = 65000.0 * (1 - 201.0 / 10_000)
    trigger = evaluate_adverse_excursion(state, mark_price=drop_price)

    assert trigger.should_exit
    assert trigger.trigger_type == "max_adverse_excursion"


def test_adverse_excursion_does_not_fire_within_limit() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        max_adverse_excursion_bps=200.0,
    )
    safe_price = 65000.0 * (1 - 100.0 / 10_000)
    trigger = evaluate_adverse_excursion(state, mark_price=safe_price)

    assert not trigger.should_exit


def test_adverse_excursion_fires_for_short() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="sell", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        max_adverse_excursion_bps=200.0,
    )
    rise_price = 65000.0 * (1 + 201.0 / 10_000)
    trigger = evaluate_adverse_excursion(state, mark_price=rise_price)

    assert trigger.should_exit


def test_adverse_excursion_no_config() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
    )
    trigger = evaluate_adverse_excursion(state, mark_price=60000.0)
    assert not trigger.should_exit


# ---------------------------------------------------------------------------
# Combined evaluation
# ---------------------------------------------------------------------------


def test_evaluate_all_exits_returns_multiple_triggers() -> None:
    opened = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at=opened.isoformat(),
        trailing_stop_distance_bps=100.0,
        time_stop_minutes=60.0,
        max_adverse_excursion_bps=200.0,
        peak_price=67000.0,
    )
    mark = 65000.0 * (1 - 201.0 / 10_000)
    now = opened + timedelta(minutes=61)

    triggers = evaluate_all_exits(state, mark_price=mark, now=now)

    trigger_types = {t.trigger_type for t in triggers}
    assert "trailing_stop" in trigger_types
    assert "time_stop" in trigger_types
    assert "max_adverse_excursion" in trigger_types


def test_evaluate_all_exits_empty_when_nothing_triggered() -> None:
    opened = datetime(2026, 4, 26, 10, 0, tzinfo=UTC)
    peak = 65100.0
    current_sl = peak * (1 - 100.0 / 10_000)
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at=opened.isoformat(),
        trailing_stop_distance_bps=100.0,
        time_stop_minutes=120.0,
        max_adverse_excursion_bps=500.0,
        peak_price=peak,
        current_sl_trigger=current_sl,
    )
    now = opened + timedelta(minutes=10)

    triggers = evaluate_all_exits(state, mark_price=65050.0, now=now)

    assert len(triggers) == 0


def test_evaluate_all_exits_trailing_modify_only() -> None:
    state = PositionExitState(
        symbol="BTCUSDT", side="buy", entry_price=65000.0,
        opened_at="2026-04-26T10:00:00Z",
        trailing_stop_distance_bps=100.0,
        peak_price=67000.0,
    )
    triggers = evaluate_all_exits(state, mark_price=67500.0)

    assert len(triggers) == 1
    assert triggers[0].trigger_type == "trailing_stop"
    assert not triggers[0].should_exit
    assert triggers[0].should_modify_bracket


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------


def test_record_exit_trigger_event_calls_observability() -> None:
    recorded: list[dict[str, Any]] = []

    class FakeObs:
        def record_execution_event(self, **kwargs: Any) -> dict[str, Any]:
            recorded.append(kwargs)
            return {"id": "evt-1"}

    trigger = ExitTrigger(
        symbol="BTCUSDT",
        trigger_type="trailing_stop",
        should_exit=True,
        reason="trailing stop hit",
    )
    record_exit_trigger_event(trigger, observability_service=FakeObs())

    assert len(recorded) == 1
    assert recorded[0]["event_type"] == "exit_trigger_trailing_stop"
    assert recorded[0]["status"] == "triggered"
    assert recorded[0]["symbol"] == "BTCUSDT"


def test_record_exit_trigger_event_modification_pending() -> None:
    recorded: list[dict[str, Any]] = []

    class FakeObs:
        def record_execution_event(self, **kwargs: Any) -> dict[str, Any]:
            recorded.append(kwargs)
            return {"id": "evt-2"}

    trigger = ExitTrigger(
        symbol="BTCUSDT",
        trigger_type="trailing_stop",
        should_modify_bracket=True,
        new_trigger_price=66340.0,
    )
    record_exit_trigger_event(trigger, observability_service=FakeObs())

    assert recorded[0]["status"] == "modification_pending"


def test_record_exit_trigger_event_tolerates_observability_error() -> None:
    class BrokenObs:
        def record_execution_event(self, **kwargs: Any) -> None:
            raise RuntimeError("observability down")

    trigger = ExitTrigger(symbol="BTCUSDT", trigger_type="time_stop", should_exit=True)
    record_exit_trigger_event(trigger, observability_service=BrokenObs())


# ---------------------------------------------------------------------------
# Model field tests
# ---------------------------------------------------------------------------


def test_execution_request_has_exit_fields() -> None:
    from backend.trading.models import ExecutionRequest

    req = ExecutionRequest(
        symbol="BTCUSDT",
        side="buy",
        amount=1.0,
        trailing_stop_distance_bps=150.0,
        time_stop_minutes=120.0,
        max_adverse_excursion_bps=300.0,
    )
    assert req.trailing_stop_distance_bps == 150.0
    assert req.time_stop_minutes == 120.0
    assert req.max_adverse_excursion_bps == 300.0


def test_execution_result_has_bracket_modifications() -> None:
    from backend.trading.models import ExecutionResult

    result = ExecutionResult(
        symbol="BTCUSDT",
        status="filled",
        success=True,
        execution_mode="live",
        bracket_modifications=[
            {"order_id": "tp-001", "status": "modified", "new_trigger_price": "68000.0"},
        ],
    )
    assert len(result.bracket_modifications) == 1
    assert result.bracket_modifications[0]["status"] == "modified"


def test_execution_result_bracket_modifications_default_empty() -> None:
    from backend.trading.models import ExecutionResult

    result = ExecutionResult(
        symbol="BTCUSDT",
        status="paper_filled",
        success=True,
        execution_mode="paper",
    )
    assert result.bracket_modifications == []
