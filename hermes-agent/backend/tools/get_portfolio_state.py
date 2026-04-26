from __future__ import annotations

import os
from datetime import timezone

from pydantic import BaseModel, Field

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.integrations.base import IntegrationError
from backend.integrations.execution import reconcile_exchange_balances
from backend.models import PortfolioState
from backend.tools._helpers import envelope, run_tool, validate


class GetPortfolioStateInput(BaseModel):
    # Passive portfolio reads should return the latest persisted snapshot without
    # also probing live exchange credentials. Callers that want live venue
    # reconciliation must request it explicitly.
    include_exchange_balances: bool = False
    venue: str | None = Field(default=None, min_length=2, max_length=32)
    venues: list[str] | None = None


def get_portfolio_state(payload: dict | None = None) -> dict:
    def _run() -> dict:
        raw_payload = payload or {}
        args = validate(GetPortfolioStateInput, raw_payload)
        account_id = os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")
        ensure_time_series_schema(get_engine())
        with session_scope() as session:
            snapshot = HermesTimeSeriesRepository(session).get_latest_portfolio_snapshot(account_id=account_id)

        state = PortfolioState(account_id=account_id)
        if snapshot is not None:
            state = PortfolioState(
                account_id=snapshot.account_id,
                total_equity_usd=snapshot.total_equity_usd,
                cash_usd=snapshot.cash_usd,
                exposure_usd=snapshot.exposure_usd,
                positions=snapshot.positions or [],
                updated_at=snapshot.snapshot_time.astimezone(timezone.utc).isoformat(),
            )
            warnings: list[str] = []
        else:
            warnings = ["Portfolio adapter not yet wired to exchange/account backend."]
        data = state.model_dump(mode="json")
        reconciliation_explicitly_requested = (
            "include_exchange_balances" in raw_payload
            or args.venue is not None
            or bool(args.venues)
        )
        # Warning semantics:
        # - If a persisted snapshot exists, a bare get_portfolio_state() call is a
        #   passive read and must stay quiet.
        # - Reconciliation/live venue inspection only runs when explicitly
        #   requested, or when no snapshot exists and the tool must fall back to
        #   live venue inspection to provide fresher data.
        should_reconcile = bool(
            args.venue is not None
            or args.venues
            or (reconciliation_explicitly_requested and args.include_exchange_balances)
            or snapshot is None
        )
        if should_reconcile:
            try:
                reconciliation = reconcile_exchange_balances(venue=args.venue, venues=args.venues)
                data["reconciliation"] = reconciliation
                data["venues"] = reconciliation.get("configured_venues", [])
                warnings.extend(reconciliation.get("warnings") or [])
            except IntegrationError as exc:
                warnings.append(str(exc))
        return envelope("get_portfolio_state", [], data, warnings=warnings)

    return run_tool("get_portfolio_state", _run)
