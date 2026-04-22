"""get_research_memos — retrieve persisted research memos from the shared store."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import ResearchMemoRow
from backend.db.session import get_engine
from backend.tools._helpers import envelope, provider_ok, run_tool, validate

logger = logging.getLogger(__name__)

_PROVIDER = "hermes_research_store"


class GetResearchMemosInput(BaseModel):
    symbol: str | None = Field(default=None, description="Filter by asset symbol (e.g. 'BTC').")
    tags: list[str] = Field(default_factory=list, description="OR-match on tags — returns memos with any of these tags.")
    strategy_ref: str | None = Field(default=None, description="Filter by strategy name reference.")
    include_superseded: bool = Field(default=False, description="If true, include memos that have been superseded.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of memos to return.")
    since_hours: int = Field(default=168, ge=1, description="Only return memos from the last N hours (default 168 = 7 days).")


def get_research_memos(payload: dict) -> dict:
    def _run() -> dict:
        args = validate(GetResearchMemosInput, payload)

        engine = get_engine()
        ensure_time_series_schema(engine)

        since_dt = datetime.now(UTC) - timedelta(hours=args.since_hours)
        results: list[dict] = []

        with session_scope() as session:
            stmt = select(ResearchMemoRow).where(ResearchMemoRow.memo_time >= since_dt)

            if args.symbol:
                stmt = stmt.where(ResearchMemoRow.symbol == args.symbol.upper())

            if args.strategy_ref:
                stmt = stmt.where(ResearchMemoRow.strategy_ref == args.strategy_ref)

            if not args.include_superseded:
                stmt = stmt.where(ResearchMemoRow.superseded_by.is_(None))

            stmt = stmt.order_by(ResearchMemoRow.memo_time.desc()).limit(args.limit)

            rows = session.execute(stmt).scalars().all()

            for row in rows:
                # Tag filter — OR match (skip rows that don't match any requested tag)
                if args.tags:
                    row_tags = [t.lower() for t in (row.tags or [])]
                    if not any(t.lower() in row_tags for t in args.tags):
                        continue
                results.append({
                    "id": row.id,
                    "symbol": row.symbol,
                    "tags": row.tags,
                    "content": row.content,
                    "source_agent": row.source_agent,
                    "strategy_ref": row.strategy_ref,
                    "superseded_by": row.superseded_by,
                    "memo_time": row.memo_time.isoformat() if row.memo_time else None,
                })

        return envelope(
            "get_research_memos",
            [provider_ok(_PROVIDER)],
            {"memos": results, "count": len(results)},
        )

    return run_tool("get_research_memos", _run)
