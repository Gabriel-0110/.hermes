"""Schema/bootstrap helpers for Hermes shared time-series storage."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .base import Base

HYPERTABLE_SPECS: tuple[tuple[str, str], ...] = (
    ("tradingview_alert_events", "event_time"),
    ("tradingview_internal_events", "event_time"),
    ("agent_signals", "signal_time"),
    ("portfolio_snapshots", "snapshot_time"),
    ("risk_events", "event_time"),
    ("notifications_sent", "sent_time"),
    ("workflow_runs", "created_at"),
    ("workflow_steps", "created_at"),
    ("tool_calls", "created_at"),
    ("agent_decisions", "created_at"),
    ("execution_events", "created_at"),
    ("movement_journal", "movement_time"),
    ("system_errors", "created_at"),
    ("replay_cases", "created_at"),
    ("replay_runs", "created_at"),
    ("replay_results", "created_at"),
    ("evaluation_scores", "created_at"),
    ("regression_comparisons", "created_at"),
    ("research_memos", "memo_time"),
    ("strategy_evaluations", "eval_time"),
)

_BOOTSTRAPPED_URLS: set[str] = set()


def _is_postgres(engine: Engine) -> bool:
    return engine.dialect.name == "postgresql"


def ensure_time_series_schema(engine: Engine) -> None:
    cache_key = str(engine.url)
    if cache_key in _BOOTSTRAPPED_URLS:
        return

    if _is_postgres(engine):
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))

    Base.metadata.create_all(bind=engine)

    if _is_postgres(engine):
        with engine.begin() as conn:
            for table_name, time_column in HYPERTABLE_SPECS:
                conn.execute(
                    text(
                        f"""
                        SELECT create_hypertable(
                            '{table_name}',
                            by_range('{time_column}'),
                            if_not_exists => TRUE,
                            migrate_data => TRUE
                        )
                        """
                    )
                )

    _BOOTSTRAPPED_URLS.add(cache_key)


def list_managed_tables(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    return [table_name for table_name, _ in HYPERTABLE_SPECS if table_name in existing]


def list_hypertables(engine: Engine) -> list[str]:
    if not _is_postgres(engine):
        return []
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT hypertable_name
                FROM timescaledb_information.hypertables
                WHERE hypertable_name = ANY(:table_names)
                ORDER BY hypertable_name
                """
            ),
            {"table_names": [table_name for table_name, _ in HYPERTABLE_SPECS]},
        ).fetchall()
    return [row[0] for row in rows]
