"""Tests for capital rotation and portfolio rebalancer."""

from __future__ import annotations

import math
from typing import Any

import pytest

from backend.portfolio.rebalancer import (
    DEFAULT_TEMPERATURE,
    MAX_ALLOCATION_PCT,
    MIN_REBALANCE_BPS,
    AllocationTarget,
    RebalanceProposal,
    SymbolEdge,
    _cap_and_renormalize,
    compute_rebalance,
    softmax_allocations,
)
from backend.jobs.capital_rotation import (
    CapitalRotationSummary,
    _collect_edges,
    run_capital_rotation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_edges(posteriors: dict[str, float]) -> list[SymbolEdge]:
    return [
        SymbolEdge(
            symbol=sym,
            posterior_mean=post,
            multiplier=0.75 + post * 0.5,
            resolved_count=50,
            wins=int(post * 50),
            losses=50 - int(post * 50),
        )
        for sym, post in posteriors.items()
    ]


# ===========================================================================
# Softmax allocation
# ===========================================================================


def test_softmax_equal_edges_produce_equal_allocations() -> None:
    edges = _make_edges({"BTC": 0.6, "ETH": 0.6, "SOL": 0.6, "XRP": 0.6})
    allocs = softmax_allocations(edges)

    assert len(allocs) == 4
    for pct in allocs.values():
        assert abs(pct - 0.25) < 0.01


def test_softmax_dominant_edge_gets_more() -> None:
    edges = _make_edges({"BTC": 0.9, "ETH": 0.5, "SOL": 0.3, "XRP": 0.3})
    allocs = softmax_allocations(edges)

    assert allocs["BTC"] > allocs["ETH"]
    assert allocs["ETH"] > allocs["SOL"]


def test_softmax_respects_40pct_cap() -> None:
    edges = _make_edges({"BTC": 0.99, "ETH": 0.1, "SOL": 0.1, "XRP": 0.1})
    allocs = softmax_allocations(edges, max_pct=0.40)

    assert allocs["BTC"] <= 0.40 + 0.001
    assert abs(sum(allocs.values()) - 1.0) < 0.01


def test_softmax_sums_to_one() -> None:
    edges = _make_edges({"BTC": 0.7, "ETH": 0.6, "SOL": 0.5, "XRP": 0.4})
    allocs = softmax_allocations(edges)

    assert abs(sum(allocs.values()) - 1.0) < 0.001


def test_softmax_empty_edges() -> None:
    assert softmax_allocations([]) == {}


def test_softmax_single_symbol() -> None:
    edges = _make_edges({"BTC": 0.8})
    allocs = softmax_allocations(edges, max_pct=0.40)

    assert allocs["BTC"] <= 0.40 + 0.001


def test_softmax_temperature_effect() -> None:
    edges = _make_edges({"BTC": 0.9, "ETH": 0.6, "SOL": 0.3, "XRP": 0.2})

    hot = softmax_allocations(edges, temperature=5.0, max_pct=1.0)
    cold = softmax_allocations(edges, temperature=0.1, max_pct=1.0)

    hot_spread = hot["BTC"] - hot["XRP"]
    cold_spread = cold["BTC"] - cold["XRP"]
    assert hot_spread < cold_spread


# ===========================================================================
# Cap and renormalize
# ===========================================================================


def test_cap_and_renormalize_basic() -> None:
    raw = {"BTC": 0.60, "ETH": 0.20, "SOL": 0.10, "XRP": 0.10}
    result = _cap_and_renormalize(raw, 0.40)

    assert result["BTC"] <= 0.40 + 0.001
    assert abs(sum(result.values()) - 1.0) < 0.01


def test_cap_and_renormalize_no_excess() -> None:
    raw = {"BTC": 0.25, "ETH": 0.25, "SOL": 0.25, "XRP": 0.25}
    result = _cap_and_renormalize(raw, 0.40)

    assert result == raw


# ===========================================================================
# Compute rebalance
# ===========================================================================


def test_compute_rebalance_produces_targets() -> None:
    edges = _make_edges({"BTC": 0.8, "ETH": 0.6, "SOL": 0.4, "XRP": 0.3})
    current = {"BTC": 0.10, "ETH": 0.10, "SOL": 0.40, "XRP": 0.40}

    proposal = compute_rebalance(edges, current, 10000.0)

    assert proposal.actionable
    assert len(proposal.targets) > 0
    for t in proposal.targets:
        assert t.delta_bps >= MIN_REBALANCE_BPS


def test_compute_rebalance_skips_small_deltas() -> None:
    edges = _make_edges({"BTC": 0.6, "ETH": 0.6, "SOL": 0.6, "XRP": 0.6})
    current = {"BTC": 0.25, "ETH": 0.25, "SOL": 0.25, "XRP": 0.25}

    proposal = compute_rebalance(edges, current, 10000.0)

    assert not proposal.actionable
    assert len(proposal.skipped) == 4


def test_compute_rebalance_all_targets_capped() -> None:
    edges = _make_edges({"BTC": 0.9, "ETH": 0.1, "SOL": 0.1, "XRP": 0.1})
    current = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0, "XRP": 0.0}

    proposal = compute_rebalance(edges, current, 10000.0, max_pct=0.40)

    for t in proposal.targets:
        assert t.target_pct <= 0.40 + 0.001


def test_compute_rebalance_respects_min_delta() -> None:
    edges = _make_edges({"BTC": 0.7, "ETH": 0.5})
    current = {"BTC": 0.50, "ETH": 0.50}

    proposal = compute_rebalance(edges, current, 10000.0, min_rebalance_bps=10000.0)

    assert not proposal.actionable
    assert len(proposal.skipped) == 2


# ===========================================================================
# Capital rotation job
# ===========================================================================


def test_run_capital_rotation_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._collect_edges",
        lambda symbols, **kw: _make_edges(
            {s.upper(): 0.5 + 0.1 * i for i, s in enumerate(symbols)}
        ),
    )
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._get_current_allocations",
        lambda symbols, **kw: ({s.upper(): 0.25 for s in symbols}, 10000.0),
    )

    summary = run_capital_rotation(dry_run=True)

    assert summary.dry_run
    assert summary.proposal is not None
    assert summary.proposals_dispatched == 0
    assert len(summary.edges) == 4


def test_run_capital_rotation_dispatches_proposals(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatched: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._collect_edges",
        lambda symbols, **kw: _make_edges({"BTC": 0.9, "ETH": 0.3, "SOL": 0.2, "XRP": 0.1}),
    )
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._get_current_allocations",
        lambda symbols, **kw: ({"BTC": 0.0, "ETH": 0.0, "SOL": 0.5, "XRP": 0.5}, 10000.0),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.dispatch_trade_proposal",
        lambda payload: dispatched.append(payload),
    )

    summary = run_capital_rotation()

    assert summary.proposals_dispatched > 0
    for d in dispatched:
        assert d["require_operator_approval"] is True
        assert d["source_agent"] == "capital_rotation"


def test_run_capital_rotation_custom_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._collect_edges",
        lambda symbols, **kw: _make_edges({s.upper(): 0.6 for s in symbols}),
    )
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._get_current_allocations",
        lambda symbols, **kw: ({s.upper(): 1.0 / len(symbols) for s in symbols}, 5000.0),
    )

    summary = run_capital_rotation(universe=["BTC", "ETH"], dry_run=True)

    assert summary.universe == ["BTC", "ETH"]
    assert len(summary.edges) == 2


# ===========================================================================
# Proposal properties
# ===========================================================================


def test_rebalance_proposals_always_require_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    dispatched: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._collect_edges",
        lambda symbols, **kw: _make_edges({"BTC": 0.95, "ETH": 0.1, "SOL": 0.1, "XRP": 0.1}),
    )
    monkeypatch.setattr(
        "backend.jobs.capital_rotation._get_current_allocations",
        lambda symbols, **kw: ({"BTC": 0.0, "ETH": 0.33, "SOL": 0.33, "XRP": 0.34}, 10000.0),
    )
    monkeypatch.setattr(
        "backend.trading.execution_service.dispatch_trade_proposal",
        lambda payload: dispatched.append(payload),
    )

    run_capital_rotation()

    for d in dispatched:
        assert d["require_operator_approval"] is True


# ===========================================================================
# Summary markdown
# ===========================================================================


def test_summary_markdown() -> None:
    summary = CapitalRotationSummary(
        universe=["BTC", "ETH"],
        edges=[{"symbol": "BTC", "posterior_mean": 0.7, "multiplier": 1.1, "wins": 7, "losses": 3}],
    )
    md = summary.to_markdown()
    assert "BTC" in md
    assert "Capital rotation" in md


def test_rebalance_proposal_markdown() -> None:
    proposal = RebalanceProposal(total_equity_usd=10000.0)
    proposal.targets.append(AllocationTarget(
        symbol="BTC",
        target_pct=0.35,
        current_pct=0.10,
        delta_pct=0.25,
        delta_bps=2500.0,
        edge=SymbolEdge(symbol="BTC", posterior_mean=0.8, multiplier=1.15, resolved_count=50, wins=40, losses=10),
    ))
    md = proposal.to_markdown()
    assert "BTC" in md
    assert "2500" in md
