# Observability Setup

Hermes now ships with a backend-native observability and audit trail layer built on the shared SQLAlchemy storage path, with TimescaleDB/Postgres as the primary target and the existing SQLite fallback retained for local or degraded environments.

## What gets stored

The observability schema adds these persistent tables:

- `workflow_runs`
- `workflow_steps`
- `tool_calls`
- `agent_decisions`
- `execution_events`
- `system_errors`

Existing tables still support related operator views:

- `tradingview_alert_events`
- `tradingview_internal_events`
- `notifications_sent`

## Required runtime

Preferred production setup:

- `DATABASE_URL=postgresql+psycopg://...`
- TimescaleDB reachable from the Hermes backend
- Redis reachable if TradingView ingestion publishes to Redis Streams

Local fallback:

- If the shared DB is unavailable, observability writes fall back to the local Hermes `state.db`
- This keeps ingestion and notifications inspectable even when TimescaleDB is temporarily down

## Startup behavior

On web/backend startup Hermes will:

1. bootstrap the shared DB schema
2. create Timescale hypertables when Postgres/Timescale is available
3. keep the existing SQLite fallback path available

The web server already calls shared backend bootstrap on startup via `hermes_cli/web_server.py`.

## Query surface

Backend/API endpoints:

- `GET /api/observability/dashboard`
- `GET /api/observability/workflow-runs`
- `GET /api/observability/workflow-runs/{workflow_run_id}`
- `GET /api/observability/agent-decisions`
- `GET /api/observability/tool-calls`
- `GET /api/observability/execution-events`
- `GET /api/observability/system-errors`
- `GET /api/observability/failures`
- `GET /api/observability/notifications`
- `GET /api/observability/timeline/{correlation_id}`

The corresponding backend helper methods live in `backend/observability/service.py`.

## Operator dashboard

The web UI now includes an `Ops` page that shows:

- recent workflow runs
- pending/in-progress work
- workflow detail with step timeline
- recent failures/errors
- execution events
- risk rejections
- tool call history
- agent decisions
- recent notifications
- correlation-based event timeline lookup

To rebuild the UI bundle after frontend changes:

```bash
cd web
npm run build
```

## Verification flow

After startup and a sample workflow/ingestion run you should be able to:

1. open the `Ops` page in the web UI
2. confirm a record appears in recent workflow runs
3. open the workflow detail and inspect workflow steps
4. inspect recent tool calls, decisions, and execution events
5. query failures/errors
6. paste a `correlation_id` into the timeline search and trace the chain end-to-end

## Notes

- Sensitive material is summarized and redacted before persistence
- Notification records embed correlation metadata in their stored payload metadata
- The workflow graph uses one correlation chain from inbound event through decisions and execution handoff
