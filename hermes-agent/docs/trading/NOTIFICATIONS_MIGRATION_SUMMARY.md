# Notifications Migration Summary

## Implemented in step 7

- Added shared backend-only Telegram and Slack notification clients under `backend/integrations/notifications/`.
- Replaced the `send_notification` stub with a normalized dispatcher that supports `log`, `telegram`, and `slack` routing.
- Added specialized internal tools:
  - `send_trade_alert`
  - `send_risk_alert`
  - `send_daily_summary`
  - `send_execution_update`
- Preserved the existing `send_notification` audit behavior by continuing to write every normalized result to `notifications_sent`.

## Security boundary

- Secrets are read only from environment variables in backend code.
- Agents never receive raw `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, or `SLACK_WEBHOOK_URL`.
- Logging and stored payloads are sanitized to avoid leaking obvious token or webhook values.

## Routing and normalization

- Generic notifications still default to `log` for backward compatibility.
- Specialized alert tools default to Telegram plus Slack routing.
- Multi-channel sends return a normalized result with per-channel delivery status.
- Partial delivery failures are surfaced as warnings instead of crashing the tool path.

## Agent policy updates

- `orchestrator_trader` can send trade alerts and execution updates.
- `risk_manager` can send risk alerts.
- `portfolio_monitor` can send generic portfolio alerts and execution updates.
- `market_researcher` can send daily summaries.
- `strategy_agent` remains non-notifying by default.
