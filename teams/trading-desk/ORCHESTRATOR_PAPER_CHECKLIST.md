# Orchestrator Live Trading Checklist

## 0. Hard Guardrail
- Confirm live runtime unlock is active before any execution call:
  - `HERMES_TRADING_MODE=live`
  - `HERMES_ENABLE_LIVE_TRADING=true`
  - `HERMES_LIVE_TRADING_ACK=I_ACKNOWLEDGE_LIVE_TRADING_RISK`
- Confirm production BitMart endpoint and account context are the intended target before any network call.
- If live unlock is missing, account state is unclear, or infra is degraded, stop immediately and report the blocker.

## 1. Market Check
- Confirm system/service status.
- Pull symbol details, top-of-book, last price, funding, and open interest.
- Confirm spread is sane and instrument status is `Trading`.
- Record fees before proposing a trade.
- If market conditions are unclear or edge is weak, choose no-trade.

## 2. Strategy Proposal
- State setup type and thesis in one sentence.
- Define symbol, side, entry type, entry price, stop, TP1/TP2, invalidation.
- Include fee-aware expected R multiple after fees.
- State confidence and why the edge is worth deploying in live mode.

## 3. Risk Approval
- Read live balance and confirm available margin/funds.
- Check current positions, open orders, and position mode.
- Size from explicit risk budget; default desk risk is 2% max unless Ben/Gabe explicitly authorizes deviation.
- Reject if runtime unlock is missing, risk is oversized, R:R is poor after fees, infra is degraded, or exposure conflicts exist.

## 4. Execution Confirmation
- Present the exact order payload and target base URL.
- Explicitly label whether the order is limit or market and whether it opens, reduces, or closes exposure.
- Require human confirmation word-for-word before any write call unless Ben/Gabe has explicitly removed that requirement for the run.
- If no confirmation is given, stop at prepared order only.

## 5. Monitoring Loop
- After execution, verify order status and position state from the exchange.
- Track fills, unrealized PnL, liquidation, stop/TP status, and open exposure.
- Update only on rule-based triggers: fill, partial fill, stop move, TP hit, invalidation, or risk breach.
- If conditions degrade or the thesis invalidates, prepare the exit order and require confirmation for any write action unless standing authority says otherwise.

## 6. End-of-Run Log
- Capture market snapshot, proposal, risk numbers, execution decision, and next monitoring trigger.
- Note whether the run ended at prepared-order stage or actual live execution.
