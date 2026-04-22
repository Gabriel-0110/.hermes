# Evaluation Migration Summary

## Added

- New replay/evaluation package under `backend/evaluation/`
- Dedicated Timescale-backed tables for:
  - `replay_cases`
  - `replay_runs`
  - `replay_results`
  - `evaluation_scores`
  - `regression_comparisons`
- Replay-safe workflow tool wrapper
- TradingView historical replay case loader
- Rule-based scoring utilities
- Regression comparison utilities
- Backend tests for replay persistence and regression comparison

## Reused Existing Hermes Components

- trading workflow graph in `backend/workflows`
- Timescale bootstrap and repository layer in `backend/db`
- audit/observability service in `backend/observability`
- TradingView shared storage contract in `backend/tradingview`

## Safety Guarantees in v1

- no live order placement during replay
- no live notifications during replay unless explicitly redirected to a test sink
- replay artifacts persisted separately from live outcome tables
- replay workflow traces tagged with replay metadata for audit joins

## Minimal First Scope

Implemented first-scope replay for:

- TradingView-triggered workflows
- one or more stored historical alerts
- dry-run only execution
- no live notifications

## Known Gaps

- no full point-in-time market/macro/onchain snapshot system yet
- scoring depends on expected outcomes supplied with the replay case for some metrics such as forward return
- no CLI wrapper yet; current integration is Python-module first

## Operational Impact

- Existing live workflows remain unchanged.
- Evaluation writes add new tables but do not require changes to the live workflow contract.
- Shared observability remains available and is now usable for replay traces via replay metadata tags.
