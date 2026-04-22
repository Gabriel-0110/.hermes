# Hermes Cryptocurrency AI Trader

Hermes is a production-oriented monorepo scaffold for a multi-agent cryptocurrency trading platform. The repository is structured to support specialized agents, shared market intelligence, Mission Control workflows, operator channels, and future execution hardening without pretending the system is complete today.

The current preferred local runtime uses **Hermes Agents** from the sibling
`hermes-agent/` workspace as the backend source of truth, with this repo
providing the API bridge and operator-facing web shell.

## Project Overview

Hermes is designed around:

- a FastAPI backend for orchestration and service APIs
- a Next.js dashboard for Mission Control and operator review
- PostgreSQL with TimescaleDB for durable and time-series workloads
- Docker Compose for local development orchestration
- local model providers through Ollama and LM Studio
- cloud model providers through OpenAI and Anthropic
- channel surfaces spanning Telegram, Slack, CLI, and web

The current repository state is a clean foundation. It includes documentation, developer tooling, starter services, shared package boundaries, and placeholder modules aligned with the architecture. It does **not** yet include live trading logic, exchange execution, strategy engines, or production-grade governance controls.

## Architecture Summary

Hermes is organized into three practical planes:

1. **Agent plane** for orchestrator, research, portfolio, risk, and strategy roles.
2. **Shared Intelligence Layer** for market data, tape, indicators, derivatives, portfolio state, risk policy, strategy libraries, sentiment, on-chain context, execution connectors, and memory.
3. **Mission Control** for dashboards, notifications, observability, and human review.

Execution and governance remain explicit first-class concerns rather than hidden implementation details. The scaffold makes room for policy-first approvals, audit trails, and operator intervention before any live execution is introduced.

## Repository Structure

```text
hermes/
  apps/
    api/                  FastAPI backend service
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

- monorepo structure aligned with the Hermes architecture
- runnable FastAPI starter service
- runnable Next.js starter dashboard
- package placeholders for agents, tools, resources, policies, and observability
- local development scripts and CI workflows

The repository does not yet provide:

- real exchange connectors
- production-grade secret management
- strategy evaluation and backtesting
- durable workflow orchestration
- policy-complete execution approval chains

## Roadmap Summary

- implement shared market and portfolio schemas
- add model routing and provider abstraction
- introduce paper-trading execution connectors
- add operator approvals and audit trails
- expand observability, replay, and incident review workflows

See [ROADMAP.md](ROADMAP.md) for the fuller phased plan.

## Important Disclaimer

This repository is a scaffold, not a live trading system. Trading logic, exchange execution, capital controls, authentication, auditability, and failure handling all require substantial additional hardening before any production or real-funds use.
