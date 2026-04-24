# CCXT Execution Migration Summary

## Added

- Shared backend execution integration under `backend/integrations/execution/ccxt_client.py`
- Normalized execution schemas in `backend/models.py` for balances, orders, trades, and status
- Backend-safe BitMart tool wrappers for balances, open orders, order placement/cancellation, order history, trade history, and execution status
- Backend-only BitMart environment placeholders in `.env.example`
- `ccxt` dependency entries in `pyproject.toml` and `requirements.txt`

## Integrated

- `tools/trading_tools.py` now registers the execution wrappers for Hermes runtime dispatch
- `toolsets.py` now enforces the requested least-privilege execution mapping:
  - `orchestrator_trader`: `place_order`, `cancel_order`, `get_execution_status`
  - `portfolio_monitor`: `get_exchange_balances`, `get_open_orders`, `get_order_history`, `get_trade_history`
  - `risk_manager`: `get_exchange_balances`, `get_open_orders`, `get_execution_status`
  - `strategy_agent`: no direct execution permissions
  - `market_researcher`: no direct execution permissions
- `AGENT_PROFILES.md` and `INTEGRATIONS.md` now document the same backend-only execution boundary
- `BITMART_EXECUTION_SUPPORT.md` documents the direct futures API lane, readiness semantics, and the explicit unsupported/unproven copy-trading automation boundary

## Security and backend boundary

- BitMart credentials are read only from `BITMART_API_KEY`, `BITMART_SECRET`, and `BITMART_MEMO`
- Credentials remain in the backend integration layer and are never exposed through tool payloads
- Execution logging is sanitized to avoid leaking API key, secret, memo, signatures, or raw request payloads
- Tool outputs are normalized and safe for agent consumption
- `api_execution_ready` applies only to direct futures API execution. It does not imply BitMart copy-trading API automation is supported.
- Browser/UI interaction remains operator-assisted fallback only and must not be used as an autonomous execution mechanism.

## Deferred follow-up

- Confirm any BitMart-specific hedge-mode / position-side flags against live exchange responses beyond the current reduce-only futures close path
- Validate any exchange-specific order and trade field nuances against live BitMart responses before adding richer execution analytics
- Prove and document a real BitMart copy-trading API surface before treating copy trading as API-ready
