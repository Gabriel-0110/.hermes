# Evaluation Architecture

## Design Goals

- Reuse the existing Hermes trading workflow graph.
- Keep replay artifacts clearly separated from live workflow data.
- Preserve correlation across source events, replay runs, and workflow traces.
- Default to dry-run semantics with no live side effects.
- Keep the first implementation practical and inspectable.

## Main Components

### `backend/evaluation/storage.py`

- Persists replay cases, runs, results, scores, and regression comparisons.
- Reconstructs TradingView replay cases from shared storage.
- Uses the existing `HermesTimeSeriesRepository` and Timescale bootstrap flow.

### `backend/evaluation/replay.py`

- Wraps the normal workflow tool surface with replay-safe adapters.
- Reuses the existing trading workflow graph.
- Tags workflow/audit metadata with replay identifiers.
- Persists replay outputs into evaluation-specific tables.

### `backend/evaluation/scoring.py`

- Computes rule-based replay scores.
- Supports:
  - approved vs rejected
  - execution vs no execution
  - forward return
  - risk compliance
  - latency

### `backend/evaluation/regression.py`

- Compares baseline and candidate replay runs.
- Supports comparisons across:
  - model version
  - prompt version
  - workflow version

## Data Separation

Replay-specific data lives in dedicated tables:

- `replay_cases`
- `replay_runs`
- `replay_results`
- `evaluation_scores`
- `regression_comparisons`

Shared workflow observability still lands in:

- `workflow_runs`
- `workflow_steps`
- `agent_decisions`
- `execution_events`
- `system_errors`

Those shared rows are tagged with replay metadata such as:

- `run_mode=replay`
- `replay_case_id`
- `replay_run_id`
- `source_event_id`
- `source_correlation_id`

## Replay Safety Model

- The replay tool wrapper blocks order placement.
- The replay tool wrapper blocks live notifications by default.
- Notification delivery can be redirected to a test sink.
- The workflow may still produce `should_execute=True`; this is treated as an evaluated outcome, not a live trade.

## Point-in-Time Behavior

Current replay reconstruction is strongest for:

- TradingView alert payloads
- internal event lineage
- portfolio snapshot lookup at or before the alert timestamp

Current v1 limitations:

- market, macro, and onchain tools still run through the existing adapters
- no full historical market-state snapshot framework yet

## Linkage Model

Each replay artifact keeps the original lineage where available:

- source TradingView `event_id`
- source `correlation_id`
- source `alert_id`
- replay run id
- workflow run id generated for replay execution

This allows:

- replay-to-source traceability
- replay-to-audit joins
- regression comparisons across versions
