# Orchestrator Paper Trading Checklist

## 0. Hard Guardrail
- Validate every BitMart request through `scripts/bitmart_paper_guard.py` before any network call.
- Allowed execution base URL in paper mode: `https://demo-api-cloud-v2.bitmart.com`
- Forbidden live base URLs:
  - `https://api-cloud-v2.bitmart.com`
  - `https://api-cloud.bitmart.com`
- If the guard rejects the URL, stop immediately and report the violation.

Example wrapper:
```bash
python3 /Users/openclaw/.hermes/teams/trading-desk/scripts/bitmart_paper_guard.py \
  --base-url https://demo-api-cloud-v2.bitmart.com \
  --method GET \
  --path /contract/private/assets-detail -- \
  curl -s -H "X-BM-KEY: $BITMART_API_KEY" \
       -H "User-Agent: bitmart-skills/futures/v2026.3.23" \
       "https://demo-api-cloud-v2.bitmart.com/contract/private/assets-detail"
```

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
- State confidence and reason for paper test if this is operational validation rather than alpha deployment.

## 3. Risk Approval
- Read demo balance and confirm non-zero funds.
- Check current positions, open orders, and position mode.
- Size from explicit risk budget; default desk risk is 2% max, but first operational paper test should use the minimum practical contract size unless Ben/Gabe says otherwise.
- Reject if live URL, oversized risk, poor R:R, or conflicting exposure is detected.

## 4. Execution Confirmation
- Present the exact order payload and target base URL.
- Explicitly label whether the order is paper-only and whether it is limit or market.
- Require human confirmation word-for-word before any write call.
- If no confirmation is given, stop at prepared order only.

## 5. Monitoring Loop
- After execution, verify order status and position state from the exchange.
- Track fills, unrealized PnL, liquidation, stop/TP status, and open exposure.
- Update only on rule-based triggers: fill, partial fill, stop move, TP hit, invalidation, or risk breach.
- If conditions degrade or the paper thesis invalidates, prepare the exit order and require confirmation for any write action.

## 6. End-of-Run Log
- Capture market snapshot, proposal, risk numbers, execution decision, and next monitoring trigger.
- Note whether the run ended at prepared-order stage or actual paper execution.
