"""Post-trade learning loop — updates strategy weight overrides from evaluator output.

Reads closed-trade evaluations, computes Bayesian-updated weights per
(strategy, symbol, regime) triple, and persists them to the
strategy_weight_overrides table. Idempotent within a calendar day.

Weight clamp: [0.1, 3.0].
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select

from backend.db import ensure_time_series_schema, session_scope
from backend.db.models import StrategyEvaluationRow, StrategyWeightOverrideRow
from backend.db.session import get_engine
from backend.strategies.performance_priors import strategy_prior_from_pnls

logger = logging.getLogger(__name__)

WEIGHT_MIN = 0.1
WEIGHT_MAX = 3.0


@dataclass(slots=True)
class LearningLoopSummary:
    strategies_processed: int = 0
    overrides_written: int = 0
    overrides_unchanged: int = 0
    dry_run: bool = False
    overrides: list[dict[str, Any]] = field(default_factory=list)

    def to_markdown(self) -> str:
        lines = [
            "# Learning loop",
            "",
            f"- Dry run: {self.dry_run}",
            f"- Strategies processed: {self.strategies_processed}",
            f"- Overrides written: {self.overrides_written}",
            f"- Overrides unchanged: {self.overrides_unchanged}",
        ]
        if self.overrides:
            lines.extend(["", "## Weight overrides", ""])
            for o in self.overrides:
                lines.append(
                    f"- `{o['strategy']}` symbol={o['symbol']} regime={o['regime']} "
                    f"weight={o['weight']:.4f} (wins={o.get('wins', '?')}, losses={o.get('losses', '?')})"
                )
        if not self.overrides:
            lines.extend(["", "No weight overrides were updated."])
        return "\n".join(lines)


def clamp_weight(value: float) -> float:
    return round(max(WEIGHT_MIN, min(WEIGHT_MAX, value)), 4)


def run_learning_loop(
    *,
    database_url: str | None = None,
    dry_run: bool = False,
    lookback_days: int = 30,
) -> LearningLoopSummary:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=max(1, lookback_days))
    summary = LearningLoopSummary(dry_run=dry_run)

    ensure_time_series_schema(get_engine(database_url=database_url))

    with session_scope(database_url=database_url) as session:
        resolved_rows = list(
            session.scalars(
                select(StrategyEvaluationRow)
                .where(StrategyEvaluationRow.resolved_at.is_not(None))
                .where(StrategyEvaluationRow.pnl_pct.is_not(None))
                .where(StrategyEvaluationRow.resolved_at >= cutoff)
                .order_by(desc(StrategyEvaluationRow.resolved_at))
            )
        )

        groups: dict[str, list[float]] = {}
        for row in resolved_rows:
            key = row.strategy_name
            if key not in groups:
                groups[key] = []
            if row.pnl_pct is not None:
                groups[key].append(float(row.pnl_pct))

        summary.strategies_processed = len(groups)

        for strategy_name, pnl_values in groups.items():
            prior = strategy_prior_from_pnls(strategy_name, pnl_values)
            weight = clamp_weight(prior.multiplier)

            evidence = {
                "alpha": prior.alpha,
                "beta": prior.beta,
                "posterior_mean": prior.posterior_mean,
                "raw_multiplier": prior.multiplier,
                "clamped_weight": weight,
                "resolved_count": prior.resolved_count,
                "wins": prior.wins,
                "losses": prior.losses,
                "computed_at": now.isoformat(),
            }

            override_info = {
                "strategy": strategy_name,
                "symbol": "*",
                "regime": "*",
                "weight": weight,
                "wins": prior.wins,
                "losses": prior.losses,
            }
            summary.overrides.append(override_info)

            if dry_run:
                summary.overrides_written += 1
                continue

            existing = session.scalars(
                select(StrategyWeightOverrideRow)
                .where(StrategyWeightOverrideRow.strategy == strategy_name)
                .where(StrategyWeightOverrideRow.symbol == "*")
                .where(StrategyWeightOverrideRow.regime == "*")
                .limit(1)
            ).first()

            if existing is not None:
                if abs(existing.weight - weight) < 0.0001:
                    summary.overrides_unchanged += 1
                    continue
                existing.weight = weight
                existing.evidence_json = evidence
                existing.updated_at = now
            else:
                session.add(StrategyWeightOverrideRow(
                    strategy=strategy_name,
                    symbol="*",
                    regime="*",
                    weight=weight,
                    evidence_json=evidence,
                    updated_at=now,
                ))
            summary.overrides_written += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-trade learning loop")
    parser.add_argument("--dry-run", action="store_true", help="Compute weights without writing to DB")
    parser.add_argument("--lookback-days", type=int, default=30, help="Days of history to consider")
    args = parser.parse_args()

    summary = run_learning_loop(dry_run=args.dry_run, lookback_days=args.lookback_days)
    print(summary.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
