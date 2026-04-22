"""Dependency container and extension points for trading workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tools import HermesWorkflowTools, TradingWorkflowToolset


@dataclass(slots=True)
class TradingWorkflowDeps:
    """Runtime dependencies for the trading workflow graph.

    `runtime_backend` is intentionally local-only for now. The field exists to
    keep the graph contracts stable when durable runtimes such as Prefect,
    Temporal, or DBOS are introduced later.
    """

    tools: TradingWorkflowToolset = field(default_factory=HermesWorkflowTools)
    agent_model: Any | None = None
    use_pydantic_ai: bool = True
    deterministic_fallback: bool = True
    runtime_backend: str = "local"
