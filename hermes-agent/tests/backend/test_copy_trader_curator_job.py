from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.copy_trader_proposals import (
    approve_copy_trader_switch_proposal,
    create_or_get_pending_copy_trader_switch_proposal,
    reject_copy_trader_switch_proposal,
)
from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import CopyTraderScoreRow, CopyTraderSwitchProposalRow, ResearchMemoRow
from backend.db.session import get_engine
from backend.jobs.copy_trader_curator import run_copy_trader_curator


class FakeTelegramNotificationClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.configured = True

    def send_message(self, text: str, *, reply_markup=None, parse_mode=None, chat_id=None):
        self.calls.append(
            {
                "text": text,
                "reply_markup": reply_markup,
                "parse_mode": parse_mode,
                "chat_id": chat_id,
            }
        )
        return {"message_id": 9001}


def test_copy_trader_curator_scores_and_creates_switch_proposal(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'copy_trader_curator.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    observed_at = datetime(2026, 4, 25, 12, 0, tzinfo=UTC)
    with session_scope(database_url=database_url) as session:
        for days_ago in range(1, 7):
            session.add(
                CopyTraderScoreRow(
                    score_time=observed_at - timedelta(days=days_ago),
                    source="bitmart_aihub",
                    trader_id="master-lag",
                    trader_name="Lagging Master",
                    rank=3,
                    score=0.18,
                    score_percentile=0.20,
                    sharpe_30d=0.35,
                    max_drawdown_pct_30d=28.0,
                    fee_pct=30.0,
                    is_active_master=True,
                    metadata_json={"seed": True},
                )
            )

    leaderboard_rows = [
        {
            "trader_id": "master-lag",
            "name": "Lagging Master",
            "sharpe_30d": 0.4,
            "max_drawdown_30d": 0.28,
            "fee_pct": 30,
        },
        {
            "trader_id": "master-steady",
            "name": "Steady Alpha",
            "sharpe_30d": 1.6,
            "max_drawdown_30d": 0.08,
            "fee_pct": 10,
        },
        {
            "trader_id": "master-mid",
            "name": "Middle Pack",
            "sharpe_30d": 1.0,
            "max_drawdown_30d": 0.16,
            "fee_pct": 20,
        },
    ]
    fake_telegram = FakeTelegramNotificationClient()

    summary = run_copy_trader_curator(
        database_url=database_url,
        observed_at=observed_at,
        leaderboard_rows=leaderboard_rows,
        active_masters=[{"trader_id": "master-lag", "name": "Lagging Master"}],
        notification_client=fake_telegram,
    )

    assert summary.score_rows_written == 3
    assert summary.proposals_created == 1
    assert summary.notifications_sent == 1
    assert len(fake_telegram.calls) == 1
    assert "Approve switch" in json.dumps(fake_telegram.calls[0]["reply_markup"])

    with session_scope(database_url=database_url) as session:
        proposal = session.scalars(select(CopyTraderSwitchProposalRow)).one()
        latest_scores = list(
            session.scalars(
                select(CopyTraderScoreRow)
                .where(CopyTraderScoreRow.score_time == observed_at)
                .order_by(CopyTraderScoreRow.rank.asc())
            )
        )

    assert proposal.active_trader_name == "Lagging Master"
    assert proposal.candidate_trader_name == "Steady Alpha"
    assert proposal.notification_message_id == "9001"
    assert latest_scores[0].trader_name == "Steady Alpha"
    assert latest_scores[-1].trader_name == "Lagging Master"
    assert latest_scores[-1].is_active_master is True


def test_copy_trader_curator_loads_leaderboard_from_research_memo(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'copy_trader_memo.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    observed_at = datetime(2026, 4, 25, 6, 0, tzinfo=UTC)
    memo_payload = {
        "leaderboard": [
            {
                "trader_id": "leader-a",
                "trader_name": "Leader A",
                "sharpe_30d": 1.8,
                "max_drawdown_pct_30d": 7.5,
                "fee_pct": 12,
            },
            {
                "trader_id": "leader-b",
                "trader_name": "Leader B",
                "sharpe_30d": 1.1,
                "max_drawdown_pct_30d": 13.0,
                "fee_pct": 18,
            },
        ]
    }
    with session_scope(database_url=database_url) as session:
        session.add(
            ResearchMemoRow(
                memo_time=observed_at - timedelta(hours=2),
                symbol=None,
                tags=["bitmart_aihub", "copy_trader_leaderboard"],
                content=f"```json\n{json.dumps(memo_payload)}\n```",
                source_agent="market-researcher",
                strategy_ref="copy_trader_curator",
            )
        )

    summary = run_copy_trader_curator(
        database_url=database_url,
        observed_at=observed_at,
        notification_client=FakeTelegramNotificationClient(),
    )

    assert summary.source == "research_memo"
    assert summary.score_rows_written == 2
    assert summary.proposals_created == 0

    with session_scope(database_url=database_url) as session:
        stored_scores = list(session.scalars(select(CopyTraderScoreRow).order_by(CopyTraderScoreRow.rank.asc())))

    assert [row.trader_name for row in stored_scores] == ["Leader A", "Leader B"]


def test_copy_trader_switch_proposals_can_be_resolved(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'copy_trader_proposals.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    proposal, created = create_or_get_pending_copy_trader_switch_proposal(
        active_trader_id="master-old",
        active_trader_name="Master Old",
        candidate_trader_id="master-new",
        candidate_trader_name="Master New",
        rationale="Seven-day underperformance streak.",
        active_score=0.22,
        active_percentile=0.15,
        candidate_score=0.88,
        candidate_percentile=1.0,
        database_url=database_url,
    )

    assert created is True
    approved = approve_copy_trader_switch_proposal(proposal["id"], operator="telegram:alice", database_url=database_url)
    rejected = reject_copy_trader_switch_proposal(proposal["id"], operator="telegram:bob", database_url=database_url)

    assert approved is not None
    assert approved["status"] == "approved"
    assert approved["operator"] == "telegram:alice"
    assert rejected is None