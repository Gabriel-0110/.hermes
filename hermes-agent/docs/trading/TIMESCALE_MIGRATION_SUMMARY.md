# Timescale Migration Summary

## What changed

- Added a shared SQLAlchemy database layer in `backend.db`.
- Added TimescaleDB/PostgreSQL support via `DATABASE_URL`.
- Added local Docker Compose support for TimescaleDB and Hermes web runtime.
- Added bootstrap-based schema creation and hypertable promotion.
- Wired the shared DB bootstrap into the live dashboard startup path used by the Docker container.
- Added a Timescale container startup wrapper that provisions the Hermes DB role/database for local Docker environments.
- Moved TradingView ingestion persistence to the shared DB layer.
- Updated TradingView read tools to read through the shared DB layer.
- Kept SQLite `state.db` only as a fallback when `DATABASE_URL` is absent or when a test explicitly passes `db_path`.

## Shared tables

- `tradingview_alert_events`
- `tradingview_internal_events`
- `agent_signals`
- `portfolio_snapshots`
- `risk_events`
- `notifications_sent`

## Manual follow-up

- Wire real `portfolio_snapshots` producers from the portfolio/account backend.
- Wire real `agent_signals` producers from strategy workflows.
- Wire real `risk_events` producers from the risk manager workflow.
- Replace notification stub delivery while preserving `notifications_sent` writes.
- Add versioned migrations if the schema starts evolving beyond bootstrap creation.
