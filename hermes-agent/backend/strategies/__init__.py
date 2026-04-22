"""Strategy library for Hermes trading agent — named strategies with per-strategy scoring."""

from backend.strategies.registry import STRATEGY_REGISTRY, StrategyDefinition, ScoredCandidate

__all__ = ["STRATEGY_REGISTRY", "StrategyDefinition", "ScoredCandidate"]
# Note: BOT_RUNNER_REGISTRY is in backend.strategies.runners (imported lazily to avoid
# circular imports through backend.trading.bot_runner).
