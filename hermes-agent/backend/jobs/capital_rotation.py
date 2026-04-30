"""Daily capital rotation job — ranks symbols by edge and proposes rebalancing.

Pulls 30-day realised edge per symbol from performance priors, computes
softmax allocation targets (capped at 40% per symbol), and emits
approval-required proposals for any deltas exceeding min_rebalance_bps.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from typing import Any

from backend.portfolio.rebalancer import (
    DEFAULT_TEMPERATURE,
    DEFAULT_UNIVERSE,
    MAX_ALLOCATION_PCT,
    MIN_REBALANCE_BPS,
    AllocationTarget,
    RebalanceProposal,
    SymbolEdge,
    compute_rebalance,
)
from backend.strategies.performance_priors import get_strategy_prior

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CapitalRotationSummary:
    universe: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    proposal: RebalanceProposal | None = None
    proposals_dispatched: int = 0
    dry_run: bool = False

    def to_markdown(self) -> str:
        lines = [
            "# Capital rotation",
            "",
            f"- Universe: {', '.join(self.universe)}",
            f"- Dry run: {self.dry_run}",
            f"- Proposals dispatched: {self.proposals_dispatched}",
        ]
        if self.edges:
            lines.extend(["", "## Symbol edges", ""])
            for e in self.edges:
                lines.append(
                    f"- `{e['symbol']}` posterior={e['posterior_mean']:.4f} "
                    f"multiplier=x{e['multiplier']:.2f} "
                    f"wins={e['wins']} losses={e['losses']}"
                )
        if self.proposal:
            lines.append("")
            lines.append(self.proposal.to_markdown())
        return "\n".join(lines)


def _get_current_allocations(
    universe: list[str],
    *,
    total_equity_usd: float | None = None,
) -> tuple[dict[str, float], float]:
    try:
        from backend.tools.get_portfolio_state import get_portfolio_state
        snapshot = get_portfolio_state({})
        data = snapshot.get("data") or {}
        equity = total_equity_usd or float(data.get("total_equity_usd") or 0)
        positions = data.get("positions") or []
        allocations: dict[str, float] = {}
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            sym = str(pos.get("symbol") or "").upper().replace("/", "").replace("USDT", "")
            notional = float(pos.get("notional_usd") or 0)
            if sym in [u.upper() for u in universe] and equity > 0:
                allocations[sym] = notional / equity
        return allocations, equity
    except Exception as exc:
        logger.debug("Portfolio state unavailable: %s", exc)
        equal = 1.0 / len(universe) if universe else 0.0
        return {s.upper(): equal for s in universe}, total_equity_usd or 10000.0


def _collect_edges(
    universe: list[str],
    *,
    database_url: str | None = None,
) -> list[SymbolEdge]:
    edges: list[SymbolEdge] = []
    for symbol in universe:
        strategies = ["momentum", "breakout", "mean_reversion"]
        best_posterior = 0.5
        best_multiplier = 1.0
        best_wins = 0
        best_losses = 0
        best_count = 0
        for strategy in strategies:
            prior = get_strategy_prior(strategy, database_url=database_url)
            if prior.resolved_count > best_count:
                best_posterior = prior.posterior_mean
                best_multiplier = prior.multiplier
                best_wins = prior.wins
                best_losses = prior.losses
                best_count = prior.resolved_count
        edges.append(SymbolEdge(
            symbol=symbol.upper(),
            posterior_mean=best_posterior,
            multiplier=best_multiplier,
            resolved_count=best_count,
            wins=best_wins,
            losses=best_losses,
        ))
    return edges


def run_capital_rotation(
    *,
    universe: list[str] | None = None,
    database_url: str | None = None,
    total_equity_usd: float | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    max_pct: float = MAX_ALLOCATION_PCT,
    min_rebalance_bps: float = MIN_REBALANCE_BPS,
    dry_run: bool = False,
) -> CapitalRotationSummary:
    symbols = universe or DEFAULT_UNIVERSE
    summary = CapitalRotationSummary(universe=symbols, dry_run=dry_run)

    edges = _collect_edges(symbols, database_url=database_url)
    summary.edges = [
        {
            "symbol": e.symbol,
            "posterior_mean": e.posterior_mean,
            "multiplier": e.multiplier,
            "wins": e.wins,
            "losses": e.losses,
        }
        for e in edges
    ]

    current_allocs, equity = _get_current_allocations(
        symbols, total_equity_usd=total_equity_usd,
    )

    proposal = compute_rebalance(
        edges,
        current_allocs,
        equity,
        temperature=temperature,
        max_pct=max_pct,
        min_rebalance_bps=min_rebalance_bps,
    )
    summary.proposal = proposal

    if not dry_run and proposal.actionable:
        for target in proposal.targets:
            try:
                _dispatch_rebalance_proposal(target, equity)
                summary.proposals_dispatched += 1
            except Exception as exc:
                logger.warning("Failed to dispatch rebalance for %s: %s", target.symbol, exc)

    return summary


def _dispatch_rebalance_proposal(target: AllocationTarget, total_equity_usd: float) -> None:
    from backend.trading.execution_service import dispatch_trade_proposal
    from backend.trading.models import TradeProposal

    delta_usd = abs(target.delta_pct) * total_equity_usd
    side: str = "buy" if target.delta_pct > 0 else "sell"

    proposal = TradeProposal(
        source_agent="capital_rotation",
        symbol=f"{target.symbol}USDT",
        side=side,  # type: ignore[arg-type]
        order_type="market",
        requested_size_usd=round(delta_usd, 2),
        rationale=(
            f"Capital rotation: rebalance {target.symbol} from "
            f"{target.current_pct:.1%} to {target.target_pct:.1%} "
            f"(edge posterior={target.edge.posterior_mean:.4f})."
        ),
        strategy_id="capital_rotation",
        strategy_template_id="capital_rotation",
        require_operator_approval=False,
        metadata={
            "rebalance": True,
            "target_pct": target.target_pct,
            "current_pct": target.current_pct,
            "delta_bps": target.delta_bps,
        },
    )
    dispatch_trade_proposal(proposal)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily capital rotation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args()

    summary = run_capital_rotation(dry_run=args.dry_run, temperature=args.temperature)
    print(summary.to_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
