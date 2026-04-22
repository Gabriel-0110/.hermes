# Hermes Local Runtime Flow

> The workspace-root `docs/workspace/LOCAL_DEV.md` file is the primary quick-start for the
> integrated stack. This document is the deeper companion runbook for debugging
> and understanding the pieces behind that one-command path.

## Purpose

This is the authoritative local startup path for the current split Hermes workspace.

Use this flow when you want:

- `hermes-agent` to act as the backend source of truth
- `hermes/apps/api` to serve the API bridge
- `hermes/apps/web` to serve the Mission Control shell

This is the current recommended way to "use Hermes Agents" locally. The backend
logic, shared storage, TradingView ingestion, and observability live in
`hermes-agent`. The `hermes/` repo should be treated as the product shell and
operator-facing API/UI layer.

## Workspace layout

- `hermes-agent/`
  - backend source of truth
  - Redis, TimescaleDB, TradingView ingestion, observability, workflows
- `hermes/`
  - FastAPI bridge and Next.js Mission Control UI

## Prerequisites

- Python 3.11+
- `uv`
- Node.js 20+
- npm
- Docker

## One-command happy path

From the workspace root:

```bash
make dev-up
make dev-check
```

That command path boots the full local development stack and verifies the HTTP
health checks that matter to operators.

The canonical integrated path prioritizes **runtime coherence** over live code
reload. In particular, the web service runs a built Next.js app inside the
container so the one-command stack is predictable. Use repo-local `make api` /
`make web` when you want hot reload while editing code.

`make dev-up` also performs a compatibility cleanup step: it shuts down the old
split compose stacks from `hermes/`, `hermes-agent/`, and
`hermes-agent/docker-compose.litellm.yml` before bringing up the unified stack.
That avoids container-name and host-port collisions from the previously
fragmented startup paths.

## Startup order and dependencies

The unified stack starts in this order:

1. `timescaledb` → shared relational/time-series state on host port `5433`
2. `redis` → event bus and approval/risk state on host port `6379`
3. `litellm` → model gateway + UI on host port `4000`
4. `dashboard` → Hermes Agent backend/dashboard on host port `9119`
5. `api` → Hermes product API bridge on host port `8000`
6. `web` → Hermes Mission Control web app on host port `3000`

Compose dependency gates now make that order explicit:

- `litellm` waits for `timescaledb`
- `dashboard` waits for `redis`, `timescaledb`, and `litellm`
- `api` waits for `timescaledb` and `dashboard`
- `web` waits for the API health check

## Health checks and expected ports

`make dev-check` verifies the canonical HTTP endpoints:

- LiteLLM → `http://127.0.0.1:4000/health/liveliness`
- Hermes Agent dashboard → `http://127.0.0.1:9119/api/status`
- Hermes API bridge → `http://127.0.0.1:8000/api/v1/healthz`
- Hermes web → `http://127.0.0.1:3000`

Expected host ports:

- `5433` → TimescaleDB/PostgreSQL
- `6379` → Redis
- `4000` → LiteLLM
- `9119` → Hermes Agent dashboard/backend
- `8000` → Hermes API bridge
- `3000` → Hermes Mission Control web app

## Manual equivalent (if you need to inspect the pieces)

### 1. Start Hermes Agent infrastructure

From `hermes-agent/`:

```bash
docker compose up -d redis timescaledb
```

This gives the Hermes backend its shared state services:

- Redis
- TimescaleDB / PostgreSQL

### 2. Optional: start LiteLLM

If you need named model routes from the desk profiles:

From `hermes-agent/`:

```bash
docker compose -f docker-compose.litellm.yml up -d
```

Use this when the agent runtime or desk profiles are expected to resolve route
names such as `orchestrator-default`, `research-default`, `risk-default`, or
`strategy-default`.

### 3. Start the Hermes Agent backend/dashboard runtime

From `hermes-agent/`:

```bash
uv sync
uv run python -m hermes_cli.main dashboard --host 0.0.0.0 --port 9119
```

This gives you:

- shared backend bootstrap
- TradingView webhook handling
- observability API surface
- Hermes Agent dashboard on port `9119`

You can also use the repo-local compose service instead:

```bash
docker compose up --build hermes
```

## 4. Start the Hermes API bridge

From `hermes/`:

```bash
cp .env.example .env
uv sync
uv run uvicorn hermes_api.main:app --reload --app-dir apps/api/src --host 0.0.0.0 --port 8000
```

Important notes:

- `hermes/apps/api` imports backend modules from the sibling `hermes-agent`
  workspace.
- If you want the bridge to use shared Postgres instead of local SQLite
  fallback, set `DATABASE_URL` in `.env`.

## 5. Start the Hermes Mission Control web app

From `hermes/apps/web`:

```bash
npm install
npm run dev
```

Set the web app to call the bridge API:

```bash
export HERMES_API_BASE_URL=http://localhost:8000/api/v1
```

Or place it in `hermes/.env`:

```bash
HERMES_API_BASE_URL=http://localhost:8000/api/v1
```

The one-command path above is preferred. The manual steps below are only for
debugging individual layers.

## Recommended operator workflow

1. Run `make dev-up` from the workspace root.
2. Run `make dev-check` and confirm all four HTTP health checks return `200`.
3. Use the `hermes/` web UI on `3000` as the primary operator shell.
4. Use the Hermes Agent dashboard on `9119` when you need low-level runtime or
  observability debugging.
5. Use `make dev-logs` for live troubleshooting and `make dev-down` to stop the
  stack.

## Auth defaults for operator mutations

Mutating product API routes are no longer implicitly open when
`HERMES_API_KEY` is unset.

Safe default policy:

- outside explicit development mode, protected routes require
  `Authorization: Bearer <HERMES_API_KEY>`
- local bypass only exists when `HERMES_API_DEV_BYPASS_AUTH=true` is set
  intentionally in a development/test environment

The unified `make dev-up` path sets that bypass explicitly for local developer
convenience. Treat it as local-only behavior, not a deployment default.

## Current limitations

- This is still a split runtime, not a single packaged deployment.
- The `hermes/` UI depends on API bridge routes that import sibling
  `hermes-agent` modules directly.
- TradingView MCP is still an external dependency outside this repo.
- Full execution hardening and operator auth are not complete yet.

## Verification commands

Preferred workspace-root verification:

```bash
make dev-check
```

Additional repo-local verification from `hermes/`:

```bash
uv run pytest apps/api/tests -q
uv run ruff check apps/api/src/hermes_api apps/api/tests
```

From `hermes/apps/web`:

```bash
npm run lint
npm run build
```
