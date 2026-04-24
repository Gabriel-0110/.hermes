"""Tests for funding-rate context in built-in strategy scorers."""

from __future__ import annotations

from backend.strategies.breakout import score_breakout
from backend.strategies.mean_reversion import score_mean_reversion
from backend.strategies.momentum import score_momentum


def test_momentum_long_gets_bonus_from_negative_funding() -> None:
    indicators = {
        "rsi_14": 60,
        "close": 105,
        "sma_20": 100,
        "sma_50": 95,
        "macd_histogram": 0.5,
    }

    baseline = score_momentum("ETH", indicators)
    with_funding = score_momentum("ETH", indicators, funding_data={"ETH": -0.0005})

    assert with_funding.direction == "long"
    assert with_funding.confidence > baseline.confidence
    assert "Funding" in with_funding.rationale


def test_mean_reversion_short_gets_bonus_from_positive_funding() -> None:
    indicators = {
        "rsi_14": 75,
        "close": 120,
        "sma_20": 100,
        "atr_14": 10,
    }

    baseline = score_mean_reversion("XRP", indicators)
    with_funding = score_mean_reversion("XRP", indicators, funding_data={"XRPUSDT": 0.0005})

    assert with_funding.direction == "short"
    assert with_funding.confidence > baseline.confidence
    assert "Funding" in with_funding.rationale


def test_breakout_long_penalized_by_crowded_positive_funding() -> None:
    indicators = {
        "close": 100,
        "sma_20": 100,
        "bb_upper": 101,
        "bb_lower": 99.5,
    }

    baseline = score_breakout("BTC", indicators)
    with_funding = score_breakout("BTC", indicators, funding_data={"BTC": 0.0005})

    assert baseline.direction == "long"
    assert with_funding.confidence < baseline.confidence
    assert "Funding" in with_funding.rationale
