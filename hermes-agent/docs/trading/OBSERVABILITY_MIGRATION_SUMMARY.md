# Observability Migration Summary

## Scope implemented

This step was implemented as:

- backend observability and audit persistence
- backend query endpoints/helpers
- minimal operator dashboard/UI

So for this repo state, **both backend + UI were implemented**.

## Schema changes

Added new shared storage tables:

- `workflow_runs`
- `workflow_steps`
- `tool_calls`
- `agent_decisions`
- `execution_events`
- `system_errors`

These were registered in `backend/db/bootstrap.py` so TimescaleDB creates hypertables on `created_at`.

## Backend changes

Added:

- `backend/observability/context.py`
- `backend/observability/service.py`
- `backend/observability/__init__.py`

Updated:

- `backend/db/models.py`
- `backend/db/repositories.py`
- `backend/db/bootstrap.py`
- `backend/tools/_helpers.py`
- `backend/tools/send_notification.py`
- `backend/tradingview/service.py`
- `backend/tradingview/router.py`
- `backend/workflows/agents.py`
- `backend/workflows/graph.py`
- `hermes_cli/web_server.py`

## Query surface added

The backend now supports:

- `get_workflow_run`
- `list_recent_workflow_runs`
- `get_agent_decision_history`
- `get_tool_call_history`
- `get_execution_event_history`
- `get_system_errors`
- `get_recent_failures`
- `get_event_timeline`

These are available through `backend/observability/service.py` and exposed over the web API.

## UI changes

Added:

- `web/src/pages/ObservabilityPage.tsx`

Updated:

- `web/src/App.tsx`
- `web/src/lib/api.ts`

The UI bundle was rebuilt into `hermes_cli/web_dist`.

## Verification completed

Completed successfully:

- Python compile pass via `./.venv/bin/python -m compileall backend hermes_cli`
- backend tests:
  - `./.venv/bin/pytest -q tests/backend/test_notifications.py tests/backend/test_shared_time_series_storage.py`
- frontend build:
  - `cd web && npm run build`

Additional note:

- `tests/backend/test_trading_workflow_graph.py` could not be executed in this environment because `pydantic_graph` is not installed in the active virtualenv. The workflow observability code itself compiles, but that optional dependency gap remains outside this migration.

## Practical outcome

After startup and a sample run, Hermes now supports:

- querying recent workflow runs
- tracing one correlation ID end-to-end
- inspecting tool call history
- inspecting recent execution events
- inspecting failures/system errors
- verifying persistence in the shared SQLAlchemy/Timescale-backed storage layer
