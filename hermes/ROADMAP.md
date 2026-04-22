# Roadmap

## Phase 0: Foundation

- establish monorepo structure
- document architecture and local development
- stand up API, web, database, and CI scaffolding
- define shared package boundaries

## Phase 1: Shared Intelligence Layer

- formalize schemas for market, portfolio, risk, and execution events
- implement adapters for exchanges, news, and on-chain data
- introduce registries for tools, prompts, and providers
- store time-series telemetry in TimescaleDB

## Phase 2: Agent Runtime

- implement orchestrator task routing
- add market research, portfolio monitor, risk manager, and strategy agents
- add task memory and research store primitives
- define model routing between local and cloud providers

## Phase 3: Mission Control

- build dashboard panels for system state, proposals, alerts, and execution review
- add operator approvals, exception handling, and notifications
- introduce role-aware access control

## Phase 4: Execution and Governance

- extend the current typed proposal -> risk/policy -> approval/mode gate ->
  execution -> observability/portfolio path
- strengthen paper-mode simulation and live-mode blockers
- improve approval gates, audit logs, replay, and incident review
- tighten execution idempotency and duplicate protection

## Phase 5: Hardening

- secrets management
- queueing and workflow durability
- backtesting and simulation
- deployment automation
- SLOs, alerting, and disaster recovery patterns
