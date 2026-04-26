"""Portfolio rebalancer — softmax allocation with per-symbol cap.

Ranks symbols by realised edge from performance priors, applies a softmax
to convert edges into allocation weights, caps each symbol at a configurable
maximum, and renormalises. Returns proposed deltas relative to current
allocations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


DEFAULT_UNIVERSE = ["BTC", "ETH", "SOL", "XRP"]
MAX_ALLOCATION_PCT = 0.40
MIN_REBALANCE_BPS = 50.0
DEFAULT_TEMPERATURE = 1.0


@dataclass(frozen=True, slots=True)
class SymbolEdge:
    symbol: str
    posterior_mean: float
    multiplier: float
    resolved_count: int
    wins: int
    losses: int


@dataclass(frozen=True, slots=True)
class AllocationTarget:
    symbol: str
    target_pct: float
    current_pct: float
    delta_pct: float
    delta_bps: float
    edge: SymbolEdge


@dataclass(slots=True)
class RebalanceProposal:
    total_equity_usd: float
    targets: list[AllocationTarget] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    actionable: bool = False

    def to_markdown(self) -> str:
        lines = [
            "# Capital rotation proposal",
            "",
            f"- Total equity: ${self.total_equity_usd:,.2f}",
            f"- Actionable: {self.actionable}",
        ]
        if self.targets:
            lines.extend(["", "## Targets", ""])
            for t in self.targets:
                lines.append(
                    f"- `{t.symbol}` target={t.target_pct:.1%} current={t.current_pct:.1%} "
                    f"delta={t.delta_pct:+.1%} ({t.delta_bps:+.0f} bps)"
                )
        if self.skipped:
            lines.extend(["", "## Skipped (below min delta)", ""])
            for s in self.skipped:
                lines.append(f"- `{s['symbol']}` delta={s['delta_bps']:.0f} bps < {MIN_REBALANCE_BPS}")
        return "\n".join(lines)


def softmax_allocations(
    edges: list[SymbolEdge],
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_pct: float = MAX_ALLOCATION_PCT,
) -> dict[str, float]:
    if not edges:
        return {}

    scores = [e.posterior_mean / max(temperature, 0.01) for e in edges]
    max_score = max(scores)
    exp_scores = [math.exp(s - max_score) for s in scores]
    total = sum(exp_scores)
    raw = {e.symbol: exp_s / total for e, exp_s in zip(edges, exp_scores)}

    capped = _cap_and_renormalize(raw, max_pct)
    return capped


def _cap_and_renormalize(allocations: dict[str, float], max_pct: float) -> dict[str, float]:
    for _ in range(10):
        excess = 0.0
        uncapped_sum = 0.0
        result: dict[str, float] = {}
        for symbol, pct in allocations.items():
            if pct > max_pct:
                result[symbol] = max_pct
                excess += pct - max_pct
            else:
                result[symbol] = pct
                uncapped_sum += pct

        if excess == 0.0:
            return result

        if uncapped_sum > 0:
            for symbol in result:
                if result[symbol] < max_pct:
                    result[symbol] += excess * (result[symbol] / uncapped_sum)
        allocations = result

    return allocations


def compute_rebalance(
    edges: list[SymbolEdge],
    current_allocations: dict[str, float],
    total_equity_usd: float,
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_pct: float = MAX_ALLOCATION_PCT,
    min_rebalance_bps: float = MIN_REBALANCE_BPS,
) -> RebalanceProposal:
    targets = softmax_allocations(edges, temperature=temperature, max_pct=max_pct)
    proposal = RebalanceProposal(total_equity_usd=total_equity_usd)

    edge_map = {e.symbol: e for e in edges}

    for symbol, target_pct in sorted(targets.items()):
        current_pct = current_allocations.get(symbol, 0.0)
        delta_pct = target_pct - current_pct
        delta_bps = abs(delta_pct) * 10_000

        alloc = AllocationTarget(
            symbol=symbol,
            target_pct=round(target_pct, 4),
            current_pct=round(current_pct, 4),
            delta_pct=round(delta_pct, 4),
            delta_bps=round(delta_bps, 2),
            edge=edge_map[symbol],
        )

        if delta_bps < min_rebalance_bps:
            proposal.skipped.append({
                "symbol": symbol,
                "delta_bps": delta_bps,
                "target_pct": target_pct,
                "current_pct": current_pct,
            })
        else:
            proposal.targets.append(alloc)

    proposal.actionable = len(proposal.targets) > 0
    return proposal
