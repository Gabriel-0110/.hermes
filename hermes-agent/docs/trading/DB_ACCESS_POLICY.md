# DB Access Policy

## Rules

- TimescaleDB/PostgreSQL is the primary source of truth for TradingView/shared time-series data in Hermes.
- All database access must stay in shared backend-owned modules under `backend.db` and backend tool/service layers that depend on them.
- Agents must not create their own database engines, sessions, cursors, or raw SQL connections.
- Secrets such as `DATABASE_URL` must stay in environment configuration, never in agent configs, prompts, or tool payloads.
- SQLite `state.db` is fallback-only and must not be treated as the canonical trading data store.

## Shared tables

- `tradingview_alert_events`
- `tradingview_internal_events`
- `agent_signals`
- `portfolio_snapshots`
- `risk_events`
- `notifications_sent`

## Access expectations by role

- `market_researcher`: read `tradingview_alert_events`
- `strategy_agent`: read `tradingview_alert_events`, write `agent_signals`
- `risk_manager`: read `tradingview_alert_events`, `portfolio_snapshots`, and `agent_signals`; write `risk_events`
- `portfolio_monitor`: write `portfolio_snapshots`; later write orders/fills when those tables are added
- `orchestrator`: primarily read shared workflow/state tables and route work

## Implementation guidance

- Use `backend.db.session` for engine/session lifecycle.
- Use `backend.db.repositories.HermesTimeSeriesRepository` for shared reads/writes.
- Keep ORM models in `backend.db.models`.
- Keep schema bootstrap and hypertable promotion in `backend.db.bootstrap`.
- TODO: add explicit service modules for agent signal, risk, and portfolio writes as those producers are wired into Hermes runtime flows.
