"""Nightly strategy evaluation and Bayesian prior updates."""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import AgentSignalRow, ExecutionEventRow, PortfolioSnapshotRow, StrategyEvaluationRow, StrategyWeightOverrideRow
from backend.db.session import get_engine
from backend.strategies.performance_priors import clear_strategy_prior_cache, strategy_prior_from_pnls

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StrategyEvaluationUpdate:
    evaluation_id: str
    strategy_name: str
    symbol: str
    outcome: str
    pnl_pct: float
    proposal_id: str | None
    resolved_at: str
    prior_multiplier: float


@dataclass(slots=True)
class StrategyEvaluatorSummary:
    scanned_rows: int = 0
    updated_rows: int = 0
    skipped_rows: int = 0
    account_id: str | None = None
    updates: list[StrategyEvaluationUpdate] = field(default_factory=list)
    priors: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            "# Strategy evaluator",
            "",
            f"- Account: `{self.account_id or 'auto'}`",
            f"- Scanned rows: {self.scanned_rows}",
            f"- Updated rows: {self.updated_rows}",
            f"- Skipped rows: {self.skipped_rows}",
        ]

        if self.updates:
            lines.extend(["", "## Resolved signals", ""])
            for update in self.updates:
                lines.append(
                    f"- `{update.strategy_name}` `{update.symbol}` → **{update.outcome}** "
                    f"({update.pnl_pct * 100:.2f}% PnL, prior x{update.prior_multiplier:.2f})"
                )

        if self.priors:
            lines.extend(["", "## Strategy priors", ""])
            for strategy_name, prior in sorted(self.priors.items()):
                lines.append(
                    f"- `{strategy_name}` posterior={prior['posterior_mean']:.4f} "
                    f"multiplier=x{prior['multiplier']:.2f} "
                    f"wins={prior['wins']} losses={prior['losses']}"
                )

        if not self.updates:
            lines.extend(["", "No unresolved strategy evaluations were updated."])

        return "\n".join(lines)


def run_strategy_evaluator(
    *,
    database_url: str | None = None,
    account_id: str | None = None,
    lookback_hours: int = 72,
) -> StrategyEvaluatorSummary:
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=max(1, lookback_hours))
    account = account_id or os.getenv("TRADING_PORTFOLIO_ACCOUNT_ID") or "paper"
    summary = StrategyEvaluatorSummary(account_id=account)

    ensure_time_series_schema(get_engine(database_url=database_url))
    with session_scope(database_url=database_url) as session:
        eval_rows = list(
            session.scalars(
                select(StrategyEvaluationRow)
                .where(StrategyEvaluationRow.eval_time >= cutoff)
                .order_by(desc(StrategyEvaluationRow.eval_time))
            )
        )
        signal_rows = list(
            session.scalars(
                select(AgentSignalRow)
                .where(AgentSignalRow.signal_time >= cutoff - timedelta(hours=6))
                .order_by(desc(AgentSignalRow.signal_time))
            )
        )
        execution_rows = list(
            session.scalars(
                select(ExecutionEventRow)
                .where(ExecutionEventRow.created_at >= cutoff - timedelta(hours=6))
                .order_by(desc(ExecutionEventRow.created_at))
            )
        )
        snapshot_query = select(PortfolioSnapshotRow).where(
            PortfolioSnapshotRow.snapshot_time >= cutoff - timedelta(days=7)
        )
        if account:
            snapshot_query = snapshot_query.where(PortfolioSnapshotRow.account_id == account)
        snapshot_rows = list(session.scalars(snapshot_query.order_by(desc(PortfolioSnapshotRow.snapshot_time))))

        summary.scanned_rows = len(eval_rows)
        signals_by_proposal = _index_signals_by_proposal(signal_rows)
        executions_by_proposal = _index_executions_by_proposal(execution_rows)
        touched_by_strategy: dict[str, list[StrategyEvaluationRow]] = defaultdict(list)

        for row in eval_rows:
            if row.resolved_at is not None and row.pnl_pct is not None:
                summary.skipped_rows += 1
                continue

            signal = _match_signal(row, signal_rows, signals_by_proposal)
            proposal_id = _proposal_id_from_evaluation(row) or (_proposal_id_from_signal(signal) if signal else None)
            execution = _match_execution_event(proposal_id, signal, execution_rows, executions_by_proposal)
            snapshot = _match_snapshot(snapshot_rows, symbol=row.symbol, after_time=execution.created_at if execution is not None else row.eval_time)

            pnl_pct, outcome, resolved_at = _resolve_row_outcome(row, execution=execution, snapshot=snapshot)
            if outcome is None or resolved_at is None:
                summary.skipped_rows += 1
                continue

            row.outcome = outcome
            row.pnl_pct = round(pnl_pct, 6)
            row.resolved_at = resolved_at
            row.metadata_json = {
                **(row.metadata_json or {}),
                "proposal_id": proposal_id,
                "matched_signal_id": signal.id if signal is not None else None,
                "matched_execution_event_id": execution.id if execution is not None else None,
                "matched_snapshot_time": snapshot.snapshot_time.astimezone(UTC).isoformat() if snapshot is not None else None,
                "evaluation_mode": "portfolio_snapshot_mark_to_market" if snapshot is not None else "execution_status_only",
            }
            touched_by_strategy[row.strategy_name].append(row)

        if touched_by_strategy:
            session.flush()

        for strategy_name, rows in touched_by_strategy.items():
            resolved_rows = list(
                session.scalars(
                    select(StrategyEvaluationRow)
                    .where(StrategyEvaluationRow.strategy_name == strategy_name)
                    .where(StrategyEvaluationRow.resolved_at.is_not(None))
                    .where(StrategyEvaluationRow.pnl_pct.is_not(None))
                    .order_by(desc(StrategyEvaluationRow.resolved_at))
                    .limit(200)
                )
            )
            pnl_values = [float(resolved.pnl_pct) for resolved in resolved_rows if resolved.pnl_pct is not None]
            as_of = None
            if resolved_rows and resolved_rows[0].resolved_at is not None:
                as_of = resolved_rows[0].resolved_at.astimezone(UTC).isoformat()
            prior = strategy_prior_from_pnls(strategy_name, pnl_values, as_of=as_of)
            prior_payload = {
                "alpha": prior.alpha,
                "beta": prior.beta,
                "posterior_mean": prior.posterior_mean,
                "multiplier": prior.multiplier,
                "resolved_count": prior.resolved_count,
                "wins": prior.wins,
                "losses": prior.losses,
                "as_of": prior.as_of,
            }
            summary.priors[strategy_name] = prior_payload
            for row in rows:
                row.metadata_json = {**(row.metadata_json or {}), "strategy_prior": prior_payload}
                summary.updates.append(
                    StrategyEvaluationUpdate(
                        evaluation_id=row.id,
                        strategy_name=row.strategy_name,
                        symbol=row.symbol,
                        outcome=row.outcome or "unknown",
                        pnl_pct=float(row.pnl_pct or 0.0),
                        proposal_id=(row.metadata_json or {}).get("proposal_id"),
                        resolved_at=row.resolved_at.astimezone(UTC).isoformat() if row.resolved_at is not None else now.isoformat(),
                        prior_multiplier=prior.multiplier,
                    )
                )

        summary.updated_rows = len(summary.updates)
        summary.skipped_rows = max(summary.skipped_rows, summary.scanned_rows - summary.updated_rows)

        for strategy_name, prior_payload in summary.priors.items():
            weight = round(max(0.1, min(3.0, prior_payload["multiplier"])), 4)
            existing = session.scalars(
                select(StrategyWeightOverrideRow)
                .where(StrategyWeightOverrideRow.strategy == strategy_name)
                .where(StrategyWeightOverrideRow.symbol == "*")
                .where(StrategyWeightOverrideRow.regime == "*")
                .limit(1)
            ).first()
            if existing is not None:
                existing.weight = weight
                existing.evidence_json = prior_payload
                existing.updated_at = now
            else:
                session.add(StrategyWeightOverrideRow(
                    strategy=strategy_name,
                    symbol="*",
                    regime="*",
                    weight=weight,
                    evidence_json=prior_payload,
                    updated_at=now,
                ))

    clear_strategy_prior_cache()
    return summary


def main() -> int:
    summary = run_strategy_evaluator()
    print(summary.to_markdown())
    return 0


def _index_signals_by_proposal(signals: list[AgentSignalRow]) -> dict[str, list[AgentSignalRow]]:
    indexed: dict[str, list[AgentSignalRow]] = defaultdict(list)
    for signal in signals:
        proposal_id = _proposal_id_from_signal(signal)
        if proposal_id:
            indexed[proposal_id].append(signal)
    return indexed


def _index_executions_by_proposal(events: list[ExecutionEventRow]) -> dict[str, list[ExecutionEventRow]]:
    indexed: dict[str, list[ExecutionEventRow]] = defaultdict(list)
    for event in events:
        proposal_id = _proposal_id_from_execution(event)
        if proposal_id:
            indexed[proposal_id].append(event)
    return indexed


def _proposal_id_from_evaluation(row: StrategyEvaluationRow) -> str | None:
    metadata = row.metadata_json or {}
    return metadata.get("proposal_id") if isinstance(metadata, dict) else None


def _proposal_id_from_signal(signal: AgentSignalRow | None) -> str | None:
    if signal is None:
        return None
    payload = signal.payload or {}
    if isinstance(payload, dict):
        return payload.get("proposal_id")
    return None


def _proposal_id_from_execution(event: ExecutionEventRow) -> str | None:
    metadata = event.metadata_json or {}
    if isinstance(metadata, dict) and metadata.get("proposal_id"):
        return str(metadata.get("proposal_id"))
    request = _execution_request_from_event(event)
    if isinstance(request, dict) and request.get("proposal_id"):
        return str(request.get("proposal_id"))
    return None


def _match_signal(
    row: StrategyEvaluationRow,
    signals: list[AgentSignalRow],
    signals_by_proposal: dict[str, list[AgentSignalRow]],
) -> AgentSignalRow | None:
    proposal_id = _proposal_id_from_evaluation(row)
    if proposal_id and signals_by_proposal.get(proposal_id):
        return sorted(signals_by_proposal[proposal_id], key=lambda item: item.signal_time)[-1]

    strategy_name = row.strategy_name
    candidates = [
        signal
        for signal in signals
        if (signal.symbol or "") == row.symbol
        and (signal.direction or "") == row.direction
        and ((signal.signal_type or "") == strategy_name or (signal.payload or {}).get("strategy_name") == strategy_name)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda signal: abs((signal.signal_time - row.eval_time).total_seconds()))


def _match_execution_event(
    proposal_id: str | None,
    signal: AgentSignalRow | None,
    executions: list[ExecutionEventRow],
    executions_by_proposal: dict[str, list[ExecutionEventRow]],
) -> ExecutionEventRow | None:
    if proposal_id and executions_by_proposal.get(proposal_id):
        return sorted(executions_by_proposal[proposal_id], key=_execution_priority, reverse=True)[0]

    correlation_id = None
    if signal is not None and isinstance(signal.payload, dict):
        correlation_id = signal.payload.get("proposal_id") or signal.payload.get("correlation_id")
    if not correlation_id:
        return None
    matched = [event for event in executions if event.correlation_id == correlation_id]
    if not matched:
        return None
    return sorted(matched, key=_execution_priority, reverse=True)[0]


def _match_snapshot(
    snapshots: list[PortfolioSnapshotRow],
    *,
    symbol: str,
    after_time: datetime,
) -> PortfolioSnapshotRow | None:
    latest_any: PortfolioSnapshotRow | None = None
    for snapshot in snapshots:
        if snapshot.snapshot_time < after_time:
            continue
        latest_any = latest_any or snapshot
        if _snapshot_position(snapshot, symbol) is not None:
            return snapshot
    return latest_any


def _resolve_row_outcome(
    row: StrategyEvaluationRow,
    *,
    execution: ExecutionEventRow | None,
    snapshot: PortfolioSnapshotRow | None,
) -> tuple[float, str | None, datetime | None]:
    if execution is not None and execution.status in {"blocked", "failed"}:
        outcome = "blocked" if execution.status == "blocked" else "failed"
        return 0.0, outcome, execution.created_at

    if snapshot is None:
        return 0.0, None, None

    position = _snapshot_position(snapshot, row.symbol)
    entry_price = None
    if execution is not None:
        request = _execution_request_from_event(execution)
        if isinstance(request, dict) and request.get("price") is not None:
            try:
                entry_price = float(request.get("price"))
            except (TypeError, ValueError):
                entry_price = None

    pnl_pct = _position_pnl_pct(position, direction=row.direction, entry_price=entry_price)
    if pnl_pct is None:
        return 0.0, None, None

    if pnl_pct > 0.002:
        outcome = "win"
    elif pnl_pct < -0.002:
        outcome = "loss"
    else:
        outcome = "flat"
    return pnl_pct, outcome, snapshot.snapshot_time


def _execution_priority(event: ExecutionEventRow) -> tuple[int, datetime]:
    if event.event_type == "order_placed" and event.status in {"filled", "paper_filled"}:
        return (4, event.created_at)
    if event.event_type == "order_failed" or event.status == "failed":
        return (3, event.created_at)
    if event.event_type == "order_blocked" or event.status == "blocked":
        return (2, event.created_at)
    if event.event_type and event.event_type.startswith("trade_proposal_"):
        return (1, event.created_at)
    return (0, event.created_at)


def _execution_request_from_event(event: ExecutionEventRow) -> dict[str, Any]:
    payload = _safe_json_load(event.summarized_input)
    if isinstance(payload, dict):
        request = payload.get("execution_request")
        if isinstance(request, dict):
            return request
    metadata = event.metadata_json or {}
    if isinstance(metadata, dict):
        nested = metadata.get("payload")
        if isinstance(nested, dict) and isinstance(nested.get("execution_request"), dict):
            return nested.get("execution_request")
    return {}


def _snapshot_position(snapshot: PortfolioSnapshotRow, symbol: str) -> dict[str, Any] | None:
    for position in snapshot.positions or []:
        if isinstance(position, dict) and str(position.get("symbol") or "").upper() == symbol.upper():
            return position
    return None


def _position_pnl_pct(
    position: dict[str, Any] | None,
    *,
    direction: str,
    entry_price: float | None,
) -> float | None:
    if not isinstance(position, dict):
        return None

    avg_entry = _to_float(position.get("avg_entry")) or entry_price
    mark_price = _to_float(position.get("mark_price"))
    if avg_entry and mark_price and avg_entry > 0:
        raw = (mark_price - avg_entry) / avg_entry
        return raw if direction == "long" else -raw

    pnl_unrealized = _to_float(position.get("pnl_unrealized"))
    quantity = _to_float(position.get("quantity"))
    if pnl_unrealized is not None and quantity not in (None, 0.0) and avg_entry not in (None, 0.0):
        base_notional = abs(quantity) * avg_entry
        if base_notional > 0:
            raw = pnl_unrealized / base_notional
            return raw if direction == "long" else -raw

    return None


def _safe_json_load(text: str | None) -> dict[str, Any]:
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())