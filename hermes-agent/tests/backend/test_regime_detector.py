"""Tests for market regime detection, strategy gating, and policy integration."""

from __future__ import annotations

import math
from typing import Any

import pytest

from backend.regime.detector import (
    _atr_values,
    _linreg_slope,
    _log_closes,
    _vol_of_vol,
    cache_regime,
    detect_regime,
    get_cached_regime,
    get_current_regime,
)
from backend.regime.models import MarketRegime, RegimeSnapshot
from backend.strategies.registry import STRATEGY_REGISTRY, resolve_strategy_name
from backend.trading.models import RiskRejectionReason, TradeProposal
from backend.trading.policy_engine import evaluate_trade_proposal


# ---------------------------------------------------------------------------
# Synthetic candle fixtures
# ---------------------------------------------------------------------------


def _make_candles(
    start_price: float,
    trend_pct_per_bar: float,
    n: int = 50,
    volatility_pct: float = 0.005,
) -> list[dict[str, Any]]:
    candles = []
    price = start_price
    for i in range(n):
        price *= 1 + trend_pct_per_bar
        high = price * (1 + volatility_pct)
        low = price * (1 - volatility_pct)
        candles.append({"open": price, "high": high, "low": low, "close": price})
    return candles


def _make_range_candles(
    center: float = 65000.0, n: int = 50, amplitude_pct: float = 0.003
) -> list[dict[str, Any]]:
    candles = []
    for i in range(n):
        offset = amplitude_pct * math.sin(2 * math.pi * i / 10)
        price = center * (1 + offset)
        high = price * 1.002
        low = price * 0.998
        candles.append({"open": price, "high": high, "low": low, "close": price})
    return candles


def _make_high_vol_candles(
    start_price: float = 65000.0, n: int = 120
) -> list[dict[str, Any]]:
    """Generate candles where ATR/price variance spikes in the recent window.

    The key is that vol-of-vol measures the *stdev of ATR ratios* — not
    the ATR itself. So we need ATR ratios to *vary wildly* within the
    last 20 bars (alternating calm and explosive bars).
    """
    candles = []
    price = start_price
    for i in range(n):
        if i >= n - 20:
            # Alternate between tiny and huge ATR within the window
            swing = 0.20 if i % 2 == 0 else 0.001
        else:
            swing = 0.002
        direction = 1 if i % 3 == 0 else -1
        price *= 1 + direction * swing * 0.1
        high = price * (1 + swing)
        low = price * (1 - swing)
        candles.append({"open": price, "high": high, "low": low, "close": price})
    return candles


# ===========================================================================
# Regime detection — all five regimes
# ===========================================================================


def test_detect_trend_up() -> None:
    candles_1h = _make_candles(65000.0, trend_pct_per_bar=0.002, n=50)
    candles_4h = _make_candles(65000.0, trend_pct_per_bar=0.003, n=50)

    snapshot = detect_regime(candles_1h, candles_4h)

    assert snapshot.regime == MarketRegime.TREND_UP
    assert snapshot.trend_slope_1h is not None
    assert snapshot.trend_slope_1h > 0
    assert snapshot.trend_slope_4h is not None
    assert snapshot.trend_slope_4h > 0


def test_detect_trend_down() -> None:
    candles_1h = _make_candles(65000.0, trend_pct_per_bar=-0.002, n=50)
    candles_4h = _make_candles(65000.0, trend_pct_per_bar=-0.003, n=50)

    snapshot = detect_regime(candles_1h, candles_4h)

    assert snapshot.regime == MarketRegime.TREND_DOWN
    assert snapshot.trend_slope_1h is not None
    assert snapshot.trend_slope_1h < 0
    assert snapshot.trend_slope_4h is not None
    assert snapshot.trend_slope_4h < 0


def test_detect_range() -> None:
    candles_1h = _make_range_candles(n=50)
    candles_4h = _make_range_candles(n=50)

    snapshot = detect_regime(candles_1h, candles_4h)

    assert snapshot.regime == MarketRegime.RANGE


def test_detect_high_vol() -> None:
    candles_1h = _make_high_vol_candles(n=120)
    candles_4h = _make_range_candles(n=50)

    snapshot = detect_regime(candles_1h, candles_4h)

    assert snapshot.regime == MarketRegime.HIGH_VOL


def test_detect_unknown_insufficient_data() -> None:
    candles_1h = [{"close": 65000.0}]
    candles_4h = [{"close": 65000.0}]

    snapshot = detect_regime(candles_1h, candles_4h)

    assert snapshot.regime == MarketRegime.UNKNOWN


def test_detect_unknown_empty_candles() -> None:
    snapshot = detect_regime([], [])
    assert snapshot.regime == MarketRegime.UNKNOWN


def test_detect_regime_preserves_metadata() -> None:
    candles = _make_candles(65000.0, 0.002, n=50)
    snapshot = detect_regime(
        candles, candles,
        universe_tag="btc_eth",
        bar_close_ts="2026-04-26T12:00:00Z",
        breadth_pct=0.65,
    )

    assert snapshot.universe_tag == "btc_eth"
    assert snapshot.bar_close_ts == "2026-04-26T12:00:00Z"
    assert snapshot.breadth_pct == 0.65


# ===========================================================================
# Helper function tests
# ===========================================================================


def test_linreg_slope_positive() -> None:
    values = [float(i) for i in range(20)]
    slope = _linreg_slope(values)
    assert slope is not None
    assert slope > 0


def test_linreg_slope_negative() -> None:
    values = [float(20 - i) for i in range(20)]
    slope = _linreg_slope(values)
    assert slope is not None
    assert slope < 0


def test_linreg_slope_flat() -> None:
    values = [5.0] * 20
    slope = _linreg_slope(values)
    assert slope is not None
    assert abs(slope) < 1e-10


def test_linreg_slope_insufficient_data() -> None:
    assert _linreg_slope([1.0, 2.0]) is None
    assert _linreg_slope([]) is None


def test_log_closes_filters_invalid() -> None:
    candles = [
        {"close": 100.0},
        {"close": 0},
        {"close": None},
        {"close": 200.0},
    ]
    result = _log_closes(candles)
    assert len(result) == 2
    assert abs(result[0] - math.log(100.0)) < 1e-10
    assert abs(result[1] - math.log(200.0)) < 1e-10


def test_atr_values_basic() -> None:
    candles = [
        {"high": 110, "low": 90, "close": 100},
        {"high": 115, "low": 95, "close": 105},
        {"high": 120, "low": 100, "close": 110},
    ]
    atrs = _atr_values(candles)
    assert len(atrs) == 3
    assert all(a > 0 for a in atrs)


def test_vol_of_vol_insufficient_data() -> None:
    candles = [{"high": 100, "low": 90, "close": 95}] * 5
    vov, p90 = _vol_of_vol(candles, window=20)
    assert vov is None
    assert p90 is None


# ===========================================================================
# Redis caching
# ===========================================================================


def test_get_cached_regime_returns_none_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.redis_client as rc_mod

    monkeypatch.setattr(rc_mod, "get_redis_client", lambda **kw: (_ for _ in ()).throw(Exception("no redis")))
    result = get_cached_regime()
    assert result is None


def test_cache_and_retrieve_regime(monkeypatch: pytest.MonkeyPatch) -> None:
    store: dict[str, str] = {}

    class FakeRedis:
        def set(self, key: str, value: str, ex: int | None = None) -> None:
            store[key] = value

        def get(self, key: str) -> str | None:
            return store.get(key)

    import backend.redis_client as rc_mod

    monkeypatch.setattr(rc_mod, "get_redis_client", lambda **kw: FakeRedis())

    snapshot = RegimeSnapshot(
        regime=MarketRegime.TREND_UP,
        universe_tag="test",
        trend_slope_1h=0.001,
    )
    cache_regime(snapshot)
    retrieved = get_cached_regime(universe_tag="test")

    assert retrieved is not None
    assert retrieved.regime == MarketRegime.TREND_UP
    assert retrieved.universe_tag == "test"
    assert retrieved.trend_slope_1h == 0.001


def test_get_current_regime_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.regime.detector.get_cached_regime",
        lambda **kwargs: None,
    )
    result = get_current_regime()
    assert result.regime == MarketRegime.UNKNOWN


# ===========================================================================
# Strategy gating — allowed_regimes
# ===========================================================================


def test_momentum_only_allowed_in_trends() -> None:
    defn = STRATEGY_REGISTRY["momentum"]
    assert "trend_up" in defn.allowed_regimes
    assert "trend_down" in defn.allowed_regimes
    assert "range" not in defn.allowed_regimes
    assert "high_vol" not in defn.allowed_regimes


def test_mean_reversion_only_allowed_in_range() -> None:
    defn = STRATEGY_REGISTRY["mean_reversion"]
    assert "range" in defn.allowed_regimes
    assert "trend_up" not in defn.allowed_regimes
    assert "trend_down" not in defn.allowed_regimes
    assert "high_vol" not in defn.allowed_regimes


def test_breakout_only_allowed_in_trends() -> None:
    defn = STRATEGY_REGISTRY["breakout"]
    assert "trend_up" in defn.allowed_regimes
    assert "trend_down" in defn.allowed_regimes
    assert "range" not in defn.allowed_regimes


def test_delta_neutral_carry_allowed_in_all_regimes() -> None:
    defn = STRATEGY_REGISTRY["delta_neutral_carry"]
    for regime in MarketRegime:
        assert regime.value in defn.allowed_regimes


def test_whale_follower_not_allowed_in_high_vol() -> None:
    defn = STRATEGY_REGISTRY["whale_follower"]
    assert "high_vol" not in defn.allowed_regimes
    assert "trend_up" in defn.allowed_regimes
    assert "range" in defn.allowed_regimes


# ===========================================================================
# Policy engine integration — regime mismatch rejection
# ===========================================================================


def _mock_policy_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.trading.policy_engine._portfolio_warnings", lambda: [])
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_kill_switch_state",
        lambda: {"active": False, "reason": None},
    )
    monkeypatch.setattr("backend.trading.policy_engine.live_trading_blockers", lambda: [])
    monkeypatch.setattr("backend.trading.policy_engine.current_trading_mode", lambda: "paper")
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_risk_approval",
        lambda payload: {
            "data": {
                "approved": True,
                "max_size_usd": payload["proposed_size_usd"],
                "confidence": 0.8,
                "reasons": [],
                "stop_guidance": "Use the defined invalidation.",
            }
        },
    )


def _momentum_proposal() -> dict[str, object]:
    return {
        "source_agent": "strategy_agent",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 1000.0,
        "rationale": "Strong uptrend detected with RSI confirmation.",
        "strategy_id": "momentum",
        "strategy_template_id": "momentum",
    }


def _mean_reversion_proposal() -> dict[str, object]:
    return {
        "source_agent": "strategy_agent",
        "symbol": "ETHUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 800.0,
        "rationale": "Oversold bounce from Bollinger Band lower band.",
        "strategy_id": "mean_reversion",
        "strategy_template_id": "mean_reversion",
    }


def test_policy_rejects_momentum_in_range_regime(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.RANGE),
    )

    decision = evaluate_trade_proposal(_momentum_proposal())

    assert decision.status == "rejected"
    assert RiskRejectionReason.REGIME_MISMATCH in decision.rejection_reasons
    assert any("regime_gate=rejected" in t for t in decision.policy_trace)
    assert any("regime=range" in t for t in decision.policy_trace)


def test_policy_approves_momentum_in_trend_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.TREND_UP),
    )

    decision = evaluate_trade_proposal(_momentum_proposal())

    assert decision.approved is True
    assert RiskRejectionReason.REGIME_MISMATCH not in decision.rejection_reasons
    assert any("regime_gate=approved" in t for t in decision.policy_trace)


def test_policy_rejects_mean_reversion_in_trend_up(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.TREND_UP),
    )

    decision = evaluate_trade_proposal(_mean_reversion_proposal())

    assert decision.status == "rejected"
    assert RiskRejectionReason.REGIME_MISMATCH in decision.rejection_reasons


def test_policy_approves_mean_reversion_in_range(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.RANGE),
    )

    decision = evaluate_trade_proposal(_mean_reversion_proposal())

    assert decision.approved is True
    assert RiskRejectionReason.REGIME_MISMATCH not in decision.rejection_reasons


def test_policy_rejects_on_unknown_regime_for_gated_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """UNKNOWN regime should fail-closed: strategies with restricted regimes get rejected."""
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.UNKNOWN),
    )

    decision = evaluate_trade_proposal(_momentum_proposal())

    assert decision.status == "rejected"
    assert RiskRejectionReason.REGIME_MISMATCH in decision.rejection_reasons
    assert any("regime=unknown" in t for t in decision.policy_trace)


def test_policy_approves_delta_neutral_carry_in_any_regime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delta neutral carry is allowed in all regimes including unknown."""
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.HIGH_VOL),
    )

    proposal = {
        "source_agent": "carry_bot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 500.0,
        "rationale": "Negative funding rate harvest opportunity.",
        "strategy_id": "delta_neutral_carry",
        "strategy_template_id": "delta_neutral_carry",
    }

    decision = evaluate_trade_proposal(proposal)

    assert decision.approved is True
    assert RiskRejectionReason.REGIME_MISMATCH not in decision.rejection_reasons


def test_policy_skips_regime_gate_for_unknown_strategy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Proposals with unresolvable strategy_id skip the regime gate."""
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.HIGH_VOL),
    )

    proposal = {
        "source_agent": "manual_agent",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 500.0,
        "rationale": "Manual trade with no strategy template.",
        "strategy_id": "custom_xyz",
        "strategy_template_id": "not_in_registry",
    }

    decision = evaluate_trade_proposal(proposal)

    assert decision.approved is True
    assert any("regime_gate=skipped" in t for t in decision.policy_trace)


def test_policy_rejects_whale_follower_in_high_vol(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.HIGH_VOL),
    )

    proposal = {
        "source_agent": "whale_bot",
        "symbol": "BTCUSDT",
        "side": "buy",
        "order_type": "market",
        "requested_size_usd": 1000.0,
        "rationale": "Whale accumulation detected on BTCUSDT.",
        "strategy_id": "whale_follower",
        "strategy_template_id": "whale_follower",
    }

    decision = evaluate_trade_proposal(proposal)

    assert decision.status == "rejected"
    assert RiskRejectionReason.REGIME_MISMATCH in decision.rejection_reasons


def test_policy_regime_trace_always_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regime value should always appear in the policy trace."""
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: RegimeSnapshot(regime=MarketRegime.TREND_DOWN),
    )

    decision = evaluate_trade_proposal(_momentum_proposal())

    assert any("regime=trend_down" in t for t in decision.policy_trace)


def test_policy_detector_exception_defaults_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the detector raises, regime defaults to UNKNOWN (fail-closed)."""
    _mock_policy_base(monkeypatch)
    monkeypatch.setattr(
        "backend.trading.policy_engine.get_current_regime",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("detector broken")),
    )

    decision = evaluate_trade_proposal(_momentum_proposal())

    assert decision.status == "rejected"
    assert RiskRejectionReason.REGIME_MISMATCH in decision.rejection_reasons
    assert any("regime=unknown" in t for t in decision.policy_trace)


# ===========================================================================
# MarketRegime enum
# ===========================================================================


def test_market_regime_enum_values() -> None:
    assert MarketRegime.TREND_UP == "trend_up"
    assert MarketRegime.TREND_DOWN == "trend_down"
    assert MarketRegime.RANGE == "range"
    assert MarketRegime.HIGH_VOL == "high_vol"
    assert MarketRegime.UNKNOWN == "unknown"
    assert len(MarketRegime) == 5


def test_regime_snapshot_serialization() -> None:
    snap = RegimeSnapshot(
        regime=MarketRegime.TREND_UP,
        trend_slope_1h=0.001,
        trend_slope_4h=0.002,
    )
    json_str = snap.model_dump_json()
    restored = RegimeSnapshot.model_validate_json(json_str)
    assert restored.regime == MarketRegime.TREND_UP
    assert restored.trend_slope_1h == 0.001
