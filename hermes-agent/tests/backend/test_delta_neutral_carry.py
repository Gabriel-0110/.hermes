from __future__ import annotations

import json

from backend.strategies.delta_neutral_carry import DeltaNeutralCarryBotRunner, build_carry_proposal
from backend.tools.get_risk_approval import get_risk_approval
from backend.trading import paired_unwind_proposal


def test_delta_neutral_carry_runner_emits_paired_proposal(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.strategies.delta_neutral_carry._fetch_funding_snapshot",
        lambda symbols: [
            {
                "symbol": "ETHUSDT",
                "funding_rate": -0.0002,
                "mark_price": 2000.0,
                "index_price": 1998.0,
            }
        ],
    )

    runner = DeltaNeutralCarryBotRunner()
    runner.default_size_usd = 500.0

    proposals = runner.scan(["ETH", "DOGE"])

    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.execution_style == "paired"
    assert proposal.strategy_template_id == "delta_neutral_carry"
    assert proposal.metadata["carry_trade"] is True
    assert proposal.metadata["delta_estimate_usd"] <= 5.0
    assert len(proposal.legs) == 2
    assert proposal.legs[0].account_type == "spot"
    assert proposal.legs[1].account_type == "swap"
    assert proposal.legs[1].position_side == "short"


def test_paired_unwind_proposal_flips_legs_for_carry_exit() -> None:
    proposal = build_carry_proposal(
        base_symbol="BTC",
        funding_rate=-0.0002,
        mark_price=60000.0,
        index_price=59950.0,
        size_usd=300.0,
        source_agent="delta_neutral_carry_bot",
        strategy_id="delta_neutral_carry/v1.0",
    )

    unwind = paired_unwind_proposal(proposal, reason="stop hit")

    assert unwind.execution_style == "paired"
    assert unwind.metadata["paired_action"] == "unwind"
    assert unwind.legs[0].side == "sell"
    assert unwind.legs[1].side == "buy"
    assert unwind.legs[1].reduce_only is True


def test_get_risk_approval_caps_carry_trade_at_thirty_percent_equity(monkeypatch) -> None:
    class FakeRedis:
        def get(self, key: str):
            if key == "hermes:risk:kill_switch":
                return None
            if key == "hermes:risk:limits":
                return json.dumps({"carry_trade_max_equity_pct": 30.0}).encode()
            return None

    monkeypatch.setattr("backend.tools.get_risk_approval.get_redis_client", lambda: FakeRedis())
    monkeypatch.setattr(
        "backend.tools.get_risk_approval.get_volatility_metrics",
        lambda payload: {"data": {"realized_volatility": 0.03}, "meta": {"providers": []}},
    )
    monkeypatch.setattr(
        "backend.tools.get_risk_approval.get_event_risk_summary",
        lambda payload: {"data": {"severity": "low"}, "meta": {"providers": []}},
    )
    monkeypatch.setattr(
        "backend.tools.get_portfolio_state.get_portfolio_state",
        lambda payload=None: {"data": {"total_equity_usd": 1000.0}},
    )

    response = get_risk_approval(
        {
            "symbol": "ETHUSDT",
            "proposed_size_usd": 500.0,
            "strategy_template_id": "delta_neutral_carry",
            "metadata": {"carry_trade": True},
        }
    )

    assert response["meta"]["ok"] is True
    assert response["data"]["approved"] is True
    assert response["data"]["max_size_usd"] == 300.0
    assert any("30.0% of equity" in reason for reason in response["data"]["reasons"])