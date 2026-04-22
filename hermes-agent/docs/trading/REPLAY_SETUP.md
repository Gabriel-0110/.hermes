# Replay Setup

## Scope

This v1 replay harness targets TradingView-triggered workflow replay for the Hermes multi-agent trading system.

- Historical inputs come from Timescale-backed `tradingview_alert_events` and `tradingview_internal_events`.
- Replay outputs persist to dedicated evaluation tables:
  - `replay_cases`
  - `replay_runs`
  - `replay_results`
  - `evaluation_scores`
  - `regression_comparisons`
- Existing observability tables are still reused for workflow traces, but replay runs are tagged with `run_mode=replay` in metadata.

## Prerequisites

- `DATABASE_URL` should point to the Hermes shared PostgreSQL/TimescaleDB instance.
- SQLite also works for local development and tests, but TimescaleDB remains the preferred persistence layer.
- Historical TradingView alerts must already exist in shared storage.

## Replay Flow

1. Load one or more TradingView alerts from storage.
2. Materialize a `ReplayCase` from the historical alert plus related internal events.
3. Run the normal trading workflow graph in replay mode.
4. Persist replay-only outputs into the evaluation tables.
5. Score the replay result with configurable evaluation rules.
6. Optionally compare replay runs for regression analysis.

## Safety Defaults

- Replay mode never places live orders.
- Replay mode never sends live notifications.
- Notifications may be diverted to a test sink such as `log`.
- Replay mode uses historical TradingView payloads and prefers a point-in-time portfolio snapshot when available.

## Current Entry Points

- Python module: `backend.evaluation`
- Runner: `backend.evaluation.replay.ReplayRunner`
- Storage facade: `backend.evaluation.storage.ReplayStorage`
- Scoring: `backend.evaluation.scoring`
- Regression comparison: `backend.evaluation.regression`

## Suggested Local Usage

```python
from backend.evaluation import EvaluationRuleConfig, ReplayRunConfig, ReplayRunner, ReplayStorage

storage = ReplayStorage()
runner = ReplayRunner(storage=storage)

case = storage.load_tradingview_alert_case(alert_id="tv_alert_123")
artifacts = await runner.run_case(
    case,
    rules=EvaluationRuleConfig(
        approved_vs_rejected_expected="execute",
        execution_expected=True,
        min_forward_return=0.0,
        max_latency_ms=5000,
    ),
    run_config=ReplayRunConfig(
        workflow_version="trading_workflow_v1",
        prompt_version="prompt_v1",
    ),
)
```

## Notes

- Forward-return scoring currently expects expected outcomes to be attached to the replay case.
- Market/macro/onchain tools still use the existing tool interfaces; v1 does not attempt a fully point-in-time market reconstruction layer.
