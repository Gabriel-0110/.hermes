# Trading Integrations Migration Summary

## Audit result

- Searched the repo for direct usage of `COINGECKO_API_KEY`, `COINMARKETCAP_API_KEY`, `TWELVEDATA_API_KEY`, `CRYPTOPANIC_API_KEY`, `NEWS_API_KEY`, `ETHERSCAN_API_KEY`, `LUNARCRUSH_API_KEY`, and `NANSEN_API_KEY`.
- No live trading-desk code paths were found using those provider secrets directly.
- Existing trading desk risk came from overly broad agent skill assignment and lack of a dedicated internal trading tool layer.

## Changed files and why

- `backend/integrations/*`: new backend-only provider clients with auth encapsulation, retries, timeouts, and normalized outputs.
- `backend/tools/*`: new safe internal tool wrappers that validate inputs and return normalized envelopes.
- `backend/db/*`: shared SQLAlchemy session, Timescale bootstrap, ORM models, and repositories for shared time-series storage.
- `backend/tradingview/*`: shared TradingView webhook ingestion, normalization, redaction, persistence, and internal event publishing with TimescaleDB/PostgreSQL as the primary backend.
- `backend/redis_client.py` and `backend/event_bus/*`: shared Redis Streams client, event schema, publisher, consumer-group bootstrap, and worker scaffolding for live agent coordination.
- `tools/trading_tools.py`: Hermes tool registration layer for the internal trading tool surface.
- `toolsets.py`: new least-privilege trading toolsets for each agent role.
- `model_tools.py`: loads the new trading tool registry module.
- `pyproject.toml`: packages the new `backend` module tree.
- `.env.example`: documents provider env vars plus `DATABASE_URL` and local Timescale defaults without exposing secrets.
- `docker-compose.yml`: local TimescaleDB, Redis, and Hermes web runtime wiring.
- [`TRADINGVIEW_INGESTION.md`](TRADINGVIEW_INGESTION.md): operator docs for webhook ingestion and the Timescale-backed source-of-truth model.
- `docs/trading/STEP_5_MACRO_MIGRATION_SUMMARY.md`: FRED macro integration summary for shared regime and event-risk context.
- [`REDIS_STREAMS_SETUP.md`](REDIS_STREAMS_SETUP.md): local Redis setup, consumer-group bootstrap, and worker startup notes.
- [`EVENT_BUS_ARCHITECTURE.md`](EVENT_BUS_ARCHITECTURE.md): shared live-event contract and consumer-group responsibilities.
- [`REDIS_STREAMS_MIGRATION_SUMMARY.md`](REDIS_STREAMS_MIGRATION_SUMMARY.md): Redis event-bus migration summary and follow-up list.
- [`INTEGRATIONS.md`](INTEGRATIONS.md): integration architecture, security model, and extension guidance.
- [`TIMESCALE_SETUP.md`](TIMESCALE_SETUP.md): local setup steps for TimescaleDB and schema bootstrap.
- [`DB_ACCESS_POLICY.md`](DB_ACCESS_POLICY.md): agent and backend database access policy.
- [`AGENT_PROFILES.md`](AGENT_PROFILES.md): runtime-facing description of each trading agent.
- [`SKILLS_CATALOG.md`](SKILLS_CATALOG.md): catalog of reusable skill profiles and dependencies.
- `teams/trading-desk/agents.yaml`: source-of-truth policy now includes canonical agent IDs, allowed tools, allowed toolsets, forbidden actions, and expected outputs.
- `profiles/*/ROLE_SKILLS.yaml`: mirrors the least-privilege tool/skill policy at the profile level.
- `teams/trading-desk/agent_profiles/*.yaml`: explicit agent profile definitions for Hermes or Paperclip ingestion.
- `teams/trading-desk/skills/*.yaml`: explicit skill profile definitions.
- `teams/trading-desk/TEAM.md`: desk-level rule update forbidding raw provider secret access.

## Manual follow-up

- Wire `portfolio_snapshots` writes to the actual portfolio or exchange adapter.
- Replace `send_notification` stub delivery with Slack or Telegram delivery while keeping `notifications_sent` as the audit trail.
- Implement a real execution adapter behind `get_execution_status` and any future execution-request tool.
- Add pending-entry claim and recovery helpers for Redis Streams workers.
- Add broker-specific TradingView-to-execution mapping once the execution backend is chosen.
- Wire BitMart execution events into the shared Redis stream once the execution adapter contract is finalized.
- Decide where the runtime should read `allowed_toolsets` from when spawning desk agents automatically; the policy files are in place, but the automatic launcher hook is not yet implemented in this repo.
