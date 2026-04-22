# Hermes Post-Fix Verification Audit

_Verification date: 2026-04-16_

This document is a **strict post-remediation verification pass** against the earlier implementation audit. It does **not** assume a fix is valid because code or docs exist. The goal here is to verify, with evidence, what is now truly working, what is only partially improved, what remains unresolved, and what has regressed.

This verification is against the **current workspace state on disk**, not just committed history. At the time of review:

- `hermes/` had no local git changes.
- `hermes-agent/` contained a large unstaged working-tree diff across workers, integrations, workflows, tools, docs, and tests.

That means several “fixed” areas are verified as **present in the local working tree**, but not yet proven merged or released.

## Verification basis

This pass used direct code/config inspection plus targeted execution evidence.

### Code and config reviewed

- `hermes/apps/api/src/hermes_api/api/routes/*.py`
- `hermes/apps/api/src/hermes_api/integrations/hermes_agent.py`
- `hermes/apps/web/app/**/*`
- `hermes/apps/web/components/*`
- `hermes/apps/web/lib/hermes-api.ts`
- `hermes-agent/backend/db/*`
- `hermes-agent/backend/observability/*`
- `hermes-agent/backend/event_bus/workers.py`
- `hermes-agent/backend/workflows/*`
- `hermes-agent/backend/tools/*`
- `hermes-agent/backend/services/portfolio_sync.py`
- `hermes-agent/backend/approvals.py`
- `hermes-agent/backend/integrations/**/*`
- `profiles/*/{config.yaml,IDENTITY.md}`
- `litellm_config.yaml`, `hermes-agent/litellm_config.yaml`, root `config.yaml`
- `hermes/docker-compose.yml`, `hermes-agent/docker-compose.yml`, `hermes-agent/docker-compose.litellm.yml`
- `hermes/docs/runtime-consolidation-plan.md`, `hermes/docs/local-runtime-flow.md`

### Working tree scope reviewed

- `hermes/`: clean working tree during verification
- `hermes-agent/`: extensive unstaged modifications, including:
	- `backend/event_bus/workers.py`
	- `backend/integrations/**/*`
	- `backend/observability/*`
	- `backend/services/portfolio_sync.py`
	- `backend/strategies/*`
	- `backend/tools/*`
	- `backend/tradingview/*`
	- `backend/workflows/*`
	- `tests/backend/*`
	- `tests/tools/*`

### Execution evidence captured

1. **Hermes product API tests**
	 - Command path used from local terminal: `source .venv/bin/activate && cd hermes && python -m pytest apps/api/tests --tb=short -q`
	 - Result: **failed during collection** with `ModuleNotFoundError: No module named 'fastapi'`.
	 - Important nuance: `hermes/pyproject.toml` does declare `fastapi`, so this is a **local environment/bootstrap issue**, not proof that the repo omitted the dependency.

2. **Hermes Agent backend/tool verification**
	 - Command path used from repo root: `cd hermes-agent && source ../.venv/bin/activate && python -m pytest tests/backend/ tests/tools/ --tb=short -q`
	 - Result: **3026 passed, 1 failed, 38 skipped**.
	 - Single product-relevant failure: `tests/backend/test_shared_time_series_storage.py::test_get_portfolio_state_reads_latest_shared_snapshot`
	 - Failure cause: `get_portfolio_state()` now adds a missing-exchange-credentials warning even when a valid persisted snapshot exists.

3. **Alternate Hermes Agent run from workspace root using absolute test paths**
	 - Result: **12 failed, 3015 passed, 38 skipped**.
	 - 11 of those failures were `FileNotFoundError` in `tests/tools/test_voice_cli_integration.py` due tests opening `cli.py`, `run_agent.py`, and `tools/*.py` with cwd-sensitive relative paths.
	 - This indicates **test harness fragility / cwd sensitivity**, not necessarily a product-runtime regression.
	 - The failing tests read source files using relative paths such as `open("cli.py")`, `open("run_agent.py")`, and `open("tools/tts_tool.py")`, so the same suite behaves differently depending on whether pytest is launched from `hermes-agent/` or from another directory.

4. **Hermes web build**
	 - Command: `cd hermes/apps/web && npm run build`
	 - Result: **failed**.
	 - Exact blocker: `Duplicate export 'default'` in `hermes/apps/web/app/mission-control/page.tsx`.

5. **Frontend source inspection after the failed web build**
	 - `hermes/apps/web/app/mission-control/page.tsx` contains the page component **twice**, including duplicated type definitions and a second `export default async function MissionControlPage()` block.
	 - `hermes/apps/web/app/observability/page.tsx` expects a flat response shape with `pending_runs` and `running_runs`, but `hermes/apps/api/src/hermes_api/api/routes/observability.py` returns `{ status, dashboard: ... }`.
	 - These are source-level confirmation points for the frontend regressions; they are not just inferred from the failed build.

## Executive verdict

The workspace is **materially improved** versus the prior audit, especially in backend wiring, workflow execution, risk controls, portfolio sync scaffolding, and test coverage. However, it is **not yet cleanly verified as a usable end-to-end paper-trading product**.

### Bottom line

- **Backend reality improved significantly**: the product API now bridges into real `hermes-agent` services instead of returning placeholder JSON; the workflow graph, execution worker, approvals, risk gate, and candidate generation are real.
- **Frontend is still not dependable**: the Next.js app is more than representational now, but it currently **does not build** because `mission-control/page.tsx` contains duplicate default exports.
- **Operational coherence improved but is still split**: documentation is better, Make targets exist, and startup order is clearer, but there is still **no single integrated stack** that boots the whole system cleanly.
- **Paper trading is closer, but not yet “comfortably usable”**: the backend can ingest signals, run a workflow, gate approvals, and simulate execution in paper mode, but the operator UI is broken at build time and some product surfaces still expose catalog-style summaries rather than first-class runtime objects.

## Comparison matrix against prior critical findings

| Prior issue | Current verification | Classification | Evidence |
|---|---|---|---|
| PostgreSQL / SQLAlchemy driver mismatch | Generic Postgres URLs are normalized to `postgresql+psycopg://`; observability fallback catches import errors, not just `OperationalError` | **Resolved** | `hermes-agent/backend/db/session.py`, `hermes-agent/backend/observability/service.py` |
| SQLite fallback behavior | Fallback path is real and CI explicitly clears `DATABASE_URL` for backend/tools tests | **Mostly Resolved** | `hermes-agent/backend/observability/service.py`, `hermes-agent/.github/workflows/tests.yml` |
| Observability storage initialization robustness | Schema bootstrap and fallback are stronger; timeline/dashboard queries are live | **Mostly Resolved** | `hermes-agent/backend/db/bootstrap.py`, `hermes-agent/backend/observability/service.py` |
| Placeholder FastAPI routes | Product API routes now call real backend bridge functions | **Mostly Resolved** | `hermes/apps/api/src/hermes_api/api/routes/{agents,execution,risk,observability,portfolio}.py`, `hermes/apps/api/src/hermes_api/integrations/hermes_agent.py` |
| Placeholder Next.js pages | Pages now fetch live endpoints and include operator controls, but the app currently fails to build | **Partially Resolved** | `hermes/apps/web/app/page.tsx`, `hermes/apps/web/app/mission-control/page.tsx`, build failure evidence |
| Exchange-backed portfolio/account sync | Real sync service exists and persists snapshots, but remains credential-gated and introduced a warning regression | **Partially Resolved** | `hermes-agent/backend/services/portfolio_sync.py`, `hermes-agent/backend/tools/get_portfolio_state.py`, failing `test_shared_time_series_storage.py` |
| Execution-routing worker | Worker now routes signal events, approval-gates execution, enforces kill switch, simulates paper fills, and can place live orders | **Mostly Resolved** | `hermes-agent/backend/event_bus/workers.py` |
| Paper-trading flow completeness | Signal ingestion → workflow → execution_requested → approval/paper-mode path exists, but end-to-end operator UX remains incomplete | **Partially Resolved** | `hermes-agent/backend/tradingview/service.py`, `hermes-agent/backend/workflows/graph.py`, `hermes-agent/backend/event_bus/workers.py`, broken web build |
| Heuristic `get_risk_approval` | Tool now reads Redis kill switch and limits, volatility, and event-risk context | **Mostly Resolved** | `hermes-agent/backend/tools/get_risk_approval.py` |
| Placeholder `list_trade_candidates` | Strategy registry and scoring functions replaced static BTC/ETH output, with fallback only when data is unavailable | **Mostly Resolved** | `hermes-agent/backend/tools/list_trade_candidates.py`, `hermes-agent/backend/strategies/registry.py` |
| Docs drift | New runtime docs explain the split more clearly, but they overstate cohesion relative to the still-split compose/runtime reality | **Partially Resolved** | `hermes/docs/runtime-consolidation-plan.md`, `hermes/docs/local-runtime-flow.md`, compose files |
| Role identity/profile drift | Identities are now role-specific, but still share the same aggressive signature/authority language | **Partially Resolved** | `profiles/*/IDENTITY.md` |
| Notification flow wiring | Real notification delivery, persistence, and retry logic now exist | **Mostly Resolved** | `hermes-agent/backend/tools/send_notification.py`, `hermes-agent/backend/integrations/notifications/retry_worker.py` |
| Integrated local startup / compose flow | Better docs and Make targets exist, but the stack is still split across multiple compose files | **Partially Resolved** | `hermes/docs/local-runtime-flow.md`, `hermes/Makefile`, `hermes/docker-compose.yml`, `hermes-agent/docker-compose*.yml` |
| Model/provider route clarity | LiteLLM route naming and profile mapping are clearer and include fallbacks | **Mostly Resolved** | root `litellm_config.yaml`, `hermes-agent/litellm_config.yaml`, `profiles/*/config.yaml` |
| TradingView MCP / webhook clarity | Webhook path is real and secured; MCP remains an external, unmanaged dependency | **Partially Resolved** | `hermes-agent/backend/tradingview/router.py`, root `config.yaml` |

## What was fixed correctly

### Database driver and fallback work is real

The earlier DB/driver mismatch has been genuinely addressed.

- `hermes-agent/backend/db/session.py`
	- `normalize_database_url()` now upgrades `postgresql://` and `postgres://` to `postgresql+psycopg://`.
- `hermes-agent/backend/observability/service.py`
	- `_FALLBACK_EXCEPTIONS` now includes `ModuleNotFoundError` and `ImportError`, which directly addresses the original failure mode.
- `hermes-agent/.github/workflows/tests.yml`
	- the `backend-tools` job clears `DATABASE_URL` to force SQLite fallback in CI.

This is one of the strongest confirmed remediations from the earlier audit.

### Backend routes are no longer empty shells

The product API under `hermes/apps/api` is no longer purely placeholder-driven.

- `agents.py` reads the desk manifest and pulls recent decisions and timelines.
- `execution.py` exposes pending TradingView signal events, recent execution events, and approval queue actions.
- `risk.py` exposes kill switch state, risk evaluation, recent rejections, and candidate listing.
- `observability.py` exposes dashboard snapshot, workflow runs, failures, and correlation timelines.
- `portfolio.py` exposes current portfolio snapshot and a sync action.

This is backed by `hermes/apps/api/src/hermes_api/integrations/hermes_agent.py`, which imports real `hermes-agent` backend modules instead of returning canned data.

### Workflow, execution, and approval logic are real now

The strongest backend improvement is the move from scaffold workers to a functioning event-driven flow.

- `hermes-agent/backend/tradingview/service.py`
	- persists alerts, publishes internal events, and pushes stream events.
- `hermes-agent/backend/workflows/graph.py`
	- executes a typed workflow across ingest, market research, strategy planning, risk review, and final orchestration.
- `hermes-agent/backend/event_bus/workers.py`
	- handles `tradingview_signal_ready`
	- performs drawdown enforcement
	- checks the global kill switch
	- creates operator approvals when required
	- simulates execution in paper mode
	- places live orders through CCXT when paper mode is disabled
- `hermes-agent/backend/approvals.py`
	- persists approval requests in Redis and republishes approved execution events back into the event stream

This is a meaningful architectural upgrade from the prior scaffold state.

### Risk approval and strategy candidate generation are no longer obvious placeholders

- `hermes-agent/backend/tools/get_risk_approval.py`
	- checks kill switch state
	- loads risk limits from Redis
	- fetches volatility metrics and event-risk summaries
	- sizes approval using severity-aware heuristics

- `hermes-agent/backend/tools/list_trade_candidates.py`
	- uses `STRATEGY_REGISTRY`
	- scores momentum, mean reversion, and breakout strategies
	- fetches indicator snapshots and OHLCV data
	- persists strategy evaluations
	- only falls back to placeholder watch candidates if scoring data is unavailable

This is materially better than the old hardcoded candidate list.

## What was only partially fixed

### Frontend moved beyond static copy, but is not cleanly operational

There is real progress in the Next.js product app:

- `hermes/apps/web/app/page.tsx` fetches live `/observability` and `/resources` data.
- `hermes/apps/web/app/agents/page.tsx` and `app/agents/[agentId]/page.tsx` pull live agent and timeline data.
- `hermes/apps/web/components/KillSwitchPanel.tsx`, `PortfolioSyncButton.tsx`, and `ApprovalQueuePanel.tsx` provide actual operator mutations.

However, this improvement is **not fully verified as usable** because:

- `hermes/apps/web/app/mission-control/page.tsx` currently contains **duplicate `export default` definitions**, which causes the app to fail to build.
- The file also contains duplicated type and page content blocks, including two full `MissionControlPage` definitions, which strongly suggests a remediation merge error rather than a subtle TypeScript issue.
- `hermes/apps/web/app/observability/page.tsx` expects a flat response shape containing `pending_runs` and `running_runs`, but `hermes/apps/api/src/hermes_api/api/routes/observability.py` returns `{ status, dashboard: ... }`, not that shape.

So the frontend is no longer representational-only, but it is **still not dependable**.

### Portfolio sync is real, but portfolio state handling regressed slightly

The earlier audit noted the lack of exchange-backed portfolio sync. That has improved:

- `hermes-agent/backend/services/portfolio_sync.py` fetches balances from CCXT, resolves prices, computes equity, and persists snapshots.
- `hermes/apps/api/src/hermes_api/api/routes/portfolio.py` exposes `/portfolio/sync`.

But a new behavior introduced a small regression:

- `hermes-agent/backend/tools/get_portfolio_state.py` now attempts reconciliation whenever configured venues are considered, and emits a missing-credentials warning.
- This breaks `tests/backend/test_shared_time_series_storage.py::test_get_portfolio_state_reads_latest_shared_snapshot`, which expected a clean snapshot with no warnings.

Classification: **improved but not cleanly stabilized**.

### Runtime consolidation docs improved more than runtime consolidation itself

The new docs are genuinely better:

- `hermes/docs/runtime-consolidation-plan.md`
- `hermes/docs/local-runtime-flow.md`

They correctly identify:

- `hermes-agent/` as backend source of truth
- `hermes/` as product shell/API/UI layer
- the recommended local startup order

But the codebase still has:

- `hermes/docker-compose.yml`
- `hermes-agent/docker-compose.yml`
- `hermes-agent/docker-compose.litellm.yml`

There is still **no single compose file** that boots Postgres/Timescale, Redis, LiteLLM, backend runtime, API bridge, and web app together.

This means operational clarity improved, but operational unification remains incomplete.

### Identity/profile drift improved, but governance tone remains uneven

Compared with the previous audit, the role files are now meaningfully differentiated:

- `profiles/orchestrator/IDENTITY.md`
- `profiles/market-researcher/IDENTITY.md`
- `profiles/risk-manager/IDENTITY.md`
- `profiles/portfolio-monitor/IDENTITY.md`
- `profiles/strategy-agent/IDENTITY.md`

Each now describes a distinct role and boundary.

However, all still retain the same shared signature and aggressive tone. That is better than before, but not fully aligned with clean governance separation for risk and monitoring roles.

## What remains unresolved

### There is still no single authoritative integrated runtime entrypoint

The product API now imports the backend directly, which is a pragmatic improvement, but the workspace is still fundamentally split:

- backend truth lives in `hermes-agent/backend`
- product API lives in `hermes/apps/api`
- product UI lives in `hermes/apps/web`
- operator/admin UI still also exists in `hermes-agent`

There is still no packaged unified runtime that eliminates this split.

### Operator auth remains optional, not enforced by default

`hermes/apps/api/src/hermes_api/core/security.py` introduces API key enforcement for protected routes, but it explicitly bypasses auth when `HERMES_API_KEY` is unset.

That is convenient for local development, but it means:

- operator auth is still **not a hard control**
- write actions can be unauthenticated in default local setups

This is **better than no mechanism**, but it is not a production-grade resolution.

### Product resource surfaces still mix live data with catalog-style summaries

`hermes/apps/api/src/hermes_api/api/routes/resources.py` is not a pure placeholder anymore, but it still synthesizes a catalog of status strings such as `partial`, `missing`, and `scaffolded` instead of exposing first-class resources with dedicated backend endpoints.

It also understates some implemented backend improvements, for example:

- it still calls the Strategy Library `scaffolded` even though `hermes-agent/backend/strategies/registry.py` exists and `list_trade_candidates.py` uses it.

So this route is now **partially representational rather than purely operational**.

### TradingView MCP is still externally coupled

Root `config.yaml` still points to an external local path for the TradingView MCP server.

- MCP remains outside the repo and unmanaged here.
- The webhook path is real and documented, but the MCP dependency is still not self-contained.

## Regressions found during this verification pass

### 1. Frontend build regression in Mission Control

`hermes/apps/web/app/mission-control/page.tsx` currently fails the web build due to duplicate default exports.

This is a concrete regression because it blocks `npm run build`.

**Classification:** **Regressed**

### 2. Product/frontend contract drift in Observability page

`hermes/apps/web/app/observability/page.tsx` expects:

- `pending_runs`
- `running_runs`
- `recent_failures`
- `recent_risk_rejections`
- `recent_notifications`

But `hermes/apps/api/src/hermes_api/api/routes/observability.py` returns a nested `dashboard` object from `service.get_dashboard_snapshot()`.

This creates a likely runtime mismatch even after the build blocker is fixed.

This is not a speculative mismatch: the route implementation and page type expectations are directly inconsistent in the current source tree.

**Classification:** **Regressed**

### 3. Portfolio snapshot test regression

`tests/backend/test_shared_time_series_storage.py::test_get_portfolio_state_reads_latest_shared_snapshot` now fails because `get_portfolio_state()` adds a warning about missing execution venues even when a valid latest snapshot exists.

That is a small but real behavior regression in the storage/read path.

**Classification:** **Regressed**

### 4. Secret handling regression in tracked profile configs

The profile configs for:

- `profiles/portfolio-monitor/config.yaml`
- `profiles/strategy-agent/config.yaml`

contain inline `api_key` entries under `custom_providers`, including a non-empty literal key value.

That is a security regression relative to the stated `.env`-driven configuration intent and should be treated as a tracked-secret exposure risk.

**Classification:** **Regressed**

## Backend verification by area

### Health endpoints

- `hermes/apps/api/src/hermes_api/api/routes/health.py` is still simple, but functional.
- Health is implemented, not placeholder.

**Status:** **Implemented**

### Agent endpoints

- Agent list/detail/timeline now use real manifest plus observability history.
- Agent detail surfaces correlated timelines, not just static metadata.

**Status:** **Mostly Resolved**

### Execution endpoints

- `/execution` surfaces pending TradingView signal events and recent execution events.
- Approval queue endpoints exist and mutate Redis-backed approval state.
- Direct order placement exists but is still heavily configuration-gated.

**Status:** **Mostly Resolved**

### Risk endpoints

- kill switch endpoints exist
- portfolio view exists
- risk evaluation exists
- candidate list exists

**Status:** **Mostly Resolved**

### Resource endpoints

- route exists and now pulls some live context
- still partly catalog/synthesis driven rather than exposing dedicated resource APIs

**Status:** **Partially Resolved**

### Observability endpoints

- dashboard/workflow/failure/timeline routes are real
- backed by `ObservabilityService`

**Status:** **Mostly Resolved**

### Service modules and DB/fallback logic

- significant improvement in DB session normalization and fallback behavior
- observability queries and persistence are real
- bootstrap-driven Timescale schema remains in use rather than migration-based evolution

**Status:** **Mostly Resolved**

### Retry and error handling

- notification retry worker exists
- execution worker retries transient live-order failures by returning `False`
- error recording is richer than before
- full operational retry policies remain uneven across all integrations

**Status:** **Partially Resolved**

## Frontend verification

### Dashboard page

- now fetches real observability/resources data
- renders workflow failures, notifications, execution events, and resource coverage

**Status:** **Partially Resolved**

### Mission Control page

- includes kill switch, portfolio sync, approval queue, execution queue, workflows, failures
- currently fails build due to duplicate exports

**Status:** **Regressed**

### Agents page

- agent roster is fed from the live desk manifest and observability layer
- detail page includes correlated timelines

**Status:** **Mostly Resolved**

### Observability page

- appears intended to be real
- currently mismatched with the backend response shape

**Status:** **Partially Resolved**

### Data fetching, actions, loading/error states

- `fetchHermesApi()` and `postHermesApi()` exist
- pages provide fallbacks and error strings
- operator actions exist for kill switch, approvals, and sync

**Status:** **Mostly Resolved**

### Overall frontend conclusion

The product frontend is **materially more functional than before**, but not yet trustworthy because the build is broken and at least one page/API contract is inconsistent.

## Agent verification

| Agent | Verification | Classification | Evidence |
|---|---|---|---|
| Orchestrator & Trader | Real orchestration node exists; final decisions and execution handoff are persisted and published | **Mostly Resolved** | `hermes-agent/backend/workflows/graph.py` |
| Market Research | Real node gathers market/macro/event/on-chain/volatility context; no durable memo write in workflow by default | **Partially Resolved** | `hermes-agent/backend/workflows/graph.py`, `hermes-agent/backend/tools/get_*` |
| Portfolio Monitor | Snapshot read path and live sync exist; not a separately invoked workflow node in the trading graph | **Partially Resolved** | `hermes-agent/backend/services/portfolio_sync.py`, `hermes-agent/backend/tools/get_portfolio_state.py` |
| Risk Manager | Real runtime node plus kill switch and approval logic; hard veto path exists | **Mostly Resolved** | `hermes-agent/backend/workflows/graph.py`, `hermes-agent/backend/tools/get_risk_approval.py`, `hermes-agent/backend/tools/set_kill_switch.py` |
| Strategy Agent | Real node plus registry-backed candidate generation; still lacks backtest/promotion/retirement loop wiring | **Partially Resolved** | `hermes-agent/backend/workflows/graph.py`, `hermes-agent/backend/strategies/registry.py`, `hermes-agent/backend/tools/list_trade_candidates.py` |

## Shared resource verification

| Resource | Before | Now | Classification | Notes |
|---|---|---|---|---|
| Market Price Feed | Partial | Still partial but real provider-backed tools exist | **Partially Resolved** | still backend-heavy, not fully surfaced in product API |
| Order Book / Depth Feed | Missing | `get_order_book` now exists, plus public order-book support in execution integrations | **Partially Resolved** | improvement is real, but not yet central to Mission Control |
| Trades / Tape Feed | Missing | `get_recent_trades` and tape models now exist | **Partially Resolved** | improved, not yet prominent in workflows/UI |
| Technical Indicator Engine | Partial | Still partial, but candidate scanning uses indicator snapshots and OHLCV | **Partially Resolved** | broader deterministic engine still incomplete |
| Derivatives & Funding Data | Partial | Real `get_funding_rates`, `get_liquidation_zones`, `get_defi_open_interest` paths exist | **Partially Resolved** | stronger than prior audit, still not deeply workflow-wired |
| Portfolio & Account State | Partial | Live sync + persisted snapshots now exist | **Partially Resolved** | still credential-gated and regression noted in warnings |
| Risk Policy Engine | Partial | Real approval gate and kill switch exist | **Mostly Resolved** | still heuristic/policy-lite rather than full policy-as-code |
| Strategy Library | Scaffolded | Registry and evaluators now exist | **Partially Resolved** | not yet full lifecycle-managed strategy system |
| News / Sentiment / Narrative Feed | Partial | Still partial; provider tools remain backend-centric | **Partially Resolved** | no major product-level surfacing added |
| On-Chain / Ecosystem Intelligence | Partial | Still partial; tool coverage exists | **Partially Resolved** | not fully promoted into product UI |
| Execution / Broker / Exchange Connector | Partial | Much stronger: CCXT, routing, paper/live gating, approval queue | **Mostly Resolved** | still not production hardened |
| Memory / Knowledge / Research Store | Partial | `ResearchMemoRow`, `save_research_memo`, `get_research_memos` now exist | **Partially Resolved** | added store is real, but not core workflow-default yet |

## Models and routing verification

### What improved

- root `litellm_config.yaml` and `hermes-agent/litellm_config.yaml` define the same route names:
	- `orchestrator-default`
	- `research-default`
	- `portfolio-default`
	- `risk-default`
	- `strategy-default`
- LiteLLM router fallbacks are now explicitly declared.
- profile configs point to route names consistently.

### What remains weak

- no strong model health-check layer was found in the product API/web stack
- no route-vs-outcome evaluation loop was found
- local/cloud routing is clearer on paper than it is validated operationally

### Verification result

- OpenAI: **operationally configured via LiteLLM routes**
- Anthropic: **operationally configured via LiteLLM routes**
- LM Studio: **present and used in portfolio/strategy routing**
- Ollama: **still not an active first-class trading route in the verified setup**

**Overall classification:** **Mostly Resolved**

## MCP / integration verification

| Integration | Current state | Classification |
|---|---|---|
| TradingView webhook | Real route with shared-secret verification | **Mostly Resolved** |
| TradingView MCP | Still external local dependency via root `config.yaml` | **Unresolved** |
| Telegram | Real client + tool + persistence path | **Mostly Resolved** |
| Slack | Real client + tool + persistence path | **Mostly Resolved** |
| Notification retries | Real retry worker exists | **Partially Resolved** |
| CCXT / BitMart execution | Real client and worker path exist | **Mostly Resolved** |
| Redis / event bus | Real approval and event workers exist | **Mostly Resolved** |
| Paperclip | Still conceptual / compatibility-oriented, not a resident runtime here | **Unresolved** |

## Infrastructure verification

### Improved

- `hermes/Makefile` adds clearer commands for API/web/dev/backend helpers.
- Docker compose files have health checks and cleaner env wiring than before.
- local startup order is documented.

### Still incomplete

- product compose only boots `postgres`, `api`, and `web`
- backend compose separately boots `redis`, `timescaledb`, `hermes`
- LiteLLM is still separate
- there is still no one-shot integrated stack

**Classification:** **Partially Resolved**

## Database / Timescale verification

### Verified improvements

- PostgreSQL URLs are normalized to `psycopg`
- Timescale extension bootstrap is real in `hermes-agent/backend/db/bootstrap.py`
- schema includes more durable runtime entities:
	- workflow runs / steps
	- tool calls
	- agent decisions
	- execution events
	- system errors
	- notifications sent
	- portfolio snapshots
	- research memos
	- strategy evaluations

### Still weak

- schema evolution is still bootstrap-driven, not migration-driven
- persistence ownership remains centered in `hermes-agent`, not unified under one shared package

**Classification:** **Mostly Resolved**

## Tests and quality verification

### Hermes product repo

- `hermes/pyproject.toml` correctly declares API dependencies including `fastapi`.
- Local test execution failed because the active environment did not have those dependencies installed.
- This means the repo is **not self-verifying from the shared workspace venv without extra setup**.

**Classification:** **Partially Resolved**

### Hermes Agent

- CI is much stronger than before via `hermes-agent/.github/workflows/tests.yml`.
- Targeted repo-root execution showed **3026 pass / 1 fail / 38 skip**.
- That is a major improvement over the earlier audit’s 14 backend/tool failures.
- The worse **12-failure** run was reproduced only when pytest was launched from outside `hermes-agent/`, which exposed cwd-sensitive source-inspection tests rather than a broader backend runtime break.

**Classification:** **Mostly Resolved**

### Web quality gate

- `hermes/.github/workflows/node-ci.yml` would correctly catch the current build failure.
- The current frontend does **not** pass that gate because `mission-control/page.tsx` is broken.

**Classification:** **Regressed**

## Security and governance verification

### Improved

- paper-mode/live-order blocking is real in `hermes-agent/backend/integrations/execution/ccxt_client.py`
- kill switch exists and is enforced in the worker and risk approval path
- TradingView webhook secret verification is real

### Still weak or incomplete

- operator auth is optional and bypassed when `HERMES_API_KEY` is empty
- there is still no robust full authorization model
- profile identities still carry overly aggressive shared authority language
- tracked profile configs contain inline `api_key` values, which is a serious secret-handling concern

**Overall classification:** **Partially Resolved**, with one clear **security regression** due inline secrets in profile config.

## What still only appears fixed in docs

### “Consolidated runtime” story

The docs explain a preferred local flow well, but the actual system is still spread across:

- product compose
- backend compose
- LiteLLM compose
- multiple independent startup commands

So consolidation is **documented better than it is implemented**.

### “Mission Control is now live” story

The web code clearly moved toward live data and operator actions, but the actual build failure means the surface is not yet verifiably operational.

## Manual setup still required

- `uv sync` in `hermes/` to provision API dependencies before local test runs
- exchange credentials for live portfolio sync / live execution
- Redis + Timescale + LiteLLM startup in separate steps
- TradingView webhook secret configuration
- Telegram / Slack credentials for non-log notification delivery
- external TradingView MCP server if MCP mode is required

## Is the platform materially closer to a usable paper-trading system?

**Yes — but not enough to call it comfortably usable yet.**

### Why it is closer

- the backend is no longer mostly aspirational
- real workflow orchestration exists
- real approval/paper-execution path exists
- real risk gate and kill switch exist
- real portfolio sync scaffolding exists
- observability persistence is much stronger

### Why it still falls short

- product web app currently fails to build
- runtime remains split and operationally awkward
- portfolio state behavior has a new warning regression
- operator auth is not a hard default
- product resource/API surfaces are still mixed with representational summaries

## Final classification summary

### Resolved

- PostgreSQL / SQLAlchemy driver mismatch

### Mostly Resolved

- SQLite fallback behavior
- observability initialization robustness
- placeholder FastAPI routes
- execution-routing worker
- `get_risk_approval` replacement
- `list_trade_candidates` replacement
- notification flow wiring
- model/provider route clarity
- database/Timescale coherence
- Hermes Agent backend/tool test health

### Partially Resolved

- placeholder Next.js pages
- exchange-backed portfolio/account sync
- paper-trading flow completeness
- docs drift
- role identity/profile drift
- integrated local startup / compose flow
- TradingView webhook/MCP clarity
- product API local verification ergonomics
- frontend observability/operator UX coherence
- shared resource surfacing in product API
- security / governance hardening

### Unresolved

- external TradingView MCP dependency
- single authoritative integrated runtime packaging
- full policy-as-code risk engine
- full product-grade auth and authorization

### Regressed

- `hermes/apps/web/app/mission-control/page.tsx` buildability
- frontend/backend response-shape alignment for observability
- portfolio snapshot read-path warning behavior
- secret handling in tracked profile configs

### Unable to verify cleanly

- a one-command local integrated paper-trading workflow from product UI to backend completion, because the current web build failure blocks that verification path

## Recommended immediate next actions

1. Fix `hermes/apps/web/app/mission-control/page.tsx` duplicate default export and remove duplicated page content.
2. Align `hermes/apps/web/app/observability/page.tsx` with the actual `/observability` response shape, or change the API shape intentionally.
3. Adjust `hermes-agent/backend/tools/get_portfolio_state.py` so persisted snapshot reads do not emit missing-execution warnings unless reconciliation was explicitly requested.
4. Remove inline provider keys from tracked profile configs and move them back to env-based configuration.
5. Add a single integrated dev entrypoint or compose overlay that starts backend infra, LiteLLM, API bridge, and web together.
6. Harden product auth so write endpoints are not effectively open by default in realistic operator deployments.

## Overall conclusion

The remediation work was **substantial and real**. This is not the same scaffold-heavy workspace described in the original audit. The backend has advanced meaningfully, the product API now bridges to real services, and the trading workflow is materially closer to an actual supervised paper-trading architecture.

But this verification pass also found that the repo is **not yet in a clean “post-fix complete” state**. The biggest blockers are a broken product web build, lingering runtime split, a small portfolio regression, and unfinished governance/security hardening. The project is **closer to usable paper trading**, but it still needs another hardening pass before the product surface can honestly be called verified end-to-end.

One final nuance: several of the strongest backend improvements currently live in the `hermes-agent/` working tree rather than in a clean committed state. So the technical direction is much better, but the delivery state is still a little “works on this desk, not yet signed off by the desk.”
