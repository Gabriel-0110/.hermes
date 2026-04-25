from __future__ import annotations

from backend.trading.sizing import vol_target_size


def test_vol_target_size_decreases_as_atr_rises() -> None:
    low_vol = vol_target_size("BTCUSDT", 50.0, atr=250.0, price=50_000.0, holding_period_hours=4.0)
    high_vol = vol_target_size("BTCUSDT", 50.0, atr=750.0, price=50_000.0, holding_period_hours=4.0)

    assert low_vol > high_vol


def test_vol_target_size_respects_floor_when_atr_missing() -> None:
    size = vol_target_size("ETHUSDT", 40.0, atr=None, price=2_500.0, holding_period_hours=1.0)

    assert size == 40.0