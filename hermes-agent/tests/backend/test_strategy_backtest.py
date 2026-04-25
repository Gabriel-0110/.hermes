from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import ReplayResultRow, ReplayRunRow
from backend.db.session import get_engine
from backend.evaluation import backtest as backtest_module
from backend.strategies.registry import ScoredCandidate


def _synthetic_bars(start: datetime, count: int = 96) -> list[dict[str, float | str | None]]:
    bars: list[dict[str, float | str | None]] = []
    price = 100.0
    for index in range(count):
        price += 0.4
        ts = start + timedelta(hours=index)
        bars.append(
            {
                "timestamp": ts.isoformat(),
                "open": price - 0.2,
                "high": price + 0.3,
                "low": price - 0.5,
                "close": price,
                "volume": 1_000 + (index * 10),
            }
        )
    return bars


def test_run_strategy_backtest_persists_replay_artifacts(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'backtest.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    ensure_time_series_schema(get_engine(database_url=database_url))

    bars = _synthetic_bars(datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(backtest_module, "_load_historical_bars", lambda *args, **kwargs: (bars, "stub"))

    def fake_score_window(*, strategy_name, scorer, symbol, bars, timeframe):
        if len(bars) in {53, 63, 73}:
            return ScoredCandidate(
                symbol=symbol,
                direction="long",
                confidence=0.82,
                rationale="synthetic momentum continuation",
                strategy_name=strategy_name,
                strategy_version="test",
            )
        return ScoredCandidate(
            symbol=symbol,
            direction="watch",
            confidence=0.12,
            rationale="no-op",
            strategy_name=strategy_name,
            strategy_version="test",
        )

    monkeypatch.setattr(backtest_module, "_score_window", fake_score_window)

    summary = backtest_module.run_strategy_backtest(
        strategy_name="momentum",
        from_iso="2026-01-01T00:00:00Z",
        to_iso="2026-01-05T00:00:00Z",
        symbols=["BTC"],
        timeframe="1h",
        database_url=database_url,
    )

    assert summary.metrics.trade_count == 3
    assert summary.metrics.total_pnl_usd > 0
    assert summary.provider_map == {"BTC": "stub"}

    with session_scope(database_url=database_url) as session:
        replay_run = session.scalars(
            select(ReplayRunRow).where(ReplayRunRow.id == summary.replay_run_id)
        ).one()
        replay_result = session.scalars(
            select(ReplayResultRow).where(ReplayResultRow.replay_run_id == summary.replay_run_id)
        ).one()

    assert replay_run.status == "completed"
    assert replay_result.output_json["metrics"]["trade_count"] == 3
