# Hermes Cryptocurrency AI Trader

Hermes is a production-oriented monorepo for a multi-agent cryptocurrency trading product shell. The repository is structured to support specialized agents, shared market intelligence, Mission Control workflows, operator channels, and execution hardening work without pretending the system is complete today.

The current preferred local runtime uses **Hermes Agents** from the sibling
`hermes-agent/` workspace as the backend source of truth. In the current split
architecture:

- `hermes-agent/backend` is the runtime source of truth for workflows, typed
  proposal/risk/execution handling, approvals, observability, and canonical
  portfolio state
- `hermes/apps/api` is the product/API bridge over that backend runtime
- `hermes/apps/web` is the operator-facing Mission Control surface

## Project Overview

Hermes is designed around:

- a FastAPI backend for orchestration and service APIs
- a Next.js dashboard for Mission Control and operator review
- PostgreSQL with TimescaleDB for durable and time-series workloads
- Docker Compose for local development orchestration
- local model providers through Ollama and LM Studio
- cloud model providers through OpenAI and Anthropic
- channel surfaces spanning Telegram, Slack, CLI, and web

The current repository state is a partially integrated product shell. It
includes the API bridge, operator web app, docs, and shared package boundaries.
The live trading runtime itself still depends on the sibling `hermes-agent/`
workspace. Hermes now has typed control-path pieces and BitMart/CCXT-backed
execution support in the runtime, but it does **not** yet represent a
production-ready autonomous trading system.

## Architecture Summary

Hermes is organized into three practical planes:

1. **Runtime plane** in `hermes-agent/backend` for orchestrator, research,
   portfolio, risk, strategy, execution control, approvals, observability, and
   canonical portfolio state.
2. **Bridge plane** in `hermes/apps/api` for product-facing API routes over the
   runtime.
3. **Operator plane** in `hermes/apps/web` for dashboards, review, and human
   intervention.

The current control path is:

`proposal or signal -> risk/policy decision -> approval and mode gates -> execution -> observability and portfolio state`

Execution and governance remain explicit first-class concerns rather than hidden
implementation details. Current live execution is guarded by trading mode,
live-trading unlock flags, acknowledgment phrase, kill switch, and approval
queue behavior where configured.

## Repository Structure

```text
hermes/
  apps/
    api/                  FastAPI bridge service over hermes-agent runtime
    web/                  Next.js Mission Control frontend
  packages/
    agents/               Specialized agent modules
    tools/                Tool interfaces by domain
    resources/            Shared schemas, prompts, registries, adapters
    mission-control/      Dashboard, notifications, operator review primitives
    policies/             Governance and risk policy definitions
    observability/        Logging, metrics, tracing placeholders
    shared/               Common settings and types
  infrastructure/
    docker/               Dockerfiles
    db/                   Database init scripts
    scripts/              Bootstrap and helper scripts
  docs/                   Architecture and operating docs
  .github/                CI workflows
```

## Stack

- Backend: FastAPI, Python 3.11+, `uv`, `ruff`, `pytest`
- Frontend: Next.js 15, TypeScript, React 19
- Data: PostgreSQL, TimescaleDB
- Local orchestration: Docker Compose
- Model providers: Ollama, LM Studio, OpenAI API, Anthropic API
- Channels in scope: Telegram, Slack, CLI, web/dashboard

## Quickstart

### Prerequisites

- Python 3.11+
- `uv`
- Node.js 20+
- npm 10+
- Docker Desktop or compatible Docker engine

### Environment Setup

1. Copy `.env.example` to `.env`.
2. Fill in API keys and local service URLs as needed.
3. Confirm local model runtimes are reachable if you plan to test local inference paths.

### Local Development

### Canonical integrated local stack

From the workspace root:

```bash
make dev-help
make dev-up
make dev-check
```

This is the authoritative happy path for product development. It brings up, in
dependency order:

- TimescaleDB on `5433`
- Redis on `6379`
- LiteLLM on `4000`
- Hermes Agent dashboard/backend on `9119`
- Hermes API bridge on `8000`
- Hermes web app on `3000`

Use `make dev-logs` to follow logs and `make dev-down` to stop the stack.

This integrated path optimizes for a **reproducible working runtime**, not hot
reload. The web container serves a built Next.js app (`next build && next
start`) so the operator stack stays stable. If you want iterative frontend
development with hot reload, use the repo-local `make web` flow instead.

`make dev-up` also shuts down the older split compose stacks first so you do
not have to manually clean up legacy `hermes/`, `hermes-agent/`, and LiteLLM
containers before using the canonical path.

The unified local stack enables an **explicit development-only auth bypass** for
mutating product API routes. Outside this path, operator mutations require
`HERMES_API_KEY` unless you intentionally set `HERMES_API_DEV_BYPASS_AUTH=true`
in a development environment.

### Repo-local development

```bash
make setup
make api
make web
```

For the current unified startup flow that uses `hermes-agent` as the backend,
start with `docs/workspace/LOCAL_DEV.md` at the workspace root and use
[`docs/local-runtime-flow.md`](docs/local-runtime-flow.md) as the deeper
runbook.

In a separate terminal, you can also run:

```bash
make test
make lint
```

### Product-only Docker Compose

```bash
make up
```

This starts:

- `postgres` with TimescaleDB enabled
- `api` on port `8000`
- `web` on port `3000`

For the full operator stack that also includes the Hermes Agent backend,
Redis, TimescaleDB, and LiteLLM, use the runbook in
the `docs/workspace/LOCAL_DEV.md` quickstart plus
[docs/local-runtime-flow.md](docs/local-runtime-flow.md).

## Environment Variables

See `.env.example` for the full starter list. Important groups:

- model providers: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, `LM_STUDIO_BASE_URL`
- database: `POSTGRES_*`, `DATABASE_URL`
- channels: `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`
- app/runtime: `APP_ENV`, `LOG_LEVEL`, `WEBHOOK_BASE_URL`, `HERMES_API_DEV_BYPASS_AUTH`

## Current Status

The repository currently provides:

- monorepo structure aligned with the current split Hermes architecture
- runnable FastAPI bridge service
- runnable Next.js operator dashboard shell
- package placeholders for agents, tools, resources, policies, and observability
- local development scripts and CI workflows

The combined workspace currently provides:

- typed proposal -> risk/policy -> execution request/result flow in
  `hermes-agent/backend`
- paper-mode execution simulation
- BitMart / CCXT-backed live connector path with explicit blockers
- kill switch support
- approval queue support
- portfolio snapshot and sync path used as canonical position state

The repository does not yet provide:

- a single packaged runtime that unifies `hermes-agent` and `hermes`
- exchange-grade position accounting or fill reconciliation
- production-grade secret management
- mature strategy evaluation and backtesting
- durable execution idempotency and replay controls
- production-ready autonomous live trading

## Roadmap Summary

- implement shared market and portfolio schemas
- add model routing and provider abstraction
- introduce paper-trading execution connectors
- add operator approvals and audit trails
- expand observability, replay, and incident review workflows

See [ROADMAP.md](ROADMAP.md) for the fuller phased plan.

## Important Disclaimer

This repository is not a finished exchange bot or production live-trading
system. Hermes is moving toward exchange-bot-like behavior through typed
control flow, explicit risk gates, approvals, and portfolio tracking, but the
current stack still has split-runtime boundaries and material hardening work
remaining before any real-funds use.
