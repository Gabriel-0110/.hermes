"""list_strategies — return all registered strategy definitions."""

from __future__ import annotations

from backend.strategies.registry import STRATEGY_REGISTRY
from backend.tools._helpers import envelope, provider_ok, run_tool


def list_strategies(_: dict | None = None) -> dict:
    def _run() -> dict:
        strategies = [
            {
                "name": s.name,
                "strategy_type": s.strategy_type,
                "description": s.description,
                "version": s.version,
                "timeframes": s.timeframes,
                "universe_filter": s.universe_filter,
                "min_confidence": s.min_confidence,
            }
            for s in STRATEGY_REGISTRY.values()
        ]
        return envelope(
            "list_strategies",
            [provider_ok("hermes_strategy_registry")],
            {"strategies": strategies, "count": len(strategies)},
        )

    return run_tool("list_strategies", _run)
