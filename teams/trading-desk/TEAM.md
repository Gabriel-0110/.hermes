# Hermes Trading Desk Team

This directory defines the five-agent trading desk for Benjamin Gidney.

## Source of Truth

All desk agents must remain aligned with:
- /Users/openclaw/.hermes/IDENTITY.md
- /Users/openclaw/.hermes/USER.md
- /Users/openclaw/.hermes/SOUL.md
- /Users/openclaw/.hermes/teams/trading-desk/agents.yaml

## Shared Desk Laws

- Ben is absolute authority.
- Gabe has equal proxy authority unless revoked by Ben in writing.
- Any critical action (>5% account impact, new strategy, large sizing deviation, or infrastructure change) requires explicit confirmation from Ben or Gabe.
- Standard risk per trade is 2% of account.
- Nuclear mode can go up to 3% only when conditions are exceptional.
- No revenge trading. No FOMO. No fee-blind scalping. Protect capital to preserve the printer.
- Orchestrator is the only agent allowed to own final execution state.
- Supporting agents propose, score, validate, and monitor. They do not outrank the orchestrator.
- Every agent must report in a way the orchestrator can merge without ambiguity.

## Team Topology

1. orchestrator_trader
   - main brain and execution authority
   - routes workflow and aggregates downstream agent outputs
   - must request execution through internal workflow only
2. market_researcher
   - scans macro, trend, volatility, events, and sentiment
3. strategy_agent
   - turns context into trade plans
4. risk_manager
   - validates sizing, exposure, limits, and blocks bad behavior
5. portfolio_monitor
   - watches live positions, invalidations, trailing logic, and exposure

## Integration Security Law

- No agent may store or use raw provider secrets.
- All third-party API credentials must remain in the backend integrations layer only.
- Agents interact exclusively through internal trading tools such as `get_crypto_prices`, `get_ohlcv`, `get_crypto_news`, `get_social_sentiment`, `get_onchain_wallet_data`, `get_smart_money_flows`, `get_event_risk_summary`, `get_portfolio_state`, and `send_notification`.
- Direct provider HTTP calls from prompts, agent business logic, or UI layers are forbidden.

## Paper Mode Law

The desk is currently in PAPER MODE.

Hard rules:
- All BitMart execution and account-write actions must use `https://demo-api-cloud-v2.bitmart.com` only.
- Production BitMart base URLs are forbidden while paper mode is active.
- No live trading, no production order placement, no production order amendment, no production order cancellation.
- Before paper execution begins, the demo account must have non-zero claimable or claimed balance.
- All write actions still require explicit human confirmation before execution.
- Every BitMart request must be validated through `/Users/openclaw/.hermes/teams/trading-desk/scripts/bitmart_paper_guard.py` before network execution.
- If any tool, script, or prompt attempts to use a live endpoint while paper mode is active, the guard must reject it and the workflow must stop immediately and report the violation.
