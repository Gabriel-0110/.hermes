# Hermes Trading Desk — Claude Code Context

## What This Is
Hermes is an autonomous crypto trading desk running on BitMart exchange.
6 AI agents coordinate via the Hermes Agent framework to trade 24/7.
Your job as Claude Code is to SUPERVISE, VERIFY, and IMPROVE the desk.
The #1 goal is PROFITS. Everything serves that goal.

## Architecture Overview
```
Claude Code Routines (you — supervisor, every few hours)
    └── Hermes Orchestrator (AI agent — decision maker, crons every 30m/4h)
            ├── position_manager.py → trail stops, manage risk
            ├── opportunity_scanner.py → find new trades
            └── desk_status.py → live portfolio state
        ├── execution-agent → places orders
        ├── market-researcher → news, sentiment
        ├── portfolio-monitor → snapshots
        ├── risk-manager → drawdown guards
        └── strategy-agent → technical scanning
```

## Key Files & Scripts
| File | Purpose |
|------|---------|
| `~/.hermes/profiles/orchestrator/memories/MEMORY.md` | **SOURCE OF TRUTH** — positions, balances, config |
| `~/.hermes/profiles/orchestrator/scripts/desk_status.py` | Live portfolio snapshot |
| `~/.hermes/profiles/orchestrator/scripts/position_manager.py` | Position risk signals |
| `~/.hermes/profiles/orchestrator/scripts/opportunity_scanner.py` | New trade candidates |
| `~/.hermes/profiles/orchestrator/scripts/daily_performance_review.py` | P&L, fees, cron logs |
| `~/.hermes/profiles/orchestrator/scripts/market_intel_briefing.py` | BTC structure, funding, RSI |
| `~/.hermes/profiles/orchestrator/config.yaml` | Agent config (approvals: off) |

## How to Run Scripts
All scripts use the hermes venv:
```bash
/Users/openclaw/.hermes/.venv/bin/python /Users/openclaw/.hermes/profiles/orchestrator/scripts/<script>.py
```

## How to Check Agent Health
```bash
# All 6 gateways
ps aux | grep "hermes_cli.main" | grep "gateway run" | grep -v grep

# Cron status
/Users/openclaw/.hermes/.venv/bin/hermes --profile orchestrator cron status

# Docker stack
docker ps --format "table {{.Names}}\t{{.Status}}"

# Gateway logs (errors)
tail -100 /Users/openclaw/.hermes/profiles/orchestrator/logs/gateway.log | grep -i error
```

## Trading Rules (NEVER VIOLATE)
- Max 5x leverage on cron-initiated trades
- Max $150 margin per new trade
- ALWAYS set TP and SL immediately after opening
- R:R must be > 2:1 from current price
- Cut losers early, trail winners
- Don't revenge trade
- Check fees before every trade proposal

## When You Find Issues
1. **Agent down** → Restart: `/Users/openclaw/.hermes/.venv/bin/hermes --profile <name> gateway start`
2. **Script broken** → Read the error, fix the Python code, test it
3. **Position unprotected** → Flag it in your report as CRITICAL
4. **Memory out of sync** → Update MEMORY.md with current state from desk_status.py
5. **Cron not firing** → Check gateway status, restart if needed

## What Success Looks Like
- All 6 agents running, 0 errors in logs
- Every position has TP and SL set
- Memory matches reality
- Profitable trades > losing trades
- Account equity trending UP over time
