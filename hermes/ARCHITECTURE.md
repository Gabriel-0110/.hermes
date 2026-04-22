# Architecture

Hermes Cryptocurrency AI Trader is organized as a production-oriented monorepo around a small number of stable system domains:

- `apps/api`: FastAPI service for operator APIs, orchestration entrypoints, health checks, and future channel adapters.
- `apps/web`: Next.js operator dashboard for Mission Control views, review workflows, and portfolio visibility.
- `packages/agents`: specialized agent modules such as orchestrator, market research, portfolio monitoring, risk, and strategy.
- `packages/tools`: reusable tool interfaces for market data, execution, sentiment, and on-chain analysis.
- `packages/resources`: shared schemas, adapters, registries, prompts, and governance primitives.
- `packages/mission-control`: human-in-the-loop surfaces such as notifications, dashboard state, and operator review.
- `packages/policies`: policy and governance definitions with risk policies as first-class artifacts.
- `packages/observability`: logging, metrics, and tracing placeholders.
- `packages/shared`: common settings and types intended to stay dependency-light.

## System Summary

The platform is designed around four architectural layers:

1. **Agent layer**: specialized decision-making and monitoring roles.
2. **Shared Intelligence Layer**: normalized market, portfolio, risk, and research context exposed to all agents.
3. **Mission Control**: the operator-facing control plane for review, notifications, observability, and intervention.
4. **Execution and governance**: routing, policy enforcement, auditability, and eventual exchange execution.

## Current Scaffold Scope

This repository intentionally does not implement trading logic yet. The current scaffold provides:

- stable package boundaries
- environment and local orchestration conventions
- starter API and web surfaces
- CI, linting, formatting, and test entrypoints
- documentation for contributors and operators

## Model Routing Philosophy

Hermes is model-provider agnostic:

- local model endpoints are represented by `OLLAMA_BASE_URL` and `LM_STUDIO_BASE_URL`
- cloud model endpoints are represented by `OPENAI_API_KEY` and `ANTHROPIC_API_KEY`
- future routing decisions should be policy-driven, task-aware, and observable

## Database Notes

PostgreSQL is the primary system of record. TimescaleDB is included to support future time-series workloads such as:

- OHLCV and tick ingestion
- order book and tape snapshots
- indicator caches
- portfolio and risk telemetry

The scaffold includes a simple SQL init file that ensures the Timescale extension is available in local development.

## Runtime Composition

Hermes is composed from two repositories and a runtime configuration layer that are kept separate by design:

### Repository Roles

| Component | Repo | Role |
|---|---|---|
| `hermes/apps/api` | `hermes/` | Future FastAPI operator surface (scaffold only, not authoritative runtime yet) |
| `hermes/apps/web` | `hermes/` | Future Mission Control UI (scaffold only) |
| `hermes-agent/backend/` | `hermes-agent/` | **Authoritative runtime backend**: tools, integrations, models, DB, agent gateway |
| `hermes-agent/gateway/` | `hermes-agent/` | Agent gateway process — hosts all running agents and the API server |
| Root `~/.hermes/` | runtime config | Profiles, teams, skills, memories, config.yaml — operator-controlled layer |

### Authoritative Runtime Backend

`hermes-agent/` is the current authoritative runtime. The `hermes/` packages are the long-term target architecture but are not wired to production workloads yet. Do not add business logic to `hermes/apps/api` until `hermes-agent/backend/` integration is complete.

### Composition at Startup

```
~/.hermes/config.yaml          → gateway configuration (model routing, providers, feature flags)
~/.hermes/profiles/<role>/     → per-agent identity, toolsets, and system prompt overrides
~/.hermes/teams/<team>/        → multi-agent team definitions and skill assignments
~/.hermes/hermes-agent/        → all backend code loaded by the gateway process
```

The gateway process (`hermes gateway run`) reads root config, loads profile and team definitions, and spins up agents backed by `hermes-agent/backend/` tools and integrations.

### Infrastructure Composition

| Service | Host | Purpose |
|---|---|---|
| PostgreSQL (hermes) | `host.docker.internal:5433` | Primary system of record; LiteLLM spend tracking |
| TimescaleDB | `host.docker.internal:5434` | Time-series workloads (OHLCV, tick, telemetry) |
| LiteLLM proxy | `127.0.0.1:4000` | Model routing and virtual key management |
| Redis | localhost | Gateway state, streams, caching |

### Adding New Capabilities

1. Implement the integration client in `hermes-agent/backend/integrations/<provider>/`.
2. Expose it via a tool function in `hermes-agent/backend/tools/<tool_name>.py`.
3. Register the tool in the relevant agent toolset definition.
4. Update the skills YAML under `~/.hermes/teams/trading-desk/skills/` to reflect real capabilities (remove stale limitation notes).
