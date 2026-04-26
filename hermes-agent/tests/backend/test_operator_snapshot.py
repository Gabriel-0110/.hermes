"""Tests for operator balance snapshot import and persistence."""

from __future__ import annotations

import json
from pathlib import Path

from backend.operator_snapshot import import_operator_snapshot, validate_operator_snapshot, import_from_file


SAMPLE_SNAPSHOT = {
    "as_of_utc": "2026-04-25T00:00:00Z",
    "exchange": "bitmart",
    "spot_balances": [
        {"asset": "USDT", "free": 500.0, "locked": 0.0},
    ],
    "futures_balances": [
        {"asset": "USDT", "wallet": 1000.0, "available": 800.0, "margin_used": 200.0, "unrealized_pnl": 50.0},
    ],
    "open_positions": [],
    "pnl": {
        "realized_24h_usdt": 12.5,
        "realized_7d_usdt": 80.0,
        "realized_30d_usdt": 320.0,
        "unrealized_total_usdt": 50.0,
    },
    "capital": {
        "available_usdt": 800.0,
        "invested_usdt": 700.0,
        "reserved_usdt": 0.0,
    },
    "loss_limits": {
        "daily_max_loss_usdt": 100.0,
        "weekly_max_loss_usdt": 300.0,
        "max_drawdown_pct_from_hwm": 5.0,
    },
    "notes": "Test snapshot",
}


def test_validate_operator_snapshot_accepts_valid_input():
    errors = validate_operator_snapshot(SAMPLE_SNAPSHOT)
    assert errors == []


def test_validate_operator_snapshot_rejects_missing_exchange():
    data = {k: v for k, v in SAMPLE_SNAPSHOT.items() if k != "exchange"}
    errors = validate_operator_snapshot(data)
    assert any("exchange" in e for e in errors)


def test_validate_operator_snapshot_rejects_missing_as_of():
    data = {k: v for k, v in SAMPLE_SNAPSHOT.items() if k != "as_of_utc"}
    errors = validate_operator_snapshot(data)
    assert any("as_of_utc" in e for e in errors)


def test_import_operator_snapshot_persists_and_returns_totals():
    result = import_operator_snapshot(SAMPLE_SNAPSHOT, reconcile=False)

    assert result["ok"] is True
    assert result["exchange"] == "bitmart"
    assert result["snapshot_id"].startswith("snap_")
    assert result["totals"]["total_equity_usd"] == 800.0 + 700.0 + 50.0
    assert result["totals"]["available_usd"] == 800.0
    assert result["totals"]["invested_usd"] == 700.0
    assert result["totals"]["unrealized_pnl_usd"] == 50.0
    assert result["divergence"] is None


def test_import_operator_snapshot_rejects_invalid_data():
    result = import_operator_snapshot({"notes": "missing required fields"}, reconcile=False)

    assert result["ok"] is False
    assert len(result["errors"]) >= 2


def test_import_from_file_reads_and_persists(tmp_path):
    snapshot_file = tmp_path / "snapshot.json"
    snapshot_file.write_text(json.dumps(SAMPLE_SNAPSHOT), encoding="utf-8")

    result = import_from_file(str(snapshot_file))

    assert result["ok"] is True
    assert result["exchange"] == "bitmart"
