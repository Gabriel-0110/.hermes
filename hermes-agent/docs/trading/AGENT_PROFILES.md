# Trading Agent Profiles

## orchestrator_trader

- Role: central coordinator and workflow router.
- Allowed tools: `list_trade_candidates`, `get_risk_approval`, `get_portfolio_state`, `place_order`, `cancel_order`, `send_trade_alert`, `send_execution_update`, `get_execution_status`, `get_recent_tradingview_alerts`, `get_pending_signal_events`, `get_tradingview_alert_context`.
- Forbidden actions: raw provider access, raw secret access, direct provider HTTP calls.
- Skills: `workflow_routing`, `decision_aggregation`, `execution_requesting`, `incident_escalation`.
- Expected outputs: approved action plan, trade execution request, workflow summary, alert decisions.

## market_researcher

- Role: market context, regime, catalyst, and watchlist intelligence.
- Allowed tools: `get_crypto_prices`, `get_market_overview`, `get_ohlcv`, `get_crypto_news`, `get_general_news`, `get_macro_series`, `get_macro_observations`, `get_macro_regime_summary`, `get_defi_protocols`, `get_defi_protocol_details`, `get_defi_chain_overview`, `get_defi_yields`, `get_defi_dex_overview`, `get_defi_fees_overview`, `get_defi_regime_summary`, `get_social_sentiment`, `get_onchain_wallet_data`, `get_smart_money_flows`, `get_event_risk_summary`, `send_daily_summary`, `get_tradingview_alert_context`.
- Forbidden actions: trade placement, direct execution access, direct secret access.
- Skills: `market_regime_analysis`, `watchlist_generation`, `catalyst_detection`, `narrative_shift_detection`, `cross_asset_context`, `chronos2_forecasting`.
- Expected outputs: regime summary, catalyst summary, ranked watchlist, risk notes, research memo, forecast scenario package.
- Chronos-2 ownership: Amazon Chronos-2 forecasting belongs to `market_researcher`; it is a research/intelligence capability that produces forecast context for downstream strategy work rather than direct trade actions.

## portfolio_monitor

- Role: source of truth for positions, balances, exposure, and reconciliation.
- Allowed tools: `get_portfolio_state`, `get_exchange_balances`, `get_open_orders`, `get_order_history`, `get_trade_history`, `get_crypto_prices`, `get_market_overview`, `get_onchain_wallet_data`, `get_wallet_transactions`, `send_notification`, `send_execution_update`, `get_recent_tradingview_alerts`, `get_tradingview_alert_by_symbol`.
- Forbidden actions: discretionary strategy generation, raw secret exposure.
- Skills: `pnl_tracking`, `exposure_tracking`, `reconciliation`, `drift_detection`, `anomaly_detection`.
- Expected outputs: portfolio health summary, PnL snapshot, reconciliation report, drift alert.

## risk_manager

- Role: hard gatekeeper for risk controls.
- Allowed tools: `get_ohlcv`, `get_volatility_metrics`, `get_correlation_inputs`, `get_event_risk_summary`, `get_macro_regime_summary`, `get_event_risk_macro_context`, `get_defi_chain_overview`, `get_defi_yields`, `get_defi_fees_overview`, `get_defi_open_interest`, `get_defi_regime_summary`, `get_social_sentiment`, `get_onchain_wallet_data`, `get_smart_money_flows`, `get_portfolio_state`, `get_exchange_balances`, `get_open_orders`, `get_execution_status`, `get_crypto_prices`, `send_risk_alert`, `get_recent_tradingview_alerts`, `get_tradingview_alert_by_symbol`, `get_tradingview_alert_context`.
- Forbidden actions: workflow bypass, raw direct execution.
- Skills: `pretrade_risk_validation`, `position_sizing`, `drawdown_protection`, `concentration_analysis`, `volatility_risk_control`, `event_risk_control`.
- Expected outputs: risk approval or rejection, max size recommendation, stop/invalidation guidance, risk flags.

## strategy_agent

- Role: generate structured trade ideas from market data and research context.
- Allowed tools: `get_crypto_prices`, `get_ohlcv`, `get_indicator_snapshot`, `get_market_overview`, `get_macro_regime_summary`, `get_defi_regime_summary`, `get_defi_protocol_details`, `get_onchain_signal_summary`, `get_smart_money_flows`, `get_recent_tradingview_alerts`, `get_pending_signal_events`, `get_tradingview_alert_context`.
- Forbidden actions: direct execution, execution-status access, direct notification delivery, raw unwrapped news access.
- Skills: `setup_scanning`, `signal_scoring`, `trade_plan_generation`, `regime_matching`, `invalidation_modeling`.
- Expected outputs: structured trade candidate, confidence score, entry/stop/target plan, invalidation logic.
- Forecasting boundary: `strategy_agent` may consume forecast packages from research, but does not own the Chronos-2 forecasting skill directly.

## TradingView ingestion rule

- No agent should parse raw TradingView webhook HTTP requests directly.
- Agents read only normalized TradingView alert records and internal event projections through the trading toolset.

## Runtime notes

- Hermes enforcement currently happens through toolsets. The repo now includes `trading-orchestrator`, `trading-research`, `trading-portfolio`, `trading-risk`, and `trading-strategy` toolsets for least-privilege runtime selection.
- Step 8 adds a LiteLLM gateway contract for model selection. Hermes or Paperclip loaders should prefer stable route names such as `orchestrator-default`, `research-cheap`, `research-strong`, `risk-stable`, `strategy-default`, and `local-fast` instead of embedding provider-native model ids in agent manifests.
- Route-to-provider mapping now belongs to the backend-facing LiteLLM layer (`litellm_config.yaml` plus `litellm_gateway` / `providers.litellm` config), not to individual agents. This keeps provider swaps, failover order, and spend policy out of agent prompts.
- Upstream provider credentials remain backend-only. Agents may receive the LiteLLM client key and route names, but they must never receive raw `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, or other upstream secrets.
- Redis Streams now provides the shared live event bus on `events:trading` with consumer groups `orchestrator_group`, `strategy_group`, `risk_group`, and `notifications_group`.
- Event routing expectations:
  orchestrator consumes workflow-routing events, strategy consumes setup and signal events, risk consumes risk-review events, portfolio monitoring reads execution and account updates through the shared event contract, and notifications consumes alert and report events.
- The desk manifests under `~/.hermes/teams/trading-desk/` mirror the same policy so Paperclip or Hermes-specific loaders can consume them directly.
