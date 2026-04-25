from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.event_bus.models import TradingEvent, TradingEventEnvelope
from backend.jobs.whale_tracker import run_whale_tracker
from backend.strategies.whale_follower import build_whale_follow_proposal, score_whale_follower
from backend.trading.models import ExecutionDispatchResult, ExecutionRequest, PolicyDecision


class FakeRedis:
    def __init__(self) -> None:
        self.values: set[str] = set()

    def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        if nx and key in self.values:
            return False
        self.values.add(key)
        return True


class FakePublisher:
    def __init__(self) -> None:
        self.events: list[TradingEvent] = []

    def publish(self, event: TradingEvent) -> TradingEventEnvelope:
        self.events.append(event)
        return TradingEventEnvelope(redis_id=f"{len(self.events)}-0", event=event)


class FakeBitMartWalletClient:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def list_smart_money_wallets(self, *, limit: int = 50):
        return [
            {"walletAddress": "wallet-sol", "chainId": 2001, "profitRate7d": 32.0, "winRate7d": 72.0},
            {"walletAddress": "wallet-arb", "chainId": 2004, "profitRate7d": 28.0, "winRate7d": 69.0},
            {"walletAddress": "wallet-old", "chainId": 2003, "profitRate7d": 14.0, "winRate7d": 58.0},
        ][:limit]

    def get_smart_money_info(self, wallet_address: str):
        recent_ms = int((self.now - timedelta(minutes=20)).timestamp() * 1000)
        old_ms = int((self.now - timedelta(hours=3)).timestamp() * 1000)
        if wallet_address == "wallet-sol":
            return {
                "profitInfo": {"profitRate7d": 35.0, "winRate7d": 75.0},
                "tradeHistory": [
                    {
                        "tokenSymbol": "ETH",
                        "tradeDirection": "BUY",
                        "tradeTime": recent_ms,
                        "totalUSD": 30_000,
                        "txHash": "tx-sol-1",
                        "chainId": 2001,
                    },
                    {
                        "tokenSymbol": "DOGE",
                        "tradeDirection": "BUY",
                        "tradeTime": recent_ms,
                        "totalUSD": 99_000,
                        "txHash": "tx-sol-ignored",
                        "chainId": 2001,
                    },
                ],
            }
        if wallet_address == "wallet-arb":
            return {
                "profitInfo": {"profitRate7d": 30.0, "winRate7d": 68.0},
                "tradeHistory": [
                    {
                        "tokenSymbol": "ETH",
                        "tradeDirection": "BUY",
                        "tradeTime": recent_ms,
                        "totalUSD": 25_500,
                        "txHash": "tx-arb-1",
                        "chainId": 2004,
                    }
                ],
            }
        return {
            "profitInfo": {"profitRate7d": 14.0, "winRate7d": 58.0},
            "tradeHistory": [
                {
                    "tokenSymbol": "ETH",
                    "tradeDirection": "BUY",
                    "tradeTime": old_ms,
                    "totalUSD": 80_000,
                    "txHash": "tx-old-1",
                    "chainId": 2003,
                }
            ],
        }


def test_whale_tracker_emits_aggregated_whale_flow_event() -> None:
    now = datetime(2026, 4, 24, 18, 0, tzinfo=UTC)
    publisher = FakePublisher()
    redis = FakeRedis()

    summary = run_whale_tracker(
        client=FakeBitMartWalletClient(now),
        publisher=publisher,
        redis_client=redis,
        now=now,
    )

    assert summary.emitted_events == 1
    assert summary.new_trades == 2
    assert publisher.events[0].event_type == "whale_flow"
    assert publisher.events[0].symbol == "ETHUSDT"
    assert publisher.events[0].payload["total_accumulation_usd"] == 55500.0
    assert publisher.events[0].payload["unique_wallet_count"] == 2

    # Dedupe is stateful across runs.
    second_summary = run_whale_tracker(
        client=FakeBitMartWalletClient(now),
        publisher=publisher,
        redis_client=redis,
        now=now,
    )
    assert second_summary.emitted_events == 0
    assert second_summary.duplicate_trades_skipped == 2


def test_whale_follower_scores_and_builds_proposal() -> None:
    payload = {
        "symbol": "ETHUSDT",
        "total_accumulation_usd": 180_000,
        "unique_wallet_count": 3,
        "trade_count": 5,
        "avg_profit_rate_7d": 27.5,
        "avg_win_rate_7d": 66.0,
        "latest_trade_at": "2026-04-24T18:00:00+00:00",
    }

    candidate = score_whale_follower("ETHUSDT", payload, regime="risk_on")

    assert candidate.direction == "long"
    assert candidate.confidence >= 0.35

    proposal = build_whale_follow_proposal(candidate, payload)
    assert proposal.symbol == "ETHUSDT"
    assert proposal.requested_size_usd == 100.0
    assert proposal.strategy_template_id == "whale_follower"


def test_orchestrator_handles_whale_flow_event(monkeypatch) -> None:
    from backend.event_bus.workers import _handle_whale_flow

    dispatched: list[object] = []

    monkeypatch.setattr("backend.event_bus.workers._fetch_market_regime", lambda: "risk_on")
    monkeypatch.setattr(
        "backend.observability.service.get_observability_service",
        lambda: SimpleNamespace(
            record_agent_decision=lambda **kwargs: None,
            record_execution_event=lambda **kwargs: None,
        ),
    )

    def _fake_dispatch(proposal):
        dispatched.append(proposal)
        return ExecutionDispatchResult(
            proposal_id=proposal.proposal_id,
            status="queued",
            execution_mode="paper",
            correlation_id="corr-whale",
            workflow_id="wf-whale",
            approval_required=False,
            policy_decision=PolicyDecision(
                proposal_id=proposal.proposal_id,
                status="approved",
                execution_mode="paper",
                approved=True,
                approved_size_usd=proposal.requested_size_usd,
                requires_operator_approval=False,
            ),
            dispatch_payload=ExecutionRequest(
                proposal_id=proposal.proposal_id,
                symbol=proposal.symbol,
                side=proposal.side,
                order_type=proposal.order_type,
                size_usd=proposal.requested_size_usd,
                amount=proposal.requested_size_usd,
                strategy_id=proposal.strategy_id,
                strategy_template_id=proposal.strategy_template_id,
            ),
        )

    monkeypatch.setattr("backend.trading.dispatch_trade_proposal", _fake_dispatch)

    envelope = TradingEventEnvelope(
        event=TradingEvent(
            event_type="whale_flow",
            symbol="ETHUSDT",
            correlation_id="corr-whale",
            workflow_id="wf-whale",
            payload={
                "symbol": "ETHUSDT",
                "total_accumulation_usd": 120_000,
                "unique_wallet_count": 2,
                "trade_count": 4,
                "avg_profit_rate_7d": 24.0,
                "avg_win_rate_7d": 65.0,
                "latest_trade_at": "2026-04-24T18:00:00+00:00",
            },
        )
    )

    handled = _handle_whale_flow(envelope)

    assert handled is True
    assert len(dispatched) == 1
    assert dispatched[0].symbol == "ETHUSDT"
    assert dispatched[0].strategy_template_id == "whale_follower"