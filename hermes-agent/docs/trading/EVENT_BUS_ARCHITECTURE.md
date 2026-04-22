# Event Bus Architecture

## Overview

Hermes uses Redis Streams as the shared live event bus and TimescaleDB as the historical system of record.

- TimescaleDB stores normalized audit history and queryable state.
- Redis Streams carries live workflow events between Hermes agents and Paperclip-compatible workers.
- The current shared stream is `events:trading`.

## Event contract

Supported event types:

- `tradingview_alert_received`
- `tradingview_signal_ready`
- `strategy_candidate_created`
- `risk_review_requested`
- `risk_review_completed`
- `execution_requested`
- `execution_status_updated`
- `portfolio_snapshot_updated`
- `notification_requested`

Each stream message includes:

- `event_id`
- `event_type`
- `source`
- `created_at`
- `schema_version`
- `symbol`
- `alert_id`
- `correlation_id`
- `causation_id`
- `producer`
- `workflow_id`
- `payload` as JSON
- `metadata` as JSON

## Flow

1. TradingView webhook ingestion normalizes and persists the alert.
2. The ingestion service publishes normalized live events to `events:trading` with `XADD`.
3. Consumer groups read the same stream independently with `XREADGROUP`.
4. Workers ack successful messages with `XACK`.
5. Failed messages remain pending and unacked for retry or manual recovery.

## Consumer group intent

- `orchestrator_group`: workflow routing and handoff decisions
- `strategy_group`: signal-to-candidate processing
- `risk_group`: pre-trade review and gating
- `notifications_group`: user-facing alerts and reports

Portfolio monitoring consumes execution and account update events through the same shared event schema. A dedicated portfolio group can be added later without changing the event payload contract.

## Design notes

- Redis access is centralized in `backend.redis_client`.
- Stream publishing is centralized in `backend.event_bus.publisher`.
- Consumer-group creation is centralized in `backend.event_bus.bootstrap`.
- Worker ack policy is centralized in `backend.event_bus.consumer`.
- No agent gets its own Redis connection config; all backend modules share `REDIS_URL`.

## Paperclip compatibility

Paperclip-compatible orchestration can subscribe by joining the same consumer-group pattern or by creating additional groups on `events:trading`. The stream payload is normalized so downstream runtimes do not need raw webhook parsing knowledge.

## TODO

- Add claim/recovery helpers for stale pending entries.
- Add a dead-letter stream policy if specific handlers need bounded retries.
- Add BitMart execution adapter publishers when execution routing is finalized.

