# Agents

Hermes is structured around specialized agents with narrow responsibilities and explicit handoff boundaries.

## Initial Roles

- `orchestrator_trader`: primary coordinator for incoming requests, task routing, and proposal assembly
- `market_research`: gathers market structure, catalysts, sentiment, and regime context
- `portfolio_monitor`: tracks positions, exposures, PnL, drift, and account state
- `risk_manager`: evaluates policy, rejects unsafe actions, and maintains veto authority
- `strategy`: maintains strategy definitions, comparison workflows, and future backtesting hooks

## Design Notes

- Each agent should consume shared resources rather than building direct one-off integrations.
- The orchestrator should compose outputs, not silently replace specialist judgment.
- Risk review should remain authoritative before any execution path is considered final.

## Future Implementation Notes

- add task contracts and message schemas
- define agent memory boundaries
- formalize escalation rules and operator override handling
- add replayable execution traces for agent decisions
