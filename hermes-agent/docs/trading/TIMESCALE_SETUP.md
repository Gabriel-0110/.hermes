# TimescaleDB Setup

## Source of truth

TradingView/shared time-series storage in Hermes now uses TimescaleDB on PostgreSQL as the primary source of truth when `DATABASE_URL` is configured.

Hermes automatically:

- creates the shared tables
- enables the `timescaledb` extension
- promotes supported time-series tables to hypertables
- runs the shared bootstrap during dashboard startup when `DATABASE_URL` is set

SQLite `state.db` remains only as a fallback for legacy or test scenarios.

## Local startup

1. Copy `.env.example` to `.env` if you are running Hermes outside Docker.
2. Set `DATABASE_URL`, for example:

```env
DATABASE_URL=postgresql+psycopg://hermes:hermes@localhost:5432/hermes_trading
TRADINGVIEW_WEBHOOK_SECRET=replace_with_shared_secret
```

3. Start TimescaleDB locally:

```bash
docker compose up -d timescaledb
```

The local Timescale container now includes a startup wrapper that ensures the
Hermes application role and database exist even if the Postgres data volume was
initialized earlier with different credentials.

4. Optionally start Hermes in Docker with the shared DB prewired:

```bash
docker compose up -d hermes
```

5. Start Hermes locally if preferred:

```bash
source venv/bin/activate
pip install -e ".[web]"
python -m hermes_cli.main web
```

## Shared tables

- `tradingview_alert_events`
- `tradingview_internal_events`
- `agent_signals`
- `portfolio_snapshots`
- `risk_events`
- `notifications_sent`

## Hypertables

Hermes promotes these tables to hypertables during bootstrap:

- `tradingview_alert_events(event_time)`
- `tradingview_internal_events(event_time)`
- `agent_signals(signal_time)`
- `portfolio_snapshots(snapshot_time)`
- `risk_events(event_time)`
- `notifications_sent(sent_time)`

The current implementation uses `create_hypertable(..., by_range(...), if_not_exists => TRUE, migrate_data => TRUE)`.

## Operational notes

- The TradingView webhook route stays at `POST /webhooks/tradingview`.
- The live `dashboard` startup path now runs the shared DB bootstrap during FastAPI startup, so container logs show started/succeeded/failed bootstrap status.
- The Timescale container startup also ensures the configured Hermes role/database exist before Hermes connects.
- Agent-facing TradingView read tools now read from the shared DB layer, not directly from `state.db`.
- If `DATABASE_URL` is missing, Hermes falls back to SQLite storage for compatibility.
- TODO: add a dedicated migration runner if schema evolution needs versioned migrations beyond bootstrap creation.
