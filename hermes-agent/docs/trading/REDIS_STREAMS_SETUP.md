# Redis Streams Setup

## Purpose

Hermes now uses Redis Streams as the shared live event bus for agent coordination and Paperclip-compatible orchestration.

- Main stream: `events:trading`
- Default consumer groups:
  - `orchestrator_group`
  - `strategy_group`
  - `risk_group`
  - `notifications_group`

## Configuration

Add Redis settings to `.env`:

```env
REDIS_URL=redis://localhost:6379/0
HERMES_REDIS_HOST=localhost
HERMES_REDIS_PORT=6379
REDIS_STREAM_MAXLEN=10000
```

`REDIS_STREAM_MAXLEN` is optional. When set, Hermes trims the stream approximately with Redis `MAXLEN ~`.

## Docker

`docker-compose.yml` now includes a local Redis container:

```bash
docker compose up -d redis
```

Or start the full local stack:

```bash
docker compose up -d
```

Redis runs with AOF persistence enabled for local durability.

## Bootstrap consumer groups

Hermes now bootstraps Redis automatically on dashboard startup:

```bash
docker compose up -d
docker compose logs hermes | grep -i "Redis event bus bootstrap"
```

Manual bootstrap is still available:

```bash
python -m backend.event_bus.validate bootstrap
```

This uses `XGROUP CREATE ... MKSTREAM` and is safe to run repeatedly.

## Validation commands

Run these from the Hermes repo root.

Confirm Redis is reachable and the stream/groups are initialized:

```bash
python -m backend.event_bus.validate bootstrap
python -m backend.event_bus.validate stream
python -m backend.event_bus.validate groups
```

If you are validating the Dockerized Hermes runtime directly, use the same commands inside the running container:

```bash
docker exec hermes-agent-hermes-1 /opt/hermes/.venv/bin/python -m backend.event_bus.validate bootstrap
docker exec hermes-agent-hermes-1 /opt/hermes/.venv/bin/python -m backend.event_bus.validate stream
docker exec hermes-agent-hermes-1 /opt/hermes/.venv/bin/python -m backend.event_bus.validate groups
```

Publish a test event:

```bash
python -m backend.event_bus.validate publish \
  --event-type notification_requested \
  --payload '{"message":"event-bus validation"}'
```

Dockerized runtime equivalent:

```bash
docker exec hermes-agent-hermes-1 /opt/hermes/.venv/bin/python -m backend.event_bus.validate publish \
  --event-type notification_requested \
  --payload '{"message":"event-bus validation"}'
```

Consume and ack it successfully:

```bash
python -m backend.event_bus.validate consume-once notifications_group --mode success
python -m backend.event_bus.validate pending notifications_group
```

Publish another test event and force worker failure so it stays pending:

```bash
python -m backend.event_bus.validate publish \
  --event-type notification_requested \
  --payload '{"message":"should stay pending"}'
python -m backend.event_bus.validate consume-once notifications_group --mode fail
python -m backend.event_bus.validate pending notifications_group
```

Expected validation result:

- `stream` shows `events:trading` with a non-zero `length` after publish
- `groups` lists `orchestrator_group`, `strategy_group`, `risk_group`, and `notifications_group`
- successful `consume-once` reports `processed: 1`
- failed `consume-once` reports `processed: 0`
- `pending notifications_group` shows pending entries after failure and none after successful ack-only runs

## Start workers

The repo now includes reusable worker scaffolds in `backend/event_bus/workers.py`.

Example long-running worker:

```bash
python -m backend.event_bus.workers orchestrator
python -m backend.event_bus.workers notifications
```

Worker behavior:

- Reads with `XREADGROUP`
- Acks with `XACK` only after successful handler completion
- Leaves failed messages pending for later inspection or reclaim

## TradingView integration

`TradingViewIngestionService` now publishes:

- `tradingview_alert_received`
- `tradingview_signal_ready`

TradingView failures still remain visible in shared storage even if stream publishing fails.

With Docker running, the dashboard runtime uses `REDIS_URL=redis://redis:6379/0` by default from `docker-compose.yml`.

## TODO

- Add pending-claim recovery and dead-letter handling once production worker retry policy is finalized.
- Wire BitMart execution updates into `execution_requested` and `execution_status_updated`.
