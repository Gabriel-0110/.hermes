# Trading Integrations

## Purpose

The trading stack now treats third-party data providers as backend-only integrations. Agents must never read raw provider secrets or make direct provider HTTP calls. Agents only interact with internal tools registered in the Hermes `trading` toolset.

Step 8 adds LiteLLM as the centralized LLM gateway for Hermes and Paperclip-compatible runtimes. The gateway is the OpenAI-compatible edge that agents hit; upstream providers stay behind it.

## Providers

| Provider | Purpose | Backend env var | Wrapped internal tools |
| --- | --- | --- | --- |
| COINGECKO | Crypto spot prices, market caps, global market context | `COINGECKO_API_KEY` | `get_crypto_prices`, `get_market_overview`, `get_portfolio_valuation` |
| COINMARKETCAP | Crypto quotes, listings, rankings, market-wide intelligence | `COINMARKETCAP_API_KEY` | `get_crypto_prices`, `get_market_overview`, `get_asset_rankings` |
| TWELVEDATA | OHLCV, indicators, time-series inputs | `TWELVEDATA_API_KEY` | `get_ohlcv`, `get_indicator_snapshot`, `get_volatility_metrics`, `get_correlation_inputs` |
| FRED | Macro time series, metadata, and regime context | `FRED_API_KEY` | `get_macro_series`, `get_macro_observations`, `get_macro_regime_summary`, `get_event_risk_macro_context` |
| CRYPTOPANIC | Crypto-native news and narratives | `CRYPTOPANIC_API_KEY` | `get_crypto_news`, `get_event_risk_summary` |
| NEWSAPI | Macro and general-news context | `NEWS_API_KEY` | `get_general_news`, `get_event_risk_summary` |
| ETHERSCAN | Wallet activity and EVM transfers | `ETHERSCAN_API_KEY` | `get_onchain_wallet_data`, `get_wallet_transactions`, `get_token_activity` |
| LUNARCRUSH | Social sentiment and engagement trends | `LUNARCRUSH_API_KEY` | `get_social_sentiment`, `get_social_spike_alerts` |
| NANSEN | Smart-money analytics and labeled wallets | `NANSEN_API_KEY` | `get_smart_money_flows`, `get_labeled_wallet_activity`, `get_onchain_signal_summary` |
| DEFILLAMA | Free DeFi protocol, chain, DEX, fee, yield, and regime intelligence from the public `api.llama.fi` surface | None required for the free API | `get_defi_protocols`, `get_defi_protocol_details`, `get_defi_chain_overview`, `get_defi_yields`, `get_defi_dex_overview`, `get_defi_fees_overview`, `get_defi_open_interest`, `get_defi_regime_summary` |
| BITMART (via CCXT) | Spot execution, balances, order state, and trade history | `BITMART_API_KEY`, `BITMART_SECRET`, `BITMART_MEMO` | `get_exchange_balances`, `get_open_orders`, `place_order`, `cancel_order`, `get_order_history`, `get_trade_history`, `get_execution_status` |
| LiteLLM gateway | Centralized model routing, fallback ordering, and spend/budget enforcement for Hermes/Paperclip agents | `LITELLM_API_KEY` or `LITELLM_MASTER_KEY` at the client edge; upstream keys remain backend-only | Route names such as `orchestrator-default`, `research-cheap`, `research-strong`, `risk-stable`, `strategy-default`, `local-fast` |

## Where keys belong

- Secrets live only in the backend environment seen by `backend.integrations.*`.
- Hermes agents and Paperclip workers should point to LiteLLM as their OpenAI-compatible endpoint and use named routes, not raw upstream provider credentials.
- Do not place these keys in agent prompts, skill files, frontend code, or team manifests.
- Do not pass them through MCP tool payloads, model messages, or notification content.
- For execution providers, agents must never receive raw exchange credentials, signed payloads, or raw CCXT client objects.

## Protection model

- Each provider client reads exactly one env var in `backend.integrations`.
- LiteLLM should read upstream provider keys from the backend environment and expose only a proxy key plus route names to Hermes/Paperclip.
- Execution adapters may read a small credential set when the upstream exchange requires it, but those credentials still remain backend-only and never leave `backend.integrations`.
- DefiLlama's free public API does not require credentials. Hermes still wraps it in `backend.integrations.defi` so the raw HTTP surface, endpoint compatibility handling, and paid-endpoint fallbacks remain backend-owned.
- Auth headers and query params are encapsulated inside the provider client classes.
- Internal tool responses return normalized data and provider-status metadata, not raw credentials.
- Errors are sanitized and are meant to be safe to surface to agents or operators.
- Shared TradingView and trading time-series persistence is backend-owned through `backend.db.*` and TimescaleDB/PostgreSQL via `DATABASE_URL`.
- Agents must not open ad hoc SQL connections or embed database credentials in prompts, configs, or skill files.

## Execution integration notes

- BitMart execution now lives under `backend/integrations/execution/ccxt_client.py`.
- The shared execution adapter enables CCXT rate limiting and injects the BitMart memo during client setup.
- Execution wrappers expose only normalized balances, orders, trades, and status records.
- `orchestrator_trader` can request placement/cancellation/status, `portfolio_monitor` can inspect balances and history, and `risk_manager` can inspect balances/open orders/status.
- `strategy_agent` and `market_researcher` do not have direct execution permissions.

## DeFi integration notes

- DefiLlama access now lives under [backend/integrations/defi/defillama_client.py](../../backend/integrations/defi/defillama_client.py).
- Hermes targets the free `https://api.llama.fi` base URL only for Step 10.
- Wrapped free endpoints currently include `/protocols`, `/protocol/{slug}`, `/v2/chains`, `/overview/dexs`, and `/overview/fees`.
- Hermes also attempts `/pools` and `/overview/derivatives`, but these are not reliably available on the current free `api.llama.fi` surface.
- `get_defi_yields` fails safely with `endpoint_not_available` when pools/yields are absent from the configured free surface.
- `get_defi_open_interest` returns a documented partial fallback when `/overview/derivatives` requires a paid plan: Hermes ranks derivatives protocols using public TVL/trend data and marks the access level as `partial`.
- `get_defi_regime_summary` is designed for `market_researcher`, `risk_manager`, and `strategy_agent` and synthesizes chain TVL, DEX activity, fee momentum, yields when available, and the open-interest read/fallback into one normalized summary.

## Macro integration notes

- FRED access now lives under `backend/integrations/macro/fred_client.py`.
- `get_macro_series` supports either series search or exact metadata lookup for a known series id.
- `get_macro_observations` returns normalized values plus the series metadata used to interpret them.
- `get_macro_regime_summary` and `get_event_risk_macro_context` synthesize FRED data into agent-safe summaries for regime and event-risk workflows.
- Example series used in docs and tests: `UNRATE`, `SOFR180DAYAVG`, and `INDPRO`.

## Adding a new provider later

1. Add a `ProviderProfile` in [backend/integrations/provider_profiles.py](../../backend/integrations/provider_profiles.py).
2. Add a client under the matching category in `backend/integrations/`.
3. Normalize raw upstream responses into shared models from [backend/models.py](../../backend/models.py).
4. Wrap the provider through one or more `backend/tools/*.py` modules.
5. Register the safe tool surface in [tools/trading_tools.py](../../tools/trading_tools.py).
6. Update [toolsets.py](../../toolsets.py), [AGENT_PROFILES.md](AGENT_PROFILES.md), and [SKILLS_CATALOG.md](SKILLS_CATALOG.md).

## Extension points

- LiteLLM route policy: update [litellm_config.yaml](../../litellm_config.yaml) when you need to rebalance providers, add explicit fallback pools, or introduce per-route budget controls.
- Hermes/Paperclip gateway wiring: use the generated `providers.litellm` or `litellm_gateway` config plus named routes instead of hardcoding provider-native model names in agent manifests.
- TradingView webhook ingestion: implemented through the shared `POST /webhooks/tradingview` pipeline, with normalized alert storage and internal event publishing.
- Broker execution providers: add an execution integration package and replace the current `get_execution_status` stub.
- Slack or Telegram notifications: replace the `send_notification` stub with a notification backend adapter.
- Database-backed caching: insert a cache layer below `BaseIntegrationClient.request()`.
- Additional Timescale-backed repositories/services: persist normalized backend-owned outputs, not raw provider payloads.
- Additional onchain or sentiment providers: follow the same provider-profile + normalized-tool pattern.
