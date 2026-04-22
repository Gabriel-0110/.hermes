# Workflow Architecture

The typed workflow layer lives under `backend/workflows/` and is intentionally isolated from existing Hermes integrations. The graph owns orchestration, branching, and output validation; the existing internal Hermes tools still own research, storage, notifications, and execution-adjacent data access.

## Design

- `backend/workflows/models.py` defines the stable contracts for:
  - `TradingInputEvent`
  - `TradingWorkflowState`
  - `ResearcherOutput`
  - `StrategyOutput`
  - `RiskOutput`
  - `OrchestratorOutput`
- `backend/workflows/tools.py` wraps existing Hermes tools and normalizes their envelopes into workflow-safe `WorkflowToolResult` objects.
- `backend/workflows/agents.py` uses `pydantic_ai.Agent` for typed node outputs. In local validation mode it uses `TestModel`, so schema validation still runs even without live model credentials.
- `backend/workflows/graph.py` defines the graph itself with explicit nodes and branch labels.
- `backend/workflows/validate.py` runs a sample event through the graph and prints the final state.

## Execution Model

The v1 workflow uses local graph execution only:

1. `IngestSignalNode`
2. `MarketResearchNode`
3. `StrategyPlanningNode`
4. `RiskReviewNode`
5. `FinalOrchestrationDecisionNode`

Branch gates are explicit and typed:

- `reject`
- `continue`
- `execute`

Research aggregation is the only place where parallel fan-out is used in v1. The graph remains otherwise linear and easy to inspect.

## Durable Runtime Extension Points

Durable execution is out of scope in this step, but the contracts leave room for it:

- `TradingWorkflowDeps.runtime_backend` is pinned to `local` today.
- `TradingWorkflowState.extension_points` reserves fields for:
  - Prefect flow IDs
  - Temporal workflow names
  - DBOS workflow identifiers
  - resume tokens

That means a future durable runtime can wrap the graph without changing the trading-node contracts.
