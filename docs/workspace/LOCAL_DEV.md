# Hermes Local Development

This is the **authoritative local development entrypoint** for the combined Hermes workspace.

If you want the full product happy path — backend infra + LiteLLM + Hermes dashboard/backend + product API + product web — use the root launcher below.

## One happy path

From the workspace root:

```bash
make dev-help
make dev-up
make dev-check
```

Use this path before falling back to repo-local commands.

## What starts

The unified stack starts these services in dependency order:

1. `timescaledb` — shared PostgreSQL/Timescale state on `5433`
2. `redis` — event bus and approval/risk state on `6379`
3. `litellm` — model gateway and UI on `4000`
4. `dashboard` — Hermes Agent backend/dashboard on `9119`
5. `api` — Hermes product API bridge on `8000`
6. `web` — Hermes Mission Control web app on `3000`

The compose file makes those dependencies explicit, and `make dev-up` shuts down the older split stacks first so port/container conflicts do not turn local startup into interpretive dance.

## Health checks and expected ports

`make dev-check` verifies the canonical HTTP endpoints:

- LiteLLM — `http://127.0.0.1:4000/health/liveliness`
- Hermes dashboard — `http://127.0.0.1:9119/api/status`
- Hermes API bridge — `http://127.0.0.1:8000/api/v1/healthz`
- Hermes web app — `http://127.0.0.1:3000`

For a single operator-facing runtime snapshot, run:

```bash
hermes ops status
```

That command summarizes the active profile, dev stack status, API/dashboard/web health,
LiteLLM, Redis, Postgres/TimescaleDB, gateway runtime authority, Slack/Telegram runtime
status, launchd state, stale lock files, cron state for drawdown guard and whale tracker,
and the last known trading mode. It exits nonzero when critical runtime components are unhealthy.

Example:

```bash
hermes ops status
```

Expected host ports:

- `5433` — TimescaleDB
- `6379` — Redis
- `4000` — LiteLLM
- `9119` — Hermes dashboard/backend
- `8000` — Hermes product API
- `3000` — Hermes web app

## Auth posture in local development

Mutating product API routes are **not open by default** in normal runs.

The unified local dev flow uses `.env.dev` / `.env.dev.example` to set an **explicit development-only bypass**:

- `HERMES_API_DEV_BYPASS_AUTH=true`

That bypass is intentional and local-only. The compose file no longer silently enables it.

If you want to exercise the authenticated path locally instead:

1. set `HERMES_API_DEV_BYPASS_AUTH=false` in `.env.dev`
2. set `HERMES_API_KEY=<your-token>` in `.env.dev`
3. send `Authorization: Bearer <your-token>` to mutating product API routes

## Common commands

```bash
make dev-up
make dev-check
make dev-logs
make dev-ps
make dev-down
```

## When to use repo-local commands instead

Use repo-local commands only when you are debugging or iterating on one layer:

- `hermes/` — hot-reload API or web development
- `hermes-agent/` — direct backend/dashboard or agent runtime work

For those deeper workflows, see:

- `hermes/docs/local-runtime-flow.md`
- `docs/workspace/GATEWAY_RUNTIME.md`
- `hermes/README.md`
- `hermes-agent/README.md`

## Short verification checklist

1. Run `make dev-up`
2. Run `hermes ops status`
3. Run `make dev-check`
4. Open:
   - LiteLLM UI: `http://localhost:4000/ui`
   - Dashboard: `http://localhost:9119`
   - Product API docs: `http://localhost:8000/docs`
   - Product web: `http://localhost:3000`
5. Confirm all HTTP checks return `200`

That is the canonical local runtime. One command, one happy path, fewer haunted compose rituals.
