# Hermes Post-Audit Verification + Improvement Prompt

Use this prompt after the latest profitability-audit tasks have been completed.

---

```text
Inspect the Hermes repository after the latest profitability-audit tasks were completed.

You are acting as the lead engineer, trading systems architect, risk architect, and production-readiness reviewer.

Goal:
Verify what was actually implemented, identify what is still incomplete or unsafe, and produce the next realistic improvement plan for making Hermes more profitable, faster, safer, and easier to operate.

Important context:
A previous prompt asked for a full profitability/codebase audit covering:
- repository capability map
- agents/tools/services/APIs/strategies/cron jobs/dashboards/database models
- production-ready vs partial vs unused vs broken features
- mapping features to profit use cases
- high-impact changes for profitability, signal quality, automation, and risk control
- new APIs/services/models/strategies
- implementation tasks and Codex prompts
- requests for real trading status, balances, invested capital, and active bot/copy-trade state when needed

Assume those tasks have now been completed. Your job is not to repeat the same audit vaguely. Your job is to verify the work, inspect the actual code changes, and produce the next actionable plan.

## Phase 1 — Repository change verification

1. Read the current repository structure.
2. Run `git status`.
3. Run a concise `git diff --stat`.
4. Review the actual changed files.
5. Identify:
   - new files
   - modified files
   - deleted files
   - generated files that should not be committed
   - secrets or credentials that must not be committed
   - migrations added
   - config/env changes
   - docs/report changes
   - dashboard/UI changes
   - agent/tool/strategy changes
   - exchange adapter changes
   - cron/runtime changes
   - tests added or changed

Output a table:

| Area | Files changed | Intended purpose | Verified? | Concern |
|---|---|---|---|---|

Do not trust prior summaries. Verify from the code.

## Phase 2 — Test and runtime verification

Run or inspect the best available local verification commands.

At minimum, try:

```bash
make dev-check
```

Then inspect available Makefile targets and run any relevant safe checks, such as:

```bash
make test
make lint
make typecheck
make dev-up
```

Only run commands that are safe and do not place live trades.

Also verify:

1. API health.
2. Dashboard health.
3. Mission Control health if present.
4. LiteLLM health if present.
5. Redis/Postgres/TimescaleDB health if present.
6. Gateway status.
7. Telegram connection status.
8. Slack connection status.
9. Cron wrapper validity.
10. Trading mode:
   - disabled
   - paper
   - approval-required
   - live

Output:

| Check | Command/source | Result | Blocking issue? |
|---|---|---|---|

If a command fails, diagnose the likely cause and propose the exact fix.

## Phase 3 — Trading feature verification

Inspect and verify all features relevant to profitability.

Check at least:

1. Strategy engine.
2. Signal scoring.
3. Market data ingestion.
4. Technical indicator handling.
5. News/event-risk handling.
6. Whale/liquidation tracking.
7. Copy-trading support.
8. Exchange-bot support.
9. BitMart adapter.
10. TP/SL bracket handling.
11. Approval workflow.
12. Paper/shadow fills.
13. Volatility-targeted sizing.
14. DB-backed risk limits.
15. Portfolio/balance reconciliation.
16. Drawdown guard.
17. Alerting/notifications.
18. Dashboards/reports.
19. Memory/state persistence.
20. Agent routing/coordination.

For each, output:

| Feature | Current state | Production readiness | Profit use case | Missing piece | Priority |
|---|---|---|---|---|---|

Use these readiness values only:
- Ready
- Mostly ready
- Partial
- Stub
- Broken
- Unknown

## Phase 4 — Profitability reality check

Give a realistic assessment of whether Hermes is currently capable of improving trading results.

Do not claim guaranteed profit.

Analyze:

1. Can Hermes currently detect opportunities faster than manual trading?
2. Can Hermes currently avoid obviously bad trades?
3. Can Hermes currently manage exits better than manual trading?
4. Can Hermes currently allocate capital intelligently?
5. Can Hermes currently compare bot/copy-trading opportunities?
6. Can Hermes currently react to market regime changes?
7. Can Hermes currently learn from previous trades?
8. Can Hermes currently explain why it entered/exited/blocked a trade?

Output:

| Capability | Current answer | Evidence from code | Needed improvement |
|---|---|---|---|

## Phase 5 — Immediate fixes before adding more features

Identify anything that must be fixed before adding new strategy logic.

Look specifically for:

1. Runtime instability.
2. Gateway/profile conflicts.
3. Stale state files.
4. Missing env validation.
5. Unsafe live-trade defaults.
6. Silent failures.
7. Missing alerts.
8. Incomplete BitMart order verification.
9. Incomplete TP/SL verification.
10. Broken cron execution.
11. Broken tests.
12. Missing database migration handling.
13. Missing observability.
14. Duplicate or dead code.
15. Overly complex paths that should be simplified.

Output:

| Fix | Why it matters | Exact files/modules | Suggested implementation | Priority |
|---|---|---|---|---|

## Phase 6 — Highest-impact profit improvements

Now propose the best next improvements.

Focus on practical improvements that can actually increase trading quality:

1. Better market regime detection.
2. Better trend/momentum confirmation.
3. Better volatility-aware entries.
4. Better volume/liquidity filters.
5. Better exit management.
6. Better capital rotation across BTC/ETH/SOL/XRP.
7. Better copy-trader ranking.
8. Better exchange bot ranking.
9. Better portfolio drawdown response.
10. Better signal deduplication.
11. Better post-trade learning.
12. Better risk-adjusted scoring.
13. Better use of AI agents only where they add value.
14. Better dashboards for live decisions.
15. Better human approval UX.

For each improvement, output:

| Improvement | Expected impact | Complexity | Risk | Files/modules | Implementation notes |
|---|---|---|---|---|---|

Use impact values:
- Very high
- High
- Medium
- Low

Use complexity values:
- Low
- Medium
- High

## Phase 7 — Strategy recommendations

Recommend concrete strategies Hermes should implement or improve next.

Prioritize strategies that fit a small account and active crypto trading.

Cover at least:

1. BTC/ETH momentum breakout with volatility filters.
2. SOL/XRP intraday trend continuation.
3. Mean-reversion only during sideways regimes.
4. Event-risk blackout strategy.
5. Copy-trader selection/ranking strategy.
6. Exchange-grid-bot parameter recommender.
7. Portfolio rotation strategy.
8. Defensive capital-preservation mode.
9. Post-loss cooldown and revenge-trade prevention.
10. High-volatility scalp filter, if realistic.

For each strategy:

| Strategy | When to use | When to avoid | Required data | Entry logic | Exit logic | Risk rule | Implementation priority |
|---|---|---|---|---|---|---|---|

Do not suggest vague “AI predicts market” strategies. Make the logic inspectable and testable.

## Phase 8 — Data/API/model recommendations

Recommend practical APIs, services, and models that would improve Hermes.

Compare options by cost, reliability, usefulness, and implementation effort.

Include:

1. Market data APIs.
2. News/event-risk APIs.
3. On-chain/whale APIs.
4. Sentiment APIs.
5. Exchange data APIs.
6. Copy-trading/bot scraping or manual input workflows.
7. Forecasting/time-series models.
8. Local models.
9. API models.
10. Embeddings/vector memory if useful.

Output:

| Service/model | Use case | Cost expectation | Reliability | Integration complexity | Recommendation |
|---|---|---|---|---|---|

Be realistic for a small trading operation. Prefer cheap/free where possible, but do not recommend unreliable data for critical execution.

## Phase 9 — Balance and capital-state prompt

If the repository does not have verified live balance reconciliation, produce a separate exact prompt asking the operator/user to provide current state.

The prompt should ask for:

1. Spot balances.
2. Futures balances.
3. Active grid bots.
4. Active copy trades.
5. Open positions.
6. Unrealized P&L.
7. Realized P&L.
8. Available USDT.
9. Invested USDT.
10. Bot parameters.
11. Copy-trader parameters.
12. Loss limits.
13. Manual trades not known to Hermes.

Also specify the exact JSON format Hermes should request or accept.

## Phase 10 — Final prioritized roadmap

Create a roadmap in this format:

### Must do before live automation

1. Task
   - Why
   - Files/modules
   - Acceptance criteria
   - Test/verification command

### Profitability improvements

1. Task
   - Why
   - Files/modules
   - Acceptance criteria
   - Test/verification command

### Operational improvements

1. Task
   - Why
   - Files/modules
   - Acceptance criteria
   - Test/verification command

### Dashboard/reporting improvements

1. Task
   - Why
   - Files/modules
   - Acceptance criteria
   - Test/verification command

### Later / optional

1. Task
   - Why
   - Files/modules
   - Acceptance criteria

## Phase 11 — Generate next Codex prompts

Generate the exact next Codex prompts to execute.

I need prompts for:

1. Full post-change verification and safety review.
2. Runtime/gateway/profile cleanup.
3. Trading state reconciliation and balance importer.
4. BitMart TP/SL and bracket-order verification.
5. Strategy scoring and market-regime upgrade.
6. Copy-trader and exchange-bot ranking engine.
7. Dashboard improvements for decisions and approvals.
8. Backtesting/paper-shadow analytics.
9. Post-trade learning loop.
10. Final commit-readiness review.

Each prompt must include:
- goal
- context
- files/modules to inspect
- implementation instructions
- safety constraints
- acceptance criteria
- commands to run
- expected output

Important safety constraints:
- Do not place live trades.
- Do not send real orders.
- Do not expose secrets.
- Do not commit credentials.
- Do not enable live trading by default.
- Approval-required mode must remain the default for anything that can trade.
- Any live execution path must require explicit environment flags and human confirmation.

Final output required:

1. Executive summary.
2. What is verified done.
3. What is not actually done.
4. What is broken or risky.
5. What should be done next.
6. Exact next Codex prompts.
7. Recommended order of execution.
8. Final decision: is Hermes ready for:
   - paper trading only
   - approval-required trading
   - limited live trading
   - not ready

Be direct, concrete, and code-specific.
```

---

## Recommended Usage

Run this before asking Codex to add more features. This prompt forces the agent to:

1. Prove what changed.
2. Verify safety.
3. Check runtime stability.
4. Confirm trading readiness.
5. Generate the next implementation prompts from actual repository state.

