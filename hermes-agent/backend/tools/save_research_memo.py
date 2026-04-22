"""save_research_memo — persist a research memo to the shared TimescaleDB/SQLite store."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import ResearchMemoRow
from backend.db.session import get_engine
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)

_PROVIDER = "hermes_research_store"


class SaveResearchMemoInput(BaseModel):
    symbol: str | None = Field(default=None, description="Asset symbol this memo applies to (e.g. 'BTC'). Omit for theme-level memos.")
    tags: list[str] = Field(default_factory=list, description="Topic tags for retrieval (e.g. ['momentum', 'rate_cuts']).")
    content: str = Field(..., min_length=1, description="Memo content — research notes, analysis, or observations.")
    source_agent: str = Field(default="hermes", description="Name/role of the agent creating the memo.")
    strategy_ref: str | None = Field(default=None, description="Optional strategy name this memo is linked to.")
    supersedes: str | None = Field(default=None, description="Optional memo ID that this new memo supersedes/replaces.")


def save_research_memo(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(SaveResearchMemoInput, payload)

        engine = get_engine()
        ensure_time_series_schema(engine)

        now = datetime.now(UTC)
        row = ResearchMemoRow(
            memo_time=now,
            symbol=args.symbol,
            tags=args.tags or [],
            content=args.content,
            source_agent=args.source_agent,
            strategy_ref=args.strategy_ref,
            superseded_by=None,
        )

        with session_scope() as session:
            session.add(row)
            # Mark the superseded memo if provided
            if args.supersedes:
                try:
                    old = session.get(ResearchMemoRow, args.supersedes)
                    if old is not None:
                        old.superseded_by = row.id
                except Exception as exc:
                    logger.warning("save_research_memo: could not mark superseded memo: %s", exc)

        return envelope(
            "save_research_memo",
            [provider_ok(_PROVIDER)],
            {
                "id": row.id,
                "symbol": row.symbol,
                "tags": row.tags,
                "source_agent": row.source_agent,
                "strategy_ref": row.strategy_ref,
                "memo_time": now.isoformat(),
            },
        )

    return run_tool("save_research_memo", _run)
