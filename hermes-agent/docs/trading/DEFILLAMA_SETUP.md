# DefiLlama Setup

## Scope

Step 10 adds a shared DefiLlama integration for Hermes under:

- [backend/integrations/defi/defillama_client.py](../../backend/integrations/defi/defillama_client.py)

This integration uses the free public API base URL only:

- `https://api.llama.fi`

No API key is required for the current Hermes integration.

## What Hermes wraps

Hermes exposes these internal tools:

- `get_defi_protocols`
- `get_defi_protocol_details`
- `get_defi_chain_overview`
- `get_defi_yields`
- `get_defi_dex_overview`
- `get_defi_fees_overview`
- `get_defi_open_interest`
- `get_defi_regime_summary`

Wrapped endpoint coverage on the free `api.llama.fi` surface:

- `/protocols`
- `/protocol/{slug}`
- `/v2/chains`
- `/overview/dexs`
- `/overview/fees`
- `/pools` when available on the configured free surface
- `/overview/derivatives` when available on the configured free surface

## Access model

- Hermes agents do not call DefiLlama directly.
- All DefiLlama HTTP logic stays inside `backend.integrations.defi`.
- Agents consume only normalized tool outputs and provider-status metadata.
- This keeps Hermes and Paperclip compatible with future endpoint migrations or paid-plan upgrades.

## Agent mapping

- `market_researcher`
  uses `get_defi_protocols`, `get_defi_protocol_details`, `get_defi_chain_overview`, `get_defi_yields`, `get_defi_dex_overview`, `get_defi_fees_overview`, `get_defi_regime_summary`
- `risk_manager`
  uses `get_defi_chain_overview`, `get_defi_yields`, `get_defi_fees_overview`, `get_defi_open_interest`, `get_defi_regime_summary`
- `strategy_agent`
  uses `get_defi_regime_summary` and may optionally call `get_defi_protocol_details`
- `orchestrator_trader`
  does not get raw DefiLlama access
- `portfolio_monitor`
  does not get raw DefiLlama access in v1

## Known free-tier constraints as of April 16, 2026

- `/overview/dexs` and `/overview/fees` are available on `api.llama.fi`.
- `/overview/derivatives` currently returns a paid-plan response on the free tier.
- `/pools` is not consistently available on the free `api.llama.fi` base URL.

Hermes handles those constraints like this:

- `get_defi_yields` returns a safe `endpoint_not_available` error if pools are not exposed.
- `get_defi_open_interest` returns `access_level=partial` and a derivatives-TVL proxy if the paid derivatives endpoint is unavailable.
- `get_defi_regime_summary` carries those limitations forward in warnings instead of hiding them.

## Validation

Recommended checks after changes:

- `pytest tests/backend/test_defillama_tools.py tests/backend/test_provider_profiles.py tests/test_toolsets.py`

## Upgrade path

If Hermes later moves to a paid DefiLlama plan:

1. Keep the same internal tool names.
2. Upgrade only the backend client behavior.
3. Remove the open-interest fallback once `/overview/derivatives` is available.
4. Enable richer yields handling if the pools endpoint becomes available from the configured base URL.
