# TradingView Ingestion

## Purpose

This repo now treats TradingView alert delivery as a shared backend webhook-ingestion problem, not an MCP problem.

- MCP access is for agents actively calling TradingView-capable tools.
- Webhook ingestion is for TradingView pushing alert events into Hermes and Paperclip through `POST /webhooks/tradingview`.
- Agents must only read normalized records and internal events. No agent should parse raw webhook HTTP requests directly.

## Endpoint

- Route: `POST /webhooks/tradingview`
- Shared secret header: `X-TV-Secret` by default
- Secret env var: `TRADINGVIEW_WEBHOOK_SECRET`
- Header-name override: `TRADINGVIEW_WEBHOOK_SECRET_HEADER`

If the request secret is missing or incorrect, the endpoint returns `401`.

## Payload handling

- `application/json`: parsed as JSON directly
- `text/plain`: parsed as JSON if possible, otherwise stored as raw text
- any other content type: stored safely as raw text payload

Inbound payloads are sanitized before storage and republishing. Keys that look like credentials or provider secrets are redacted automatically. Do not put exchange keys, broker credentials, or provider secrets in TradingView alert messages.

## Normalized schema

Normalized alerts are stored with:

- `source`
- `received_at`
- `symbol`
- `timeframe`
- `alert_name`
- `strategy`
- `signal`
- `direction`
- `price`
- `raw_payload`

## Storage

The shared backend persists TradingView and shared trading time-series data in TimescaleDB on PostgreSQL when `DATABASE_URL` is configured. This is now the primary source of truth for Hermes and Paperclip.

Primary shared tables:

- `tradingview_alert_events`
- `tradingview_internal_events`
- `agent_signals`
- `portfolio_snapshots`
- `risk_events`
- `notifications_sent`

`tradingview_alert_events` stores the canonical alert record plus `processing_status` and `processing_error`.

`tradingview_internal_events` stores downstream workflow events such as:

- `tradingview_alert_received`
- `tradingview_signal_ready`
- `tradingview_alert_failed`

Fallback behavior:

- If `DATABASE_URL` is unset, Hermes falls back to local `state.db` for TradingView storage only.
- If code explicitly instantiates `TradingViewStore(db_path=...)`, that path is treated as an intentional SQLite fallback for tests or legacy flows.
- Agents and tools should treat TimescaleDB/PostgreSQL as the canonical runtime backend.

## Agent read tools

- `get_recent_tradingview_alerts`
- `get_tradingview_alert_by_symbol`
- `get_pending_signal_events`
- `get_tradingview_alert_context`

Role guidance:

- `market_researcher`: read TradingView alert context
- `strategy_agent`: read TradingView signals and confirmations
- `risk_manager`: read TradingView alerts for gating and rejection logic
- `portfolio_monitor`: read TradingView alerts for traceability only
- `orchestrator`: read normalized TradingView events and route workflow

## TradingView alert message example

Use JSON alert messages in TradingView, for example:

```json
{
  "symbol": "{{ticker}}",
  "timeframe": "{{interval}}",
  "alert_name": "ema_cross_confirmed",
  "strategy": "trend_following_v1",
  "signal": "entry",
  "direction": "long",
  "price": "{{close}}"
}
```

Keep the message minimal. Send trading intent and context, not credentials.

## Operational notes

- TradingView alert messages are snapshots of the alert configuration at creation time. Updating your Pine script or indicator does not retroactively rewrite already-created alerts.
- TradingView does not reliably save webhook URLs in alert presets. Recheck the webhook URL when cloning or recreating alerts.
- Broker-specific mappings are intentionally not hardcoded here yet.
  TODO: add broker/execution translation once the execution adapter is finalized.

## Migration summary

- Added a shared FastAPI webhook route for TradingView alert ingestion.
- Added backend normalization, sanitization, storage, and internal event publishing.
- Added a shared SQLAlchemy-backed database layer and TimescaleDB hypertables for shared trading data.
- Updated agent-facing read tools so Hermes Agents and Paperclip can consume normalized TradingView state from TimescaleDB without touching raw HTTP payloads.
