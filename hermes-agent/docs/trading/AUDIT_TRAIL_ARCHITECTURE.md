# Audit Trail Architecture

## Goals

The v1 audit trail is designed to make the Hermes multi-agent trading system inspectable without adding an external observability stack.

Primary design goals:

- end-to-end traceability by `event_id` and `correlation_id`
- durable storage in the shared TimescaleDB/Postgres layer
- compatibility with existing Hermes backend/session/repository patterns
- safe summaries instead of raw secret-bearing payload persistence
- direct operator visibility through Hermes-native APIs and UI

## Core pieces

### Storage

`backend/db/models.py` defines the persistent observability records:

- `WorkflowRunRow`
- `WorkflowStepRow`
- `ToolCallRow`
- `AgentDecisionRow`
- `ExecutionEventRow`
- `SystemErrorRow`

`backend/db/bootstrap.py` registers them as Timescale hypertables on `created_at`.

`backend/db/repositories.py` exposes structured insert/query methods for these records.

### Context propagation

`backend/observability/context.py` uses `contextvars` to propagate:

- `event_id`
- `correlation_id`
- `workflow_run_id`
- `workflow_name`
- `workflow_step`
- `agent_name`
- `tool_name`

This is what keeps the same correlation chain attached while the workflow graph invokes tools and agents.

### High-level service

`backend/observability/service.py` is the backend-native facade that:

- summarizes and redacts payloads
- writes audit records
- exposes query helpers such as:
  - `get_workflow_run`
  - `list_recent_workflow_runs`
  - `get_agent_decision_history`
  - `get_tool_call_history`
  - `get_execution_event_history`
  - `get_system_errors`
  - `get_recent_failures`
  - `get_event_timeline`
- falls back to local SQLite when the shared DB is unavailable

## Instrumented paths

### TradingView ingestion

`backend/tradingview/service.py` now records:

- inbound TradingView event ingestion
- persistence result
- Redis publish success/failure
- parse/publish errors

The ingestion path generates a fresh `event_id` and `correlation_id` and stores both in persisted payload metadata.

### Workflow execution

`backend/workflows/graph.py` now records:

- workflow run start/end/failure
- workflow step start/end for major graph stages
- execution handoff readiness
- risk rejections
- terminal rejection events

### Agent decisions

`backend/workflows/agents.py` now records:

- typed agent completion
- typed agent fallback
- typed agent failure

### Tool calls

`backend/tools/_helpers.py` now records:

- tool completion
- validation failures
- provider configuration failures
- provider failures
- unexpected tool failures

This automatically covers the workflow’s backend tool adapters because they reuse `run_tool()`.

### Notifications

`backend/tools/send_notification.py` now:

- stores correlation metadata inside notification payload metadata
- records a `notification_sent` execution event

## Operator visibility

### API

The web server exposes backend-native observability endpoints in `hermes_cli/web_server.py`.

### UI

The React web UI adds an `Ops` page that renders:

- live workflows
- workflow detail
- failures/errors
- execution events
- risk rejections
- tool call history
- agent decisions
- notifications
- correlation timeline search

## Security model

The audit layer stores summarized data, not raw unrestricted payloads.

Protections in v1:

- sensitive key-name redaction
- string truncation for long payloads
- notification metadata sanitization
- no secret values intentionally surfaced in the operator page

## Extension points

Natural next steps if the trading runtime grows:

- dedicated execution adapter instrumentation for `place_order` / exchange fills
- richer workflow-step drilldowns
- SQL-level timeline unions for larger datasets
- retention/compression policies for long-running Timescale deployments
- operator filters by symbol, workflow, agent, or severity
