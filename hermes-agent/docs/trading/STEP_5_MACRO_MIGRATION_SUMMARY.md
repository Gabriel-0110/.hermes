# Step 5 Macro Integration Migration Summary

## Scope

- Added a backend-only FRED integration at `backend/integrations/macro/fred_client.py`.
- Added normalized macro schemas in `backend/models.py` for series metadata, observations, regime indicators, regime summaries, and event-risk context.
- Added internal tools `get_macro_series`, `get_macro_observations`, `get_macro_regime_summary`, and `get_event_risk_macro_context`.

## Access model

- Backend credentials are read only from `FRED_API_KEY`.
- Agents never receive raw provider credentials.
- Raw FRED search and observation access is limited to `market_researcher`.
- `risk_manager` and `strategy_agent` receive only synthesized macro summaries needed for risk and regime work.
- `orchestrator_trader` and `portfolio_monitor` do not receive direct macro tool access.

## Initial coverage

- Example and default series: `UNRATE`, `SOFR180DAYAVG`, `INDPRO`.
- FRED wrapper methods cover:
  - series search
  - series metadata
  - series observations
- Tool responses are normalized into structured schemas and wrapped in the standard Hermes envelope.

## Operational notes

- FRED requests inherit the shared backend timeout, retries, and sanitized error handling from `BaseIntegrationClient`.
- Logging was added at the client and tool layers for search, metadata lookup, observation fetches, and macro summary generation.
- Minimal tests cover provider profile registration, safe failure without credentials, normalized macro outputs, and trading-tool registration.
