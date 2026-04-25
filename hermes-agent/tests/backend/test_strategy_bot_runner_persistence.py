from __future__ import annotations

from sqlalchemy import select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import AgentSignalRow, StrategyEvaluationRow
from backend.db.session import get_engine
from backend.strategies.registry import ScoredCandidate
from backend.trading.bot_runner import StrategyBotRunner
from backend.trading.models import ExecutionDispatchResult, ExecutionRequest, PolicyDecision


class _StubRunner(StrategyBotRunner):
    strategy_id = "momentum/v1.1"
    source_agent = "momentum_bot"
    default_size_usd = 50.0
    min_confidence = 0.3

    def scan(self, universe: list[str]):
        return [
            ScoredCandidate(
                symbol="BTC",
                direction="long",
                confidence=0.84,
                rationale="synthetic runner signal",
                strategy_name="momentum",
                strategy_version="1.1.0",
            )
        ]

    def timeframe_for_candidate(self, candidate: ScoredCandidate) -> str | None:
        return "4h"


def test_strategy_bot_runner_persists_agent_signal_and_evaluation(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'runner.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    def fake_dispatch_trade_proposal(proposal):
        decision = PolicyDecision(
            proposal_id=proposal.proposal_id,
            status="approved",
            execution_mode="paper",
            approved=True,
            approved_size_usd=proposal.requested_size_usd,
        )
        request = ExecutionRequest(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            side=proposal.side,
            order_type=proposal.order_type,
            size_usd=proposal.requested_size_usd,
            amount=proposal.requested_size_usd,
            rationale=proposal.rationale,
            strategy_id=proposal.strategy_id,
            strategy_template_id=proposal.strategy_template_id,
            timeframe=proposal.timeframe,
            source_agent=proposal.source_agent,
        )
        return ExecutionDispatchResult(
            proposal_id=proposal.proposal_id,
            status="queued",
            execution_mode="paper",
            correlation_id=proposal.proposal_id,
            workflow_id=f"proposal::{proposal.proposal_id}",
            policy_decision=decision,
            dispatch_payload=request,
        )

    monkeypatch.setattr(
        "backend.trading.execution_service.dispatch_trade_proposal",
        fake_dispatch_trade_proposal,
    )

    results = _StubRunner().run_cycle(["BTC"], dry_run=False)

    assert len(results) == 1
    with session_scope(database_url=database_url) as session:
        signals = list(session.scalars(select(AgentSignalRow)))
        evaluations = list(session.scalars(select(StrategyEvaluationRow)))

    assert len(signals) == 1
    assert signals[0].payload["proposal_id"] == results[0].proposal_id
    assert len(evaluations) == 1
    assert evaluations[0].metadata_json["proposal_id"] == results[0].proposal_id
