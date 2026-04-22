"""Position monitoring helpers for the controlled execution pipeline."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from backend.db import HermesTimeSeriesRepository, ensure_time_series_schema, session_scope
from backend.db.session import get_engine
from backend.models import PortfolioAsset, PortfolioState
from backend.observability.service import get_observability_service
from backend.services.portfolio_sync import sync_portfolio_from_exchange
from backend.tools.get_portfolio_state import get_portfolio_state

from .models import (
    ExecutionOutcome,
    ExecutionRequest,
    ExecutionResult,
    PositionMonitorExecutionContext,
    PositionMonitorSnapshot,
    PositionRiskSummary,
    PositionStateLine,
)

logger = logging.getLogger(__name__)


def _account_id(account_id: str | None = None) -> str:
    return account_id or os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID", "paper")


def _load_latest_snapshot_row(account_id: str) -> Any | None:
    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        return HermesTimeSeriesRepository(session).get_latest_portfolio_snapshot(account_id=account_id)


def _portfolio_from_tool(account_id: str) -> PortfolioState:
    result = get_portfolio_state({})
    data = result.get("data") or {}
    if not data.get("account_id"):
        data["account_id"] = account_id
    return PortfolioState.model_validate(data)


def _snapshot_metadata(snapshot_row: Any | None, *, source: str) -> dict[str, Any]:
    metadata = dict(getattr(snapshot_row, "payload", None) or {})
    metadata.setdefault("source", source)
    metadata.setdefault(
        "snapshot_time",
        snapshot_row.snapshot_time.astimezone(UTC).isoformat() if snapshot_row is not None else None,
    )
    metadata.setdefault("account_id", getattr(snapshot_row, "account_id", None))
    metadata.setdefault("positions_count", len(getattr(snapshot_row, "positions", None) or []))
    return metadata


def _state_mode(snapshot_metadata: dict[str, Any], last_execution: PositionMonitorExecutionContext | None) -> str:
    mode = str(snapshot_metadata.get("execution_mode") or snapshot_metadata.get("mode") or "").lower()
    if mode in {"paper", "live"}:
        return mode
    if last_execution is not None and last_execution.execution_mode in {"paper", "live"}:
        return last_execution.execution_mode
    return "unknown"


def _summarize_portfolio(portfolio: PortfolioState) -> PositionRiskSummary:
    warnings: list[str] = []
    largest_symbol: str | None = None
    largest_notional: float | None = None

    for position in portfolio.positions:
        notional = position.notional_usd
        if notional is None:
            continue
        if largest_notional is None or notional > largest_notional:
            largest_notional = notional
            largest_symbol = position.symbol

    total_equity = portfolio.total_equity_usd or 0.0
    largest_weight = None
    gross_exposure_pct = None
    if portfolio.exposure_usd is not None and total_equity > 0:
        gross_exposure_pct = portfolio.exposure_usd / total_equity
        if gross_exposure_pct >= 0.9:
            warnings.append("Gross exposure exceeds 90% of total equity.")
    if largest_notional is not None and total_equity > 0:
        largest_weight = largest_notional / total_equity
        if largest_weight >= 0.5:
            warnings.append("Largest position exceeds 50% of total equity.")

    cash_buffer_pct = None
    if total_equity > 0 and portfolio.cash_usd is not None:
        cash_buffer_pct = portfolio.cash_usd / total_equity
        if cash_buffer_pct < 0.1:
            warnings.append("Cash buffer is below 10% of total equity.")

    return PositionRiskSummary(
        total_positions=len(portfolio.positions),
        largest_position_symbol=largest_symbol,
        largest_position_notional_usd=largest_notional,
        largest_position_weight=largest_weight,
        cash_buffer_pct=cash_buffer_pct,
        gross_exposure_pct=gross_exposure_pct,
        warnings=warnings,
    )


def _extract_last_execution_context(*, symbol: str | None = None) -> PositionMonitorExecutionContext | None:
    try:
        rows = get_observability_service().get_execution_event_history(limit=20)
    except Exception as exc:
        logger.warning("position_manager: failed to load execution history: %s", exc)
        return None

    for row in rows:
        if symbol and row.get("symbol") not in {None, symbol}:
            continue
        output = row.get("summarized_output") or {}
        payload = row.get("payload") or {}
        outcome = output.get("execution_outcome") or payload.get("execution_outcome")
        result = output.get("execution_result") or payload.get("execution_result")
        request = output.get("execution_request") or payload.get("execution_request")
        if isinstance(outcome, dict):
            request = outcome.get("request") or request
            result = outcome.get("result") or result
        if not isinstance(result, dict):
            continue
        request = request if isinstance(request, dict) else {}
        mode = str(result.get("execution_mode") or "").lower()
        return PositionMonitorExecutionContext(
            event_type=row.get("event_type") or "execution_event",
            status=row.get("status"),
            execution_mode=mode if mode in {"paper", "live"} else "unknown",
            symbol=result.get("symbol") or row.get("symbol"),
            request_id=request.get("request_id") or result.get("payload", {}).get("request_id"),
            idempotency_key=request.get("idempotency_key") or result.get("payload", {}).get("idempotency_key"),
            correlation_id=row.get("correlation_id"),
            workflow_id=row.get("workflow_run_id"),
            observed_at=row.get("created_at"),
        )
    return None


def _position_states(
    portfolio: PortfolioState,
    *,
    source: str,
    state_mode: str,
    last_execution: PositionMonitorExecutionContext | None,
) -> list[PositionStateLine]:
    states: list[PositionStateLine] = []
    for position in portfolio.positions:
        quantity = position.quantity
        if quantity > 0:
            side = "long"
        elif quantity < 0:
            side = "short"
        else:
            side = "flat"
        states.append(
            PositionStateLine(
                symbol=position.symbol,
                quantity=quantity,
                mark_price=position.mark_price,
                notional_usd=position.notional_usd,
                state="open" if abs(quantity) > 1e-12 else "closed",
                exposure_side=side,
                last_update_source=source,
                execution_mode=state_mode if state_mode in {"paper", "live"} else "unknown",
                updated_at=portfolio.updated_at,
                last_request_id=last_execution.request_id if last_execution and last_execution.symbol == position.symbol else None,
                last_correlation_id=last_execution.correlation_id if last_execution and last_execution.symbol == position.symbol else None,
            )
        )
    return states


def get_position_monitor_snapshot(
    *,
    account_id: str | None = None,
    refresh: bool = False,
) -> PositionMonitorSnapshot:
    effective_account_id = _account_id(account_id)
    if refresh:
        portfolio = sync_portfolio_from_exchange(account_id=effective_account_id)
        source = "live_sync"
        snapshot_row = _load_latest_snapshot_row(effective_account_id)
    else:
        portfolio = _portfolio_from_tool(effective_account_id)
        source = "persisted_snapshot"
        snapshot_row = _load_latest_snapshot_row(effective_account_id)

    last_execution = _extract_last_execution_context()
    snapshot_metadata = _snapshot_metadata(snapshot_row, source=source)
    state_mode = _state_mode(snapshot_metadata, last_execution)

    return PositionMonitorSnapshot(
        account_id=portfolio.account_id,
        portfolio=portfolio,
        risk_summary=_summarize_portfolio(portfolio),
        position_states=_position_states(
            portfolio,
            source=source,
            state_mode=state_mode,
            last_execution=last_execution,
        ),
        snapshot_metadata=snapshot_metadata,
        state_mode=state_mode,
        last_execution=last_execution,
        source=source,
    )


def _persist_portfolio_state(
    portfolio: PortfolioState,
    *,
    metadata: dict[str, Any],
) -> PortfolioState:
    ensure_time_series_schema(get_engine())
    with session_scope() as session:
        HermesTimeSeriesRepository(session).insert_portfolio_snapshot(
            account_id=portfolio.account_id,
            total_equity_usd=portfolio.total_equity_usd,
            cash_usd=portfolio.cash_usd,
            exposure_usd=portfolio.exposure_usd,
            positions=[item.model_dump(mode="json") for item in portfolio.positions],
            payload=metadata,
        )
    return portfolio


def _apply_paper_execution_to_portfolio(
    portfolio: PortfolioState,
    *,
    request: ExecutionRequest,
    result: ExecutionResult,
) -> PortfolioState:
    positions = {item.symbol: item.model_copy(deep=True) for item in portfolio.positions}
    existing = positions.get(request.symbol)
    existing_qty = existing.quantity if existing is not None else 0.0
    delta_qty = float(request.amount or 0.0)
    signed_delta = delta_qty if request.side == "buy" else -delta_qty
    new_qty = existing_qty + signed_delta

    mark_price = request.price
    if mark_price is None and existing is not None:
        mark_price = existing.mark_price

    notional_usd = request.size_usd
    if notional_usd is None and mark_price is not None:
        notional_usd = abs(new_qty) * mark_price

    if abs(new_qty) <= 1e-12:
        positions.pop(request.symbol, None)
    else:
        positions[request.symbol] = PortfolioAsset(
            symbol=request.symbol,
            quantity=new_qty,
            avg_entry=existing.avg_entry if existing is not None else request.price,
            mark_price=mark_price,
            notional_usd=notional_usd,
            pnl_unrealized=existing.pnl_unrealized if existing is not None else None,
        )

    cash_usd = portfolio.cash_usd
    if cash_usd is not None and request.size_usd is not None:
        cash_usd = cash_usd - request.size_usd if request.side == "buy" else cash_usd + request.size_usd

    positions_list = sorted(positions.values(), key=lambda item: item.symbol)
    exposure_usd = sum(item.notional_usd or 0.0 for item in positions_list) or None
    total_equity_usd = portfolio.total_equity_usd
    if cash_usd is not None:
        total_equity_usd = (cash_usd or 0.0) + (exposure_usd or 0.0)

    return PortfolioState(
        account_id=portfolio.account_id,
        total_equity_usd=total_equity_usd,
        cash_usd=cash_usd,
        exposure_usd=exposure_usd,
        positions=positions_list,
        updated_at=result.payload.get("updated_at") or datetime.now(UTC).isoformat(),
    )


def apply_execution_outcome_to_portfolio(
    outcome: ExecutionOutcome,
    *,
    account_id: str | None = None,
) -> PortfolioState | None:
    request = outcome.request
    result = outcome.result
    effective_account_id = _account_id(account_id)

    if not result.success:
        return None

    if result.execution_mode == "live":
        try:
            return sync_portfolio_from_exchange(account_id=effective_account_id)
        except Exception as exc:
            logger.warning(
                "position_manager: live execution sync failed for request_id=%s: %s",
                request.request_id,
                exc,
            )
            return None

    snapshot_row = _load_latest_snapshot_row(effective_account_id)
    base_portfolio = _portfolio_from_tool(effective_account_id)
    updated = _apply_paper_execution_to_portfolio(base_portfolio, request=request, result=result)
    return _persist_portfolio_state(
        updated,
        metadata={
            **(getattr(snapshot_row, "payload", None) or {}),
            "source": "execution_projection",
            "execution_mode": result.execution_mode,
            "derived_from_request_id": request.request_id,
            "derived_from_idempotency_key": request.idempotency_key,
            "derived_from_correlation_id": result.correlation_id,
            "positions_count": len(updated.positions),
        },
    )
