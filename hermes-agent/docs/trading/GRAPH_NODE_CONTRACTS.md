# Graph Node Contracts

## Ingest Signal

- Input: `TradingInputEvent`
- Responsibilities:
  - validate minimum workflow requirements
  - reject events missing symbol or signal direction
  - initialize state trace
- Output branch:
  - `reject`
  - `continue`

## Market Research

- Agent mapping: `market_researcher`
- Responsibilities:
  - gather Hermes tool context
  - validate typed `ResearcherOutput`
  - attach evidence, catalysts, warnings, and raw context
- Output branch:
  - `reject`
  - `continue`

## Strategy Planning

- Agent mapping: `strategy_agent`
- Responsibilities:
  - translate research context into a typed trade plan
  - define action, size, thesis, invalidation, and reasons
- Output branch:
  - `reject`
  - `continue`

## Risk Review

- Agent mapping: `risk_manager`
- Responsibilities:
  - review proposed size and event-risk context
  - validate typed `RiskOutput`
  - determine whether the trade is blocked, manual-review, or execution-ready
- Output branch:
  - `reject`
  - `continue`
  - `execute`

## Final Orchestration Decision

- Agent mapping: `orchestrator_trader`
- Responsibilities:
  - convert the final workflow state into a typed `OrchestratorOutput`
  - prepare an execution intent without actually dispatching durable execution
  - preserve operator-facing audit data
- Output:
  - final `OrchestratorOutput`

## Optional Inputs

- `portfolio_monitor` is not a node in v1.
- It is treated as an optional state/input provider through the existing `get_portfolio_state` tool.
