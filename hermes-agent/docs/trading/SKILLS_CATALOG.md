# Trading Skills Catalog

## Shared skills

- `workflow_routing`: orchestrator-only routing and task coordination. Depends on `list_trade_candidates`, `get_risk_approval`, `get_portfolio_state`, `get_execution_status`.
- `decision_aggregation`: orchestrator merge layer for research, strategy, risk, and portfolio outputs.
- `execution_requesting`: orchestrator bridge into a future execution subsystem. Depends on `get_execution_status`, `send_notification`.
- `incident_escalation`: orchestrator escalation path for failures or policy violations. Depends on `send_notification`.
- `send_structured_alert`: orchestrator or portfolio monitor notification wrapper. Depends on `send_notification`.
- `audit_logging`: shared convention for redacted audit records.

## Research skills

- `market_regime_analysis`: uses `get_market_overview`, `get_crypto_prices`, `get_ohlcv`.
- `watchlist_generation`: uses `get_crypto_prices`, `get_market_overview`, `get_smart_money_flows`.
- `catalyst_detection`: uses `get_crypto_news`, `get_general_news`, `get_event_risk_summary`.
- `narrative_shift_detection`: uses `get_social_sentiment`, `get_crypto_news`.
- `cross_asset_context`: uses `get_crypto_prices`, `get_market_overview`, `get_ohlcv`.
- `chronos2_forecasting`: uses wrapped historical time-series inputs and the shared Chronos-2 skill to produce low/median/high forward scenarios for research.

## Portfolio skills

- `pnl_tracking`: uses `get_portfolio_state`, `get_crypto_prices`.
- `exposure_tracking`: uses `get_portfolio_state`, `get_market_overview`.
- `reconciliation`: uses `get_portfolio_state`, `get_wallet_transactions`, `get_onchain_wallet_data`.
- `drift_detection`: uses `get_portfolio_state`, `get_crypto_prices`.
- `anomaly_detection`: uses `get_wallet_transactions`, `get_onchain_wallet_data`, `send_notification`.

## Risk skills

- `pretrade_risk_validation`: uses `get_ohlcv`, `get_volatility_metrics`, `get_event_risk_summary`, `get_portfolio_state`.
- `position_sizing`: uses `get_volatility_metrics`, `get_portfolio_state`.
- `drawdown_protection`: uses `get_portfolio_state`.
- `concentration_analysis`: uses `get_portfolio_state`, `get_correlation_inputs`, `get_crypto_prices`.
- `volatility_risk_control`: uses `get_volatility_metrics`, `get_ohlcv`.
- `event_risk_control`: uses `get_event_risk_summary`, `get_social_sentiment`.

## Strategy skills

- `setup_scanning`: uses `get_crypto_prices`, `get_ohlcv`, `get_indicator_snapshot`.
- `signal_scoring`: uses `get_indicator_snapshot`, `get_onchain_signal_summary`.
- `trade_plan_generation`: uses `get_crypto_prices`, `get_ohlcv`, `get_indicator_snapshot`.
- `regime_matching`: uses `get_market_overview`, `get_crypto_prices`.
- `invalidation_modeling`: uses `get_ohlcv`, `get_indicator_snapshot`.

## Skill profiles

- Canonical skill profiles live in `~/.hermes/teams/trading-desk/skills/*.yaml`.
- Each profile includes `skill_id`, `name`, `purpose`, `agents_allowed`, `tools_required`, `inputs`, `outputs`, `dependencies`, `usage_example`, `limitations`, and `audit_logging_requirements`.

## Agent to skill mapping

- `orchestrator_trader`: `workflow_routing`, `decision_aggregation`, `execution_requesting`, `incident_escalation`.
- `market_researcher`: research skills.
- `portfolio_monitor`: portfolio skills.
- `risk_manager`: risk skills.
- `strategy_agent`: strategy skills.
