# Hermes Trading Desk — Database Sync & Audit Logging Plan
# Authored by: orchestrator (2026-04-24)
# Delegated to: coding agent (Claude Code / Codex)
# Do NOT modify without reading the full audit findings below.

---

## AUDIT FINDINGS

### What exists

The backend has a fully-designed SQLAlchemy schema in:
  `hermes-agent/backend/db/models.py`

Tables designed for trading audit and intelligence:
  - `execution_events`      — every order attempt, fill, rejection
  - `movement_journal`      — every capital movement (buys, sells, transfers)
  - `agent_decisions`       — every agent decision with rationale
  - `agent_signals`         — scored signals from strategy scorers
  - `strategy_evaluations`  — strategy cycle output (direction, confidence, symbol)
  - `portfolio_snapshots`   — point-in-time account state
  - `risk_events`           — risk violations, kill switch triggers, drawdown alerts
  - `research_memos`        — market-researcher memos saved via save_research_memo tool
  - `workflow_runs`         — full workflow lifecycle logs
  - `tool_calls`            — every tool invocation with input/output summaries
  - `notifications_sent`    — delivery audit for every Telegram/Slack alert
  - `system_errors`         — agent errors with stack context
  - `tradingview_alert_events` — inbound TradingView webhook events

### What is broken / empty

Every trading-critical table has 0 rows. Only `messages`, `sessions`, and `tool_calls`
are being populated (Hermes internal session data — not trading data).

Root cause: `DATABASE_URL` env var is NOT set in any profile .env file.
Without it, `get_database_url()` returns None and the engine falls back to
per-profile `state.db` SQLite files — but the trading tools write to the
**shared** Postgres DB when available, and silently skip writes when it isn't.

The PostgreSQL instance IS configured:
  `postgresql://hermes:***@localhost:5433/hermes_trading`
  (port 5433, not 5432 — non-standard, likely Docker)

Redis is also configured:
  `redis://localhost:***@localhost:5433/hermes_trading`
  (note: this Redis URL has wrong port — see fix below)

### Per-profile database isolation problem

Each profile has its OWN `state.db`. This means:
- strategy-agent writes strategy_evaluations to its own SQLite
- portfolio-monitor writes portfolio_snapshots to its own SQLite
- risk-manager writes risk_events to its own SQLite
- orchestrator can't read any of it

They are completely siloed. No cross-agent audit trail exists.

---

## THE FIX — 4 tasks for coding agent

### TASK 1: Set DATABASE_URL in all profile .env files

Add to every profile .env (orchestrator, market-researcher, strategy-agent,
portfolio-monitor, risk-manager, execution-agent, hermes-agent, hermes):

  DATABASE_URL=postgresql://hermes:hermes@localhost:5433/hermes_trading

Also fix the Redis URL (wrong port — Redis default is 6379, not 5433):
  REDIS_URL=redis://localhost:6379/0

Check if Postgres is actually running on 5433:
  lsof -i :5433 || pg_lsof 5433 || docker ps | grep postgres

If it's a Docker container, verify the correct host/port mapping.
If Postgres is NOT running, fall back to a SHARED SQLite path:
  DATABASE_URL=sqlite:////Users/openclaw/.hermes/shared_trading.db

The shared SQLite path is acceptable for now — it is CROSS-PROFILE (single file,
all agents read/write the same DB). This is better than 5 isolated state.db files.

### TASK 2: Add DATABASE_URL to the env sync script

File: `/Users/openclaw/.hermes/scripts/sync_env.py` (or equivalent skill)
Also add it to the SYNC_KEYS list in the sync-env-keys skill at:
  `/Users/openclaw/.hermes/profiles/orchestrator/skills/hermes-agent/sync-env-keys/SKILL.md`

So future env syncs automatically propagate DATABASE_URL everywhere.

### TASK 3: Verify the schema bootstraps correctly against the shared DB

Run from the hermes-agent venv:
  cd /Users/openclaw/.hermes/hermes-agent
  DATABASE_URL=<confirmed_url> python3 -c "
  from backend.db import ensure_time_series_schema
  from backend.db.session import get_engine
  engine = get_engine()
  ensure_time_series_schema(engine)
  print('Schema OK')
  "

Expected output: "Schema OK" with no errors.
If TimescaleDB hypertables fail (SQLite doesn't support them), verify the
bootstrap gracefully skips hypertable creation for SQLite — check
`backend/db/bootstrap.py` for the `if backend == 'postgresql'` guard.

### TASK 4: Verify 3 critical write paths actually insert rows

After DATABASE_URL is set, test that these tools actually persist data:

Test A — strategy_evaluations (strategy-agent writes these):
  cd /Users/openclaw/.hermes/hermes-agent
  DATABASE_URL=<url> python3 -c "
  from backend.tools.evaluate_strategy import evaluate_strategy
  result = evaluate_strategy({'strategy_name': 'momentum', 'symbol': 'BTC/USD', 'timeframe': '1h'})
  print('direction:', result.get('data', {}).get('direction'))
  print('confidence:', result.get('data', {}).get('confidence'))
  "
  Then verify: sqlite3 /Users/openclaw/.hermes/shared_trading.db \
    'SELECT COUNT(*) FROM strategy_evaluations;'
  Expected: > 0

Test B — research_memos (market-researcher writes these):
  DATABASE_URL=<url> python3 -c "
  from backend.tools.save_research_memo import save_research_memo
  r = save_research_memo({'symbol': 'BTC', 'content': 'DB test memo', 'source_agent': 'test'})
  print('ok:', r.get('ok'))
  "
  Verify: sqlite3 /Users/openclaw/.hermes/shared_trading.db \
    'SELECT content FROM research_memos LIMIT 1;'

Test C — portfolio_snapshots (portfolio-monitor writes these):
  DATABASE_URL=<url> python3 -c "
  from backend.services.portfolio_sync import sync_portfolio_snapshot
  sync_portfolio_snapshot()
  " 2>&1 | head -20

---

## WHAT THIS ENABLES (why it matters)

Once all agents share one DATABASE_URL:

1. AUDIT TRAIL — every execution_event, movement_journal entry, and agent_decision
   is permanently logged. Investors can query exactly what happened and when.

2. STRATEGY PERFORMANCE TRACKING — strategy_evaluations accumulates over time.
   After 2 weeks of cron runs, we can query win rate, best-performing strategy,
   best-performing symbol. Real data, not guesses.

3. PORTFOLIO HISTORY — portfolio_snapshots taken every 15min by portfolio-monitor
   builds a complete equity curve. Can chart account growth over time.

4. CROSS-AGENT RESEARCH — research_memos saved by market-researcher are readable
   by strategy-agent and orchestrator via get_research_memos tool. Currently broken
   because each reads its own isolated SQLite.

5. ERROR MONITORING — system_errors table logs every agent error. Can build a
   weekly error digest cron that reads this table and reports unresolved issues.

---

## VERIFICATION AFTER COMPLETING ALL TASKS

Run this and confirm all counts > 0 after one strategy cycle fires:

  python3 << 'EOF'
  import sqlite3
  # adjust path if using postgres
  db = '/Users/openclaw/.hermes/shared_trading.db'
  conn = sqlite3.connect(db)
  tables = ['strategy_evaluations', 'research_memos', 'tool_calls',
            'portfolio_snapshots', 'execution_events', 'system_errors']
  for t in tables:
      try:
          c = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
          status = 'OK' if c > 0 else 'EMPTY'
          print(f'{status:6} {t}: {c} rows')
      except Exception as e:
          print(f'ERROR  {t}: {e}')
  conn.close()
  EOF

Report the output back to orchestrator via Telegram once complete.

---

## FILES TO TOUCH (summary)

1. All profile .env files — add DATABASE_URL (use env sync script)
2. ~/.hermes/hermes-agent/backend/db/session.py — verify SQLite shared path fallback
3. ~/.hermes/hermes-agent/backend/db/bootstrap.py — verify hypertable guard for SQLite
4. ~/.hermes/scripts/funding_rate_monitor.py — no change needed
5. ~/.hermes/profiles/orchestrator/skills/hermes-agent/sync-env-keys/SKILL.md
   — add DATABASE_URL to SYNC_KEYS list

Do NOT touch: models.py (schema is correct), tools/*.py (write paths are correct),
strategy runners (already call ensure_time_series_schema).

---
END OF PLAN
