# Redis Streams Migration Summary

## Added

- Shared Redis connection management via `backend/redis_client.py`
- Central Redis Streams event bus package under `backend/event_bus/`
- Normalized trading event schema for Hermes and Paperclip-compatible workers
- Shared publisher helpers using `XADD`
- Consumer-group bootstrap using `XGROUP CREATE ... MKSTREAM`
- Reusable worker scaffolding using `XREADGROUP` and `XACK`
- Docker Compose Redis service with local persistence
- `REDIS_URL` and related Redis env documentation

## Integrated

- TradingView ingestion now publishes `tradingview_alert_received` and `tradingview_signal_ready` into `events:trading`
- Agent/runtime documentation now describes stream routing responsibilities
- Hermes dashboard startup now pings Redis and bootstraps consumer groups automatically
- A runtime validation utility now supports stream inspection, test publish, group listing, pending inspection, and one-shot worker consumption

## Missing wiring that is now fixed

- Redis event bus bootstrap is now connected to the real Hermes startup path in `hermes_cli/web_server.py`
- Docker now exposes Redis on `${HERMES_REDIS_PORT:-6379}` and uses an explicit Redis image/config matching the documented local runtime
- Runtime logging now covers Redis client initialization, ping success/failure, startup bootstrap, publish success, group bootstrap, worker polling, ack success, and ack/failure paths
- Worker scaffolds are now directly runnable with `python -m backend.event_bus.workers ...`

## Initial groups

- `orchestrator_group`
- `strategy_group`
- `risk_group`
- `notifications_group`

## Initial live event contract

- `tradingview_alert_received`
- `tradingview_signal_ready`
- `strategy_candidate_created`
- `risk_review_requested`
- `risk_review_completed`
- `execution_requested`
- `execution_status_updated`
- `portfolio_snapshot_updated`
- `notification_requested`

## Deferred

- Pending-entry claim and replay helpers
- Dead-letter queue policy
- BitMart execution adapter publishing and consumption
