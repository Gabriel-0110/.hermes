# Notifications Setup

## Purpose

Hermes now routes trading notifications through shared backend-only Telegram and Slack integrations. Agent-facing tools never receive raw bot tokens, chat IDs, or webhook URLs.

## Environment variables

Set these only in the backend runtime environment:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SLACK_WEBHOOK_URL`

You can enable either channel independently or both together.

## Delivery model

- `send_notification` is the generic normalized notification tool.
- `send_trade_alert` is for trade lifecycle events.
- `send_risk_alert` is for risk escalations.
- `send_daily_summary` is for research or operator summaries.
- `send_execution_update` is for order and execution status changes.

All notification tools:

- validate inputs before delivery
- sanitize obvious secret-like values from payload text and metadata
- retry transient HTTP failures
- use bounded HTTP timeouts
- write the final normalized result to `notifications_sent`

## Routing

Supported explicit routes:

- `telegram`
- `slack`
- `log`

Examples:

- `{"channel": "telegram", "message": "BTC breakout confirmed"}`
- `{"channels": ["telegram", "slack"], "title": "Risk Alert", "message": "Reduce exposure"}`
- `{"channel": "log", "message": "Audit-only note"}`

If a specialized alert tool is used without a route, Hermes defaults to both `telegram` and `slack`, then records any unavailable channel as a warning. The generic `send_notification` tool keeps the legacy default of `log`.

## Security notes

- Credentials stay under `backend/integrations/notifications/*`.
- Notification clients do not log raw tokens, chat IDs, or webhook URLs.
- Agent-visible tool responses contain normalized delivery status only.
- Audit payloads are stored in sanitized form.

## Paperclip compatibility

- The tool surface stays normalized and backend-owned.
- The persisted audit trail remains `notifications_sent`.
- Routing uses stable channel names instead of provider-specific request shapes.
