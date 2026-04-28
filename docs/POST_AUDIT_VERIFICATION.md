# Hermes Post-Audit Verification Report

Date: 2026-04-25
Reviewer role: Lead engineer / trading-systems architect / risk architect / production-readiness reviewer
Repo HEAD: `8a7540d` ("Refactor trading strategy runners and risk management tools")
Working tree: 2 modified, 1 untracked (this prompt file).

> ⚠️ Note: `FULL_REPORT.md` in the repo root is **NOT** a real audit report — it is a dump of tool-call logs from a previous Copilot session (`Created 6 todos`, `Read [...]` lines). It must be regenerated or deleted. This file (`POST_AUDIT_VERIFICATION.md`) supersedes it.

---

## Executive summary

The previous "profitability audit" prompt was executed and produced **substantive code changes** (≈10 commits, ~60 new modules, 22+ new test files, 4 new alembic migrations, 5 new strategies, copy-trader curator job, drawdown guard, paper-shadow fills, BitMart execution gating, and a 676-line `ops_status` CLI). The code is real, not theatre. However:

1. **The summary report was never written** — the root `FULL_REPORT.md` is a tool-log artifact, not the deliverable.
2. **The alembic migration DAG is broken** — two `0005_*` revisions branch off `0004` and one references a non-existent down-revision (`"0004_paper_shadow_fills"`); `alembic upgrade head` will fail or produce a multi-head error.
3. **Tests do not pass cleanly**: `tests/backend` 5 failed + 1 import error; `tests/tools` 15 failed + 1 import error; `tests/hermes_cli` 15 failed. Notably `test_execution_tools` (11 failures), `test_risk_limits`, `test_whale_tracker`, `test_tradingview_ingestion`, `test_multi_venue_market_data` (ImportError on `run_funding_spread_watcher_once`).
4. **Uncommitted work in the tree**: a new `whale_follower` strategy is added to `STRATEGY_REGISTRY` but has no commit, no integration tests visible, and the matching runner registration must be cross-checked.
5. **Trading mode default is `paper`** ✓ and live unlock requires `HERMES_TRADING_MODE=live`. Approval gate (`HERMES_REQUIRE_APPROVAL`) only fires when *also* in live mode — i.e. there is no first-class "approval-required" mode, only a paper/live binary plus an approval flag.
6. **Stale runtime state**: `gateway_state.json` shows `"gateway_state": "stopped"` from 2026-04-23 with a stale PID 27572; `processes.json` is `[]`.

**Final readiness verdict (Phase 11):** **Paper trading only.** Hermes is *not* ready for approval-required, limited live, or live trading until the migration DAG is repaired, the failing test buckets are green, and a verified balance reconciliation flow + manual order-verification probe are in place on BitMart.

---

## Phase 1 — Repository change verification

### Commits since prior baseline (last 10)
```
8a7540d Refactor trading strategy runners and risk management tools
3ab4363 feat: enhance 'doctor' command for comprehensive runtime health diagnostics
6ffb272 feat: enhance whale tracking and portfolio synchronization features
f3169df feat(gateway): add 'doctor' command for gateway diagnostics
788509e feat: add drawdown guard job for portfolio risk management
cd3727e feat: Implement paper shadow fills and liquidation hunt strategy
783bbe4 feat: Enhance trading functionality with Chronos scoring and risk management improvements
5ab5633 Add TradingView scripts for Chronos-2 forecasts and views
efa89b6 Add Firecrawl and Exa skills, funding rate monitor script, and environment sync script
8bfa7f0 feat: add systematic-debugging, test-driven-development, and writing-plans skills
```

### Working tree status
```
 M hermes-agent/backend/strategies/registry.py    # whale_follower added — UNCOMMITTED
 M profiles/strategy-agent/config.yaml            # context_length 32768 → 200000 — UNCOMMITTED
?? hermes_post_audit_verification_prompt.md       # prompt itself
```

### Change verification table

| Area | Files changed (sample) | Intended purpose | Verified? | Concern |
|---|---|---|---|---|
| Migrations | `alembic/versions/0003_chronos_forecasts.py`, `0004_paper_shadow_fills.py`, `0005_copy_trader_curator.py`, `0005_risk_limits.py` | New tables for forecasts, shadow fills, curator scores/proposals, risk limits | **PARTIAL — BROKEN DAG** | Two `0005_*` files; `0005_risk_limits.down_revision="0004_paper_shadow_fills"` but actual rev ID is `"0004"`. Will break `alembic upgrade head`. **CRITICAL FIX**. |
| Strategies | `strategies/{breakout,mean_reversion,momentum,funding,delta_neutral_carry,liquidation_hunt,whale_follower,chronos_scoring,performance_priors}.py`, `registry.py`, `runners.py` | 4 new strategies + Chronos scoring + perf priors | Mostly verified | `whale_follower` registry entry **uncommitted**; runner mapping for it needs spot-check. `test_strategy_funding_bonus`, `test_strategy_backtest`, `test_delta_neutral_carry`, `test_liquidation_hunt` cover most. |
| Risk / Trading core | `trading/{bot_runner.py (+277 lines),execution_service.py,policy_engine.py,sizing.py,lifecycle_notifications.py,models.py}` | Volatility-targeted sizing, lifecycle notifications, persistent risk limits | Partial | `test_risk_limits` failing on persistence; `test_execution_tools` 11 failures. |
| Execution mode | `integrations/execution/mode.py` (+291), `multi_venue.py`, `ccxt_client.py` | paper/live gate + paper-shadow scheduling | Mostly verified | Mode is binary `{paper,live}`; no first-class "approval-required" or "disabled" modes. |
| Public market data (multi-venue) | `integrations/derivatives/{binance_public_client,bybit_public_client,okx_public_client,bitmart_public_client,public_data,_utils}.py` | Cross-venue funding/OI/depth | Stub→Partial | `test_multi_venue_market_data` ImportError on `run_funding_spread_watcher_once` — module/symbol mismatch. |
| Whale tracking | `jobs/whale_tracker.py`, `tests/backend/test_whale_tracker.py` (217 lines), `integrations/onchain/{nansen_client,etherscan_client,bitmart_wallet_client}.py` | Smart-money + on-chain | Partial | `test_whale_tracker` failing. |
| Copy-trader curator | `jobs/copy_trader_curator.py` (804 lines), `backend/copy_trader_proposals.py`, migration `0005_copy_trader_curator.py`, test (195 lines) | Curator scoring & proposals | Mostly ready | Largest single addition; depends on broken migration. |
| Drawdown guard | `jobs/drawdown_guard.py` (177), `tests/backend/test_drawdown_guard.py` | Portfolio drawdown response | Ready (tests pass per group 1) | Wire-up to alerter / kill switch should be re-verified. |
| Portfolio sync | `jobs/portfolio_sync.py` (89), `scripts/portfolio_sync.py` | Spot/futures balance reconciliation | Partial | No verified live BitMart balance import yet — Phase 9 prompt required. |
| Strategy evaluator | `jobs/strategy_evaluator.py` (424), test (107) | Backtest-style scoring loop | Mostly ready | Tests pass per group 1 sample. |
| Backtesting | `backend/evaluation/{backtest.py (567), models.py}`, `test_strategy_backtest.py` | Offline simulation harness | Mostly ready | No CLI surface confirmed. |
| BitMart adapter | `integrations/derivatives/bitmart_public_client.py`, `integrations/onchain/bitmart_wallet_client.py`, `tests/backend/test_bitmart_public_client.py` (65) | Public + wallet probe | Partial | Order-side write-capability probe added in earlier commits; tests show 1 failure in bitmart_public_client. |
| TradingView | `tradingview/service.py`, `scripts/tradingview_*.js`, `test_tradingview_signal_pipeline.py` (214) | Pine inject / signal pipeline | Partial | `test_tradingview_ingestion.AttributeError: redis_id`. |
| Gateway / CLI | `hermes_cli/{gateway.py (+445), main.py (+179), ops_status.py (676 new), web_server.py (95 new), status.py}`, tests | `gateway doctor`, `ops_status` CLI, web server | Partial | Gateway/CLI tests show 15 failures (cleanup, config migration, doctor, env loader). |
| Notifications | `gateway/platforms/{telegram.py (+60),slack.py}`, `integrations/notifications/telegram_client.py` | Lifecycle alerts | Mostly ready | Slack diff is 1 line — superficial. |
| Profiles / personas | `profiles/execution-agent/**` (very large skill bundle import incl. `tirith` 10 MB binary) | Execution agent persona seeded | Partial | `profiles/execution-agent/bin/tirith` is a **10 MB binary committed to git** — should be `.gitignore`d / git-lfs / not committed. **Concern**. |
| Skills | Massive `profiles/execution-agent/skills/**` and `skills/**` additions (mlops, creative, web-design templates, etc.) | Skill library expansion | Off-topic | Most of this has no trading impact; bloat risk. |
| Docs | `FULL_REPORT.md` (643 lines), `docs/architecture/db-sync-plan.md` (201), `docs/workspace/GATEWAY_RUNTIME.md`, `plans/2026-04-24-bitmart-api-first-trading-path.md` (372), `hermes-agent/CHANGELOG.md` updates? | Architecture docs | **`FULL_REPORT.md` is invalid (tool-log)** | Replace/delete. |
| Env / config | `.env.dev.example` (+4), `hermes-agent/.env.example` (+7), `hermes/.env.example` (+13), `litellm_config.yaml` (+13), `hermes-agent/litellm_config.yaml` (+115), `docker-compose.dev.yml` (+5), `hermes/docker-compose.yml` (+4) | New provider/env keys | Partial | Confirm no real keys leaked (none observed in diffs sampled). |
| Web / dashboards | `web/src/lib/api.ts` (+35), `web/src/pages/AnalyticsPage.tsx` (+113) | Analytics page changes | Partial | UI tests for these not present. |

### Generated / committed-but-shouldn't-be artefacts

- `profiles/execution-agent/bin/tirith` — **10 MB binary** in git history.
- `profiles/execution-agent/cron/.tick.lock` — empty lock file checked in.
- `profiles/execution-agent/skills/.bundled_manifest` — generated.
- Root files like `port3000.html`, `port3100.html`, `response_3000.html`, `response_3100.html` (debug captures) — should be gitignored.
- `feishu_seen_message_ids.json`, `gateway_state.json`, `processes.json`, `auth.json`, `channel_directory.json` — runtime state in repo root.

### Secrets / credentials

No raw secrets observed in inspected diffs; `.env.example` files only. ✅
Recommend: `git secrets --scan` or `trufflehog` pass before any push.

---

## Phase 2 — Test and runtime verification

### Available targets
The root `Makefile` exposes only the `dev-*` targets (`dev-up`, `dev-down`, `dev-check`, `dev-logs`, `dev-ps`, `dev-bootstrap`, `dev-clean-legacy`).
There is **no `make test`, `make lint`, `make typecheck` at the root**, and `hermes-agent/Makefile` does not exist (consumed via direct `pytest` / `cli.py`).

### Runtime / health state
- `processes.json` = `[]` → no managed processes.
- `gateway_state.json`: `gateway_state="stopped"`, `pid=27572` (stale, `start_time=null`), `updated_at=2026-04-23` (2 days old).
- `active_profile` = `orchestrator`.
- No docker dev stack was started during this verification (per safety constraint — `make dev-up` would build/spawn containers; not run).

### Check matrix

| Check | Command / source | Result | Blocking? |
|---|---|---|---|
| `make dev-check` (HTTP probes) | Root Makefile | **Not run** (would require `dev-up` first; no live infra running) | No (manual) |
| Unit tests — backend | `pytest tests/backend -k "not live and not network and not e2e"` | **106 pass / 5 fail / 1 import-error** | Yes — must fix |
| Unit tests — tools | `pytest tests/tools` | **1446 pass / 15 fail / 1 import-error** | Yes — `test_execution_tools` 11 failures are blocking |
| Unit tests — hermes_cli | `pytest tests/hermes_cli` | **1162 pass / 15 fail** | Yes — gateway doctor + cleanup tests failing |
| Lint / typecheck | n/a — no Make target | **Not run** | Add target |
| Alembic DAG validity | `alembic heads` (would show 2 heads) | **Broken** (`0005` and `0005_risk_limits` both branch off `0004`; the latter references nonexistent `"0004_paper_shadow_fills"`) | **CRITICAL** |
| Gateway state | `gateway_state.json` | Stale (2026-04-23, stopped) | Cleanup needed |
| Telegram gateway | code path present (`gateway/platforms/telegram.py +60`) | Not exercised live | Confirm with `hermes gateway doctor` |
| Slack gateway | `gateway/platforms/slack.py +1` | Stub | Low priority |
| LiteLLM config | `hermes-agent/litellm_config.yaml +115` | Static config diff | Verify with `dev-check` after `dev-up` |
| Cron wrappers | `cron/jobs.json`, `scripts/*` | Code present | Run dry-mode loader |
| Trading mode default | `mode.py:26` | `"paper"` ✅ | Safe default |
| Approval workflow | `safety.py:46-68` env `HERMES_REQUIRE_APPROVAL` | Activates only when `mode=="live"` | Should also be respected in `paper` for human-in-the-loop UX |

### Top failing tests (representative)

| Failure | Likely root cause | Suggested fix |
|---|---|---|
| `tests/backend/test_multi_venue_market_data.py` ImportError on `run_funding_spread_watcher_once` | Symbol moved/renamed in `backend.event_bus.workers` (file shows +554 lines; large refactor) | Re-export `run_funding_spread_watcher_once` from `event_bus.workers`, or update test import path |
| `tests/backend/test_risk_limits.py` "persistence failure for symbol caps" | Migration `0005_risk_limits` not applied (broken DAG) — table absent at test setup | Fix migration revision IDs (see Phase 5) and re-run |
| `tests/backend/test_whale_tracker.py` failures | Likely depends on Nansen/Etherscan client mocks; check fixture wiring | Inspect the new `nansen_client` (33 +) and `etherscan_client` (11 +) signatures |
| `tests/backend/test_tradingview_ingestion.py AttributeError: redis_id` | Worker rename — `redis_id` was renamed/removed in workers.py refactor | Update consumer/test attribute |
| `tests/tools/test_execution_tools.py` (11 failures, order placement / venue selection) | `place_order.py +40` and `preview_execution_order.py` (new, 63 lines) changed contracts | Pin the `OrderRequest`/`OrderResult` schema; verify `multi_venue.py` venue selection |
| `tests/tools/test_mcp_tool.py` ImportError | `mcp` package missing in venv | `pip install mcp` or guard import |
| `tests/hermes_cli/test_gateway_doctor.py` failures | New `doctor` command (commits `f3169df`/`3ab4363`) not aligned with test fixtures | Rebase tests against current `hermes_cli/gateway.py` |
| `tests/hermes_cli/test_*` cleanup/config-migration/env-loader/auth | Likely cascading from `main.py +179` refactor | Audit `hermes_cli/main.py` command surface |

---

## Phase 3 — Trading feature verification

| # | Feature | Current state | Readiness | Profit use case | Missing piece | Priority |
|---|---|---|---|---|---|---|
| 1 | Strategy engine (`strategies/runners.py`, `registry.py`) | 5 new strategies registered + chronos scoring + perf priors | Mostly ready | Multi-edge selector | `whale_follower` uncommitted; runner→registry mapping audit | High |
| 2 | Signal scoring (`chronos_scoring.py`, `performance_priors.py`) | Both implemented + tests | Mostly ready | Bayesian-flavoured scoring | Score-to-size translation | High |
| 3 | Market data ingestion (multi-venue derivatives) | New clients for Binance/Bybit/OKX, public_data aggregator | Partial | Funding/OI cross-venue | Import errors fail tests | High |
| 4 | Technical indicators | Strategies compute SMA/EMA/Bollinger/RSI inline | Partial | Lacks shared indicator library | Refactor into `backend/indicators/` | Medium |
| 5 | News / event-risk (`tools/get_event_risk_summary.py +80`) | Refactored | Partial | LunarCrush, news skim | No structured event-blackout calendar | Medium |
| 6 | Whale / liquidation tracking | `jobs/whale_tracker.py`, `liquidation_hunt.py` | Partial | Smart-money follow + liquidation pulse | Tests failing | High |
| 7 | Copy-trading | `jobs/copy_trader_curator.py` (804), `copy_trader_proposals.py` | Partial | Curator scoring | Live BitMart copy-trade follow-trace not yet end-to-end | High |
| 8 | Exchange-bot support | Partial scoring scaffolding only | Stub | Grid/DCA recommender | Parameter recommender not implemented | Medium |
| 9 | BitMart adapter | Public client + wallet probe + execution gating commits (`b123e3c`, `2461b6b`, `8a7540d`) | Partial | Read OK, write probe present | TP/SL bracket round-trip not asserted in tests | **High** |
| 10 | TP/SL bracket handling | Models in `trading/models.py +89`, sizing logic | Partial | Bracketed exits | No explicit `place_bracket_order` integration test | **High** |
| 11 | Approval workflow (`safety.py`) | Env-flag based | Partial | Human-in-loop | Only honours when mode=live; not surfaced in UI | High |
| 12 | Paper / shadow fills (`mode.py:140-241`, `0004` migration) | Implemented + test_paper_shadow.py | Mostly ready | Live↔paper P&L divergence | Acts only in `live` mode (shadows live trades) — by design but worth documenting | Medium |
| 13 | Volatility-targeted sizing (`trading/sizing.py +43`) | Implemented + tests | Mostly ready | Risk-adjusted size | No regime-conditional vol target | Medium |
| 14 | DB-backed risk limits (`0005_risk_limits`) | Migration broken; persistence test failing | Broken | Ops-tunable caps | Fix migration first | **High** |
| 15 | Portfolio / balance reconciliation (`jobs/portfolio_sync.py`, `scripts/portfolio_sync.py`) | Partial | Partial | Spot+futures snapshot | No verified live BitMart balance importer | High |
| 16 | Drawdown guard (`jobs/drawdown_guard.py`) | Implemented + tests pass | Ready | Equity-curve cutoff | Confirm wired to kill switch | Medium |
| 17 | Alerting / notifications | Telegram + lifecycle hooks | Mostly ready | Trade alerts | Slack stub | Medium |
| 18 | Dashboards / reports (`web/AnalyticsPage.tsx +113`, `ops_status.py 676`) | Partial | Partial | Decision support | UI tests absent | Medium |
| 19 | Memory / state persistence | Repos in `db/repositories.py +124` | Mostly ready | Audit trail | Verify migration|schema sync | Medium |
| 20 | Agent routing / coordination (`teams/`, `profiles/`) | Mature persona system | Ready | Multi-agent | None blocking | Low |

---

## Phase 4 — Profitability reality check

| Capability | Current answer | Evidence | Needed improvement |
|---|---|---|---|
| Detect opportunities faster than manual | **Partially** | Funding-rate monitor, multi-venue clients, whale tracker, TradingView ingestion. But tests for these fail. | Stabilise ingestion pipeline; ensure latencies <30 s end-to-end |
| Avoid obviously bad trades | **Partially** | Risk approval (`get_risk_approval`), kill switch, blockers in `policy_engine`, blockers when mode=live without unlock | Wire event-risk blackouts (CPI/FOMC) into policy |
| Manage exits better than manual | **No, not yet** | TP/SL models exist in `trading/models.py` but no proven bracket round-trip on BitMart | Add live BitMart bracket smoke test + paper TP/SL exits |
| Allocate capital intelligently | **Partial** | `sizing.py` volatility-target, perf priors | No portfolio-level rebalancer across BTC/ETH/SOL/XRP |
| Compare bot/copy-trade opportunities | **Stub** | `copy_trader_curator.py` exists; bot ranker absent | Build grid-bot parameter recommender and unified ranking score |
| React to market regime changes | **Stub** | No regime-detector module observed (`grep regime` ≈ 0 hits in strategies) | Add HMM/volatility regime classifier; condition strategy enable list on regime |
| Learn from previous trades | **Partial** | `performance_priors.py` (130) + evaluator job + backtest harness | Close the loop: evaluator → priors → registry weights nightly |
| Explain entry/exit/block decisions | **Partial** | `policy_engine.trace[]`, blockers list | Persist policy traces per proposal; surface in dashboard |

**Bottom line:** The skeleton is in place across all 8 dimensions, but only #1 and #2 are usefully better than manual today, and only when the failing tests are repaired.

---

## Phase 5 — Immediate fixes before adding more features

| Fix | Why it matters | Files / modules | Suggested implementation | Priority |
|---|---|---|---|---|
| Repair alembic DAG (`0005` collision) | `alembic upgrade head` fails → risk-limits + curator tables never created → tests + runtime broken | `alembic/versions/0005_copy_trader_curator.py`, `0005_risk_limits.py` | Rename to `0005_risk_limits` → revision `"0005"`, down `"0004"`; rename other to `0006_copy_trader_curator` revision `"0006"`, down `"0005"`. Or unify on string IDs. Run `alembic heads` → must show single head. | **CRITICAL** |
| Fix `run_funding_spread_watcher_once` import | Import-error stops test_multi_venue_market_data | `backend/event_bus/workers.py`, `tests/backend/test_multi_venue_market_data.py` | Re-export the symbol or update test path | **High** |
| Fix `test_execution_tools` 11 failures | Tools-layer regression on order placement | `backend/tools/place_order.py`, `preview_execution_order.py`, `trading/execution_service.py` | Lock `OrderRequest`/`OrderResult` contracts; make venue selection deterministic in tests | **High** |
| Fix `test_risk_limits` persistence | Persisted caps are the live safety net | `backend/db/repositories.py`, migration above | Re-run after migration fix; assert UPSERT semantics | **High** |
| Fix `test_whale_tracker` | Whale signal feeds `whale_follower` strategy | `jobs/whale_tracker.py`, `integrations/onchain/nansen_client.py` | Mock Nansen + Etherscan responses cleanly | High |
| Fix `test_tradingview_ingestion` (`redis_id`) | TV is the primary chart-trigger pipeline | `event_bus/workers.py` | Restore or rename `redis_id` consistently | High |
| Commit or revert `whale_follower` registry entry | Drift between repo HEAD and runtime | `backend/strategies/registry.py` | Either commit + register runner or `git checkout` | Medium |
| Replace bogus `FULL_REPORT.md` | Reviewers will be misled | `FULL_REPORT.md` | Replace with this verification report or delete | Medium |
| Clean stale `gateway_state.json` / `processes.json` | Stale PID 27572 confuses doctor | repo-root state files | Add `hermes gateway doctor --reset` path; gitignore | Medium |
| Remove 10 MB `tirith` binary from git | Repo bloat | `profiles/execution-agent/bin/tirith` | git-lfs or fetch-on-install + `.gitignore` | Medium |
| Add `make test` / `make lint` / `make typecheck` targets | No standard quality gate | root `Makefile` | Wrap `pytest`, `ruff`, `mypy --strict` | Medium |
| Make trading mode tri-state (`disabled` / `paper` / `live`) | Avoid accidental re-enable | `mode.py` | Accept `disabled` (no order routing at all even paper); default remains `paper` | Medium |
| Always honour `HERMES_REQUIRE_APPROVAL` (incl. paper) | Train approval UX in paper | `trading/safety.py:63` | Drop `mode == "live"` precondition for approval gate (or add `HERMES_REQUIRE_APPROVAL_PAPER`) | Medium |
| BitMart TP/SL bracket round-trip test | TP/SL is core P&L protection | `integrations/derivatives/bitmart_*`, `tests/backend/test_bitmart_*` | Add a sandboxed mock test asserting both legs are filed and cancellable | High |
| Centralise indicators | Drift across strategies | `backend/indicators/` (new) | Pull SMA/EMA/RSI/BB out of strategy files | Low |
| Gitignore runtime state files | Drift / secrets risk | `.gitignore` | Add `gateway_state.json`, `processes.json`, `feishu_seen_message_ids.json`, `port*.html`, `response_*.html` | Medium |

---

## Phase 6 — Highest-impact profit improvements

| Improvement | Impact | Complexity | Risk | Files / modules | Notes |
|---|---|---|---|---|---|
| Market regime detector (vol-of-vol + trend slope + breadth) | Very high | Medium | Low | `backend/regime/` (new), consumed by `strategies/runners.py` | Gate momentum/breakout to trend regimes; mean-reversion to range; disable trades in extreme vol |
| Trend/momentum confirmation gate (multi-timeframe) | High | Low | Low | `strategies/momentum.py`, `breakout.py` | Require 1h trend agree with 15m signal |
| Vol-aware entry sizing improvement | High | Low | Low | `trading/sizing.py` | Cap notional by ATR; floor on min vol |
| Volume / liquidity filter | High | Low | Low | strategies | Reject if 24h volume < $X or top-of-book depth < $Y |
| Exit management (trailing + time-stop + adverse-excursion) | Very high | Medium | Medium | `trading/execution_service.py`, `models.py` | Today TP/SL is static |
| Capital rotation BTC/ETH/SOL/XRP (rank-by-edge) | High | Medium | Medium | new `jobs/capital_rotation.py` | Daily rerank by realised edge from `performance_priors` |
| Copy-trader ranking improvements (volatility-adjusted Sharpe + drawdown) | High | Low | Low | `jobs/copy_trader_curator.py` | Already 804 lines — add Sortino + UPI |
| Exchange bot ranking | High | Medium | Medium | new module | Score grid bots on grid-density vs realised range |
| Drawdown response (de-leverage ladder) | High | Low | Low | `jobs/drawdown_guard.py` | Step-down sizing at -3 / -5 / -8 % |
| Signal deduplication (TTL + idempotency) | Medium | Low | Low | `event_bus/workers.py` | Hash {strategy,symbol,bucket} → drop dupes |
| Post-trade learning loop | Very high | Medium | Low | `jobs/strategy_evaluator.py` → `performance_priors.py` | Already in place; close the loop nightly |
| Risk-adjusted score (Kelly-fraction cap) | High | Low | Low | `sizing.py` | Cap to fraction of Kelly given priors |
| Use AI agents only at decision points | Medium | Low | Low | `profiles/`, `toolset_distributions.py` | Avoid LLM in hot path |
| Decision dashboard (live policy traces) | High | Medium | Low | `web/`, `ops_status.py` | Show why a trade was approved/blocked |
| Approval UX (Telegram inline keyboard) | High | Medium | Low | `gateway/platforms/telegram.py` | One-tap approve/decline with TTL |

---

## Phase 7 — Strategy recommendations

| Strategy | Use when | Avoid when | Required data | Entry | Exit | Risk rule | Priority |
|---|---|---|---|---|---|---|---|
| BTC/ETH momentum breakout w/ vol filter | Trend regime, ATR_norm > 0.6 | Range or low-vol regime | 1h/4h OHLCV, ATR, 24h vol | Close > N-bar high & ATR_norm in [0.6, 1.4] & vol > $X | TP=2*ATR, SL=1*ATR, time-stop 6h | Risk per trade ≤ 0.5% equity | **High** |
| SOL/XRP intraday trend continuation | Aligned 1h+15m EMA, funding ≤ 0.02% | Funding extreme or news blackout | 15m OHLCV, EMA20/50, funding | EMA20>EMA50 on both TF, pullback to EMA20 | TP=1.5R trail, SL=below pullback low | Cap notional 1× ATR move | High |
| Mean-reversion (range only) | Range regime, BB-width compressed | Trend regime | 5m/15m, BB, RSI | Close outside 2σ + RSI extreme | Mid-band or 1.5R, time-stop 90m | ≤ 0.3% per trade | High |
| Event-risk blackout | CPI/FOMC/OPEX windows | Always honour | Econ calendar, options expiry | n/a — *blocks* opens | Flatten before window | Hard block at policy_engine | **High** |
| Copy-trader curator | All times | Trader < N trades or < 30 days | Curator scores | Mirror trades from top-N traders, vol-scaled | Mirror exits or trader-disable cutoff | Per-trader cap, total cap | High |
| Grid-bot recommender | Range regime on alt | Trend regime | Realised range, ATR | Recommend grid = 1.2× ATR / N levels | n/a | Capital-share cap | Medium |
| Portfolio rotation | Daily | Liquidity drought | `performance_priors`, edge by symbol | Top-K weighted by realised edge | Rebalance daily | Max single-symbol 40% | High |
| Defensive capital-preservation | Equity DD ≥ -5% | Always allow re-enable | Equity curve | Cut leverage 50%, halve sizing | Re-arm at HWM-2% | Hard floor | **High** |
| Post-loss cooldown / anti-revenge | After 2 consecutive losses | Always | Trade history | n/a (block opens) | 30–60 min cooldown | Per-symbol throttle | High |
| HV scalp filter | ATR_norm > 1.4 | Otherwise | 1m/5m | Two-bar momentum + spread guard | TP=0.5R, SL=0.5R, fast time-stop | Tight notional, max 3/hour | Low (only if infra latency proven) |

---

## Phase 8 — Data / API / model recommendations

| Service / model | Use case | Cost | Reliability | Integration | Recommendation |
|---|---|---|---|---|---|
| Binance public REST + WS | Spot/perp price, OI, funding | Free | High | Already in `binance_public_client.py` | **Adopt as primary** |
| Bybit public REST | Cross-venue funding/OI | Free | High | Already added | Adopt |
| OKX public REST | Cross-venue | Free | High | Already added | Adopt |
| BitMart REST/WS | Execution | Free | Medium | Adapter present, partial | Keep, but never single-source for prices |
| CoinGecko (`coingecko_client.py +66`) | Discovery, sanity | Free tier strict | Medium | Present | Use as cache, not hot path |
| TwelveData (`twelvedata_client.py +36`) | TA endpoints | Cheap | Medium | Present | Optional, not critical |
| LunarCrush (`lunarcrush_client.py +27`) | Sentiment / Galaxy Score | Paid | Medium | Present | Useful as feature, not gate |
| Nansen / Etherscan | Whale/on-chain | Nansen $$$, Etherscan free | High | Present | Keep Nansen optional behind env flag |
| TradingView webhooks | Chart-driven entries | Pro plan needed | High | Present (`scripts/tradingview_*.js`) | Adopt for primary chart triggers |
| Econ calendar (FRED + Trading Economics free RSS) | Event blackout | Free / cheap | Medium | Not present | **Add** |
| Cryptopanic / NewsAPI | News risk | Free tier | Medium | Not present | Add behind cache |
| Chronos forecasting (`chronos-forecasting/`, `chronos_scoring.py`) | Time-series prior | Local / cheap | Medium | Present | Keep, but treat as one signal |
| Local LLM via litellm | Reasoning, not signal | Cheap | Medium | Present | Keep out of hot path |
| Embeddings / vector memory | Trade journal recall | Cheap | High | Not yet | Defer until learning loop closed |
| Coinglass (free or paid) | Liquidations, OI heatmaps | Cheap | High | Not present | Add to liquidation_hunt |
| Funding-rate aggregator (Coinalyze / Coinglass) | Cross-venue funding edge | Cheap | High | Partially via venue clients | Add aggregator |

---

## Phase 9 — Balance and capital-state prompt (verbatim, hand to operator)

```text
Hermes does not yet have verified live BitMart balance reconciliation. Please provide your current trading state in the JSON schema below. All amounts in USD unless noted. All values must be your own; Hermes will treat this as authoritative until live reconciliation is implemented.

REQUIRED JSON (paste into the operator channel or save to `state/operator_snapshot.json`):

{
  "as_of_utc": "2026-04-25T00:00:00Z",
  "exchange": "bitmart",
  "spot_balances": [
    { "asset": "USDT", "free": 0.0, "locked": 0.0 },
    { "asset": "BTC",  "free": 0.0, "locked": 0.0 }
  ],
  "futures_balances": [
    { "asset": "USDT", "wallet": 0.0, "available": 0.0, "margin_used": 0.0, "unrealized_pnl": 0.0 }
  ],
  "active_grid_bots": [
    {
      "bot_id": "string",
      "symbol": "BTCUSDT",
      "side": "long|short|neutral",
      "lower_price": 0.0,
      "upper_price": 0.0,
      "grid_levels": 0,
      "invested_usdt": 0.0,
      "realized_pnl": 0.0,
      "unrealized_pnl": 0.0,
      "running_since_utc": "2026-04-01T00:00:00Z"
    }
  ],
  "active_copy_trades": [
    {
      "trader_id": "string",
      "label": "string",
      "allocated_usdt": 0.0,
      "realized_pnl": 0.0,
      "unrealized_pnl": 0.0,
      "started_utc": "2026-04-01T00:00:00Z",
      "trader_params": { "max_followers": 0, "fee_share": 0.0 }
    }
  ],
  "open_positions": [
    {
      "symbol": "BTCUSDT",
      "side": "long|short",
      "entry_price": 0.0,
      "qty": 0.0,
      "leverage": 0,
      "tp": 0.0,
      "sl": 0.0,
      "unrealized_pnl_usdt": 0.0,
      "venue": "bitmart"
    }
  ],
  "pnl": {
    "realized_24h_usdt": 0.0,
    "realized_7d_usdt": 0.0,
    "realized_30d_usdt": 0.0,
    "unrealized_total_usdt": 0.0
  },
  "capital": {
    "available_usdt": 0.0,
    "invested_usdt": 0.0,
    "reserved_usdt": 0.0
  },
  "loss_limits": {
    "daily_max_loss_usdt": 0.0,
    "weekly_max_loss_usdt": 0.0,
    "max_drawdown_pct_from_hwm": 0.0
  },
  "manual_trades_unknown_to_hermes": [
    { "symbol": "BTCUSDT", "side": "long", "qty": 0.0, "entry_price": 0.0, "opened_utc": "2026-04-25T00:00:00Z" }
  ],
  "notes": "free text"
}

Please send this JSON. Hermes will then:
1. Persist a snapshot in `paper_shadow_account` and a new `operator_snapshot` table.
2. Reconcile with anything BitMart's read API does return.
3. Raise an alert on every divergence > 1%.
```

---

## Phase 10 — Final prioritized roadmap

### Must do before live automation

1. **Repair alembic DAG**
   - Why: `alembic upgrade head` fails / multi-head; risk_limits and curator tables never created.
   - Files: `hermes-agent/alembic/versions/0005_copy_trader_curator.py`, `0005_risk_limits.py`.
   - Acceptance: `alembic heads` returns one head; `alembic upgrade head` succeeds on a fresh DB; `test_risk_limits` passes.
   - Verify: `cd hermes-agent && alembic heads && alembic upgrade head && pytest tests/backend/test_risk_limits.py -q`.

2. **Green test buckets**
   - Why: 35+ failing tests block any live promotion.
   - Files: see Phase 5.
   - Acceptance: `pytest tests/backend tests/tools tests/hermes_cli -q` exits 0.
   - Verify: same command.

3. **BitMart TP/SL bracket round-trip test (mocked + sandboxed live)**
   - Why: TP/SL is the core P&L protection; not asserted today.
   - Files: `backend/integrations/derivatives/bitmart_*`, `backend/trading/execution_service.py`, `tests/backend/test_bitmart_*`.
   - Acceptance: Place → confirm both TP and SL legs exist on exchange → cancel both → verify state transitions.
   - Verify: dedicated marker `pytest -m bitmart_bracket`.

4. **Tri-state trading mode + always-on approval**
   - Why: Avoid accidental live; train approvals in paper.
   - Files: `mode.py`, `safety.py`, `policy_engine.py`.
   - Acceptance: `HERMES_TRADING_MODE in {disabled,paper,live}`; `HERMES_REQUIRE_APPROVAL` honoured in paper too.
   - Verify: new unit test in `tests/backend/test_trading_control_path.py`.

5. **Operator balance import path (Phase 9 prompt → table)**
   - Why: Today portfolio reconciliation is partial.
   - Files: new `backend/operator_snapshot.py`, migration `0007_operator_snapshot.py`, CLI command.
   - Acceptance: JSON imported, persisted, surfaced in dashboards.

### Profitability improvements

1. Regime detector + strategy gating — `backend/regime/`, `strategies/runners.py`.
2. Exit management upgrade (trailing + time-stop) — `trading/execution_service.py`, `trading/models.py`.
3. Capital rotation job — `jobs/capital_rotation.py`.
4. Vol-adjusted curator ranking — `jobs/copy_trader_curator.py`.
5. Closing the post-trade learning loop nightly — `jobs/strategy_evaluator.py` → `strategies/performance_priors.py`.

### Operational improvements

1. `make test`, `make lint`, `make typecheck` at root.
2. Gitignore runtime state + remove `tirith` binary from history.
3. `hermes gateway doctor --reset` to clear stale state.
4. Centralise indicators in `backend/indicators/`.
5. Standardise event bus worker contracts (fix `redis_id`, `run_funding_spread_watcher_once`).

### Dashboard / reporting improvements

1. Decision dashboard with live policy traces (`web/AnalyticsPage.tsx` + backend trace endpoint).
2. Telegram approval inline keyboard with TTL.
3. Operator snapshot view + divergence alerts.
4. Per-strategy edge & priors page.

### Later / optional

1. HMM regime classifier.
2. Vector memory of trade journal.
3. Grid-bot recommender service.
4. Coinglass / Coinalyze integration.

---

## Phase 11 — Next Codex prompts

For each prompt below: hand to Codex/agent, do not run live trades, do not commit secrets, default mode stays `paper`, approval flag must keep gating live execution.

### Prompt 1 — Full post-change verification + safety review
- **Goal**: Produce machine-readable verification artefact for the changes since `8a7540d`.
- **Context**: This file (`POST_AUDIT_VERIFICATION.md`) is the human-readable baseline.
- **Files to inspect**: `git diff HEAD~10..HEAD`, all changed files in Phase 1.
- **Instructions**: Generate a `verification.json` listing every changed file with `{path, change_type, lines_added, lines_removed, has_tests, test_status}`; include a `secrets_scan` section using `trufflehog filesystem --json`.
- **Safety**: read-only, no network calls.
- **Acceptance**: `verification.json` validates against schema; secrets_scan returns 0 findings.
- **Commands**: `git diff --stat HEAD~10..HEAD`, `pytest -q --collect-only`, `trufflehog filesystem .`.
- **Expected output**: `verification.json` + a markdown summary.

### Prompt 2 — Runtime / gateway / profile cleanup
- **Goal**: Eliminate stale runtime state and gitignore runtime artefacts.
- **Files**: `gateway_state.json`, `processes.json`, `feishu_seen_message_ids.json`, `port*.html`, `response_*.html`, `.gitignore`, `hermes_cli/gateway.py`.
- **Instructions**: Add `--reset` to `hermes gateway doctor`; gitignore the listed files; remove `profiles/execution-agent/bin/tirith` from tracking (use `git rm --cached`); add `.gitattributes` for git-lfs if needed.
- **Safety**: do not delete history; only untrack.
- **Acceptance**: `git status` shows clean tree after reset; `hermes gateway doctor` reports `clean`.
- **Commands**: `hermes gateway doctor --reset`, `git status`, `pytest tests/hermes_cli/test_gateway_doctor.py`.

### Prompt 3 — Trading state reconciliation + balance importer
- **Goal**: Implement the operator-snapshot import path from Phase 9.
- **Files**: new `backend/operator_snapshot.py`, migration `0007_operator_snapshot.py`, CLI cmd `hermes ops import-snapshot`, dashboard tile.
- **Instructions**: Validate JSON against the Phase 9 schema; persist; reconcile with whatever BitMart read endpoints already work; raise alerts on divergence >1%.
- **Safety**: no order placement.
- **Acceptance**: end-to-end test: import sample JSON, query reconciliation, see divergence alert.
- **Commands**: `pytest tests/backend/test_operator_snapshot.py`.

### Prompt 4 — BitMart TP/SL + bracket-order verification
- **Goal**: Prove TP/SL bracket round-trip on BitMart sandbox/paper.
- **Files**: `backend/integrations/derivatives/bitmart_*`, `backend/trading/execution_service.py`, `tests/backend/test_bitmart_bracket.py` (new).
- **Instructions**: Mock BitMart REST/WS; assert order → TP leg → SL leg → cancel; mark live test with `@pytest.mark.bitmart_sandbox` requiring env `HERMES_BITMART_SANDBOX=1`.
- **Safety**: never call mainnet.
- **Acceptance**: mocked test passes; sandbox test passes when explicitly enabled.

### Prompt 5 — Strategy scoring + market-regime upgrade
- **Goal**: Add `backend/regime/detector.py` and gate strategies by regime.
- **Files**: new `backend/regime/`, edits in `strategies/runners.py`, `strategies/registry.py`, tests.
- **Instructions**: Implement realised-vol-adjusted regime classifier (range / trend / high-vol / event-risk). Map each strategy to allowed regimes. Integrate with `policy_engine`.
- **Safety**: no live changes.
- **Acceptance**: `pytest tests/backend/test_regime_detector.py` and `test_strategy_gating.py` green.

### Prompt 6 — Copy-trader + exchange-bot ranking engine
- **Goal**: Vol-adjusted ranking + grid-bot parameter recommender.
- **Files**: `jobs/copy_trader_curator.py`, new `jobs/exchange_bot_recommender.py`, web tile.
- **Instructions**: Add Sortino, Ulcer Index, max DD, recovery factor; for grid bots, recommend levels = 1.2 × ATR / N where N optimised by walk-forward.
- **Acceptance**: ranking endpoint returns deterministic top-N; recommender outputs JSON.

### Prompt 7 — Dashboard improvements for decisions and approvals
- **Goal**: Surface policy traces + approval UX.
- **Files**: `web/src/pages/AnalyticsPage.tsx`, new `DecisionsPage.tsx`, backend trace endpoint, `gateway/platforms/telegram.py`.
- **Instructions**: Persist `PolicyDecision.trace[]` per proposal; show in UI; Telegram inline keyboard with `approve|decline|details` buttons + 10-min TTL.
- **Acceptance**: e2e click-through approves a paper trade.

### Prompt 8 — Backtesting / paper-shadow analytics
- **Goal**: First-class CLI + dashboard for `evaluation/backtest.py` and paper-shadow divergence.
- **Files**: `backend/evaluation/backtest.py`, new `cli` subcommand `hermes eval run`, web page.
- **Instructions**: Drive backtest from `STRATEGY_REGISTRY`; output equity curve, Sharpe, max DD, hit rate; compare to live shadow fills.
- **Acceptance**: `hermes eval run --strategy momentum --symbol BTCUSDT --since 30d` prints metrics.

### Prompt 9 — Post-trade learning loop
- **Goal**: Close evaluator → priors → registry confidence weights nightly.
- **Files**: `jobs/strategy_evaluator.py`, `strategies/performance_priors.py`, cron entry, `strategies/registry.py`.
- **Instructions**: Update `min_confidence` per strategy from rolling realised edge; write to DB-backed override table.
- **Acceptance**: scheduled cron updates priors; visible in dashboard.

### Prompt 10 — Final commit-readiness review
- **Goal**: Pre-merge gate.
- **Files**: all of the above.
- **Instructions**: Run full test suite, `ruff`, `mypy`, secret scan; verify `alembic heads` is single; verify `make dev-up && make dev-check` returns 200 on every endpoint; produce `RELEASE_READINESS.md`.
- **Acceptance**: zero failing tests, zero secret findings, single migration head, all health endpoints green.

### Recommended order of execution
1 → 2 → 4 → 3 → 5 → 9 → 6 → 7 → 8 → 10.

---

## Final decision

Hermes is currently ready for **paper trading only**.

To progress to **approval-required trading** (paper with human approvals): complete Phase 5 must-fix items 1–4 + Prompts 1, 2, 5, 7 above.

To progress to **limited live trading** (capped capital, single venue, single strategy): additionally complete Prompts 3 and 4 with sandbox-verified BitMart bracket round-trips, and operator-snapshot reconciliation must run for ≥7 days with <1% divergence.

Full live automation is **not appropriate** until the post-trade learning loop (Prompt 9) and the regime detector (Prompt 5) have been validated for ≥30 days in paper.
