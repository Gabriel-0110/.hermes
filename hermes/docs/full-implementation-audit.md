# Hermes Complete Implementation Audit

## 1. Executive Summary

Hermes is currently a **split-state platform** rather than a single coherent repository. The `hermes/` monorepo contains the intended product shape for the trading platform, but it is still mostly a scaffold: the FastAPI routes are placeholders, the Next.js Mission Control UI is static, the shared packages are skeletal, and only the health endpoint is meaningfully functional. In contrast, `hermes-agent/` contains a substantial amount of real backend implementation for market-data integrations, TradingView webhook ingestion, shared time-series persistence, Redis event transport, observability storage, notification delivery, and a typed trading workflow graph. The workspace also contains `teams/trading-desk/` and `profiles/*`, which define the five-agent desk, tool permissions, paper-mode rules, and LiteLLM route selection, but much of that layer is declarative rather than fully enforced end-to-end.

Current maturity level is best described as **Early-to-Moderate for internal paper-trading infrastructure, Early for productized Hermes platform, Not Ready for autonomous live trading**. The strongest areas are the shared backend plumbing in `hermes-agent/`, especially TradingView ingestion, provider wrappers, observability schemas, and the LiteLLM route map. The weakest areas are the actual `hermes/` product surfaces, strategy/risk logic depth, portfolio/account synchronization, execution hardening, and production-safe security controls. The biggest blockers are: lack of a single integrated runtime, placeholder Mission Control/API layers, missing/heuristic agent logic, incomplete portfolio and execution wiring, and environment/dependency issues that currently break part of the backend test suite.

What is closest to production today is the **shared backend utility layer** in `hermes-agent/`: market/news/on-chain provider wrappers, Timescale/SQLite persistence, TradingView webhook ingestion, Redis event-bus contracts, notification transports, and operator-facing observability endpoints. What remains mostly scaffolded is the **actual Hermes trading application layer** in `hermes/`: backend routers, frontend Mission Control UI, package boundaries for agents/resources/policies/tools, and the explicit architecture described in `docs/architecture/hermes-trader-architecture.md`.

## 2. Audit Method

This audit is based on direct repository inspection of the full workspace rooted at the current Hermes workspace, not on architectural assumptions.

Status labels below are evidence-based:

- **Implemented**: clearly present and functionally real in code/config.
- **Mostly Implemented**: mostly real, but with small missing pieces.
- **Partial**: meaningful implementation exists, but major gaps remain.
- **Scaffolded**: structure exists, but real functionality is minimal.
- **Missing**: expected capability was not found.
- **Unclear**: references exist, but implementation evidence is insufficient.

The audit included:

- repository structure review with import/config following
- docs, READMEs, roadmap, security, setup, and integration docs
- backend and frontend code in `hermes/`
- backend, web server, workflows, integrations, DB/event bus, and tests in `hermes-agent/`
- team manifests, role skill files, paper-mode rules, and agent profiles in `teams/` and `profiles/`
- environment templates, Docker Compose files, CI workflows, bootstrap scripts, and root runtime config
- targeted test execution in both `hermes/` and `hermes-agent/`

## 3. Repository-Wide Status Snapshot

| Area | Status | Evidence | Main Gaps | Priority |
|------|--------|----------|-----------|----------|
| Docs and architecture | Partial | `docs/architecture/hermes-trader-architecture.md`, `hermes/README.md`, `hermes/ARCHITECTURE.md`, `hermes-agent/*.md` | Docs describe more than `hermes/` implements; some `hermes-agent` docs lag code | High |
| FastAPI product backend (`hermes/apps/api`) | Scaffolded | Placeholder routes for agents/execution/risk/resources/observability | No real orchestration, persistence, auth, policy, execution, or workers | Critical |
| Next.js product frontend (`hermes/apps/web`) | Scaffolded | Static pages for dashboard, Mission Control, agents | No API integration, state, auth, live data, operator actions, or tests | High |
| Shared package layer in `hermes/packages` | Scaffolded | Placeholder modules for agents/resources/tools/policies/observability | No substantive implementation behind architecture boundaries | High |
| Shared backend services in `hermes-agent/backend` | Partial | Real integrations, TradingView ingestion, DB models, event bus, workflows, observability | Heuristic logic, incomplete execution/portfolio wiring, test breakage | Critical |
| Agent desk manifests and role profiles | Partial | `teams/trading-desk/agents.yaml`, `agent_profiles/*.yaml`, `profiles/*/config.yaml` | Mostly declarative; model/provider blanks in team manifest; identities misaligned | High |
| Shared Intelligence Layer | Partial | Tool wrappers and normalized models in `hermes-agent/backend/tools` and `backend/models.py` | Order book, tape, true strategy library, robust risk engine, research store missing | Critical |
| Model provider routing | Partial | LiteLLM route maps in root and `hermes-agent/litellm_config.yaml` | No unified provider abstraction in `hermes/`; Ollama path mostly conceptual; runtime coupling unclear | High |
| MCP and external integrations | Partial | TradingView webhook path real; root MCP config points at external TradingView server | TradingView MCP itself is outside repo; Paperclip mostly conceptual; exchange path not fully operational | High |
| Notifications and channels | Partial | Telegram/Slack clients exist in `hermes-agent`; env templates present | End-to-end operator notification flow not wired through product UI/workflows | Medium |
| Database and persistence | Partial | SQLAlchemy models, Timescale bootstrap, SQLite fallback, TradingView store | Portfolio/account sync incomplete; persistence split across repos; no coherent migration layer in `hermes/` | Critical |
| Infrastructure and local dev | Partial | Docker Compose, Dockerfiles, bootstrap scripts in both repos | Two parallel stacks, manual secrets/service setup, likely startup drift | High |
| Observability and auditability | Partial | Real observability service, tables, API endpoints in `hermes-agent` | `hermes/` observability is placeholder; tests fail due DB driver mismatch | High |
| Security, governance, and safety | Partial | Paper-mode guard script, secret redaction in observability, localhost CORS in web server | No operator auth in product app, incomplete policy enforcement, dangerous identity/config defaults | Critical |
| Tests and quality gates | Partial | CI in `hermes/`, test suite in `hermes-agent`, lint/test pass in scaffold repo | Coverage uneven; 14 backend tests failing locally due dependency/backend assumptions | Critical |

## 4. Detailed Findings by Domain

### Docs

Summary:

- `docs/architecture/hermes-trader-architecture.md` is clear and specific about the target platform.
- `hermes/README.md` and `hermes/ARCHITECTURE.md` explicitly admit that `hermes/` is a scaffold.
- `hermes-agent/` has extensive operational docs for TradingView ingestion, Timescale, Redis Streams, LiteLLM, notifications, observability, and workflows.

Files reviewed:

- `docs/architecture/hermes-trader-architecture.md`
- `hermes/README.md`
- `hermes/ARCHITECTURE.md`
- `hermes/ROADMAP.md`
- `hermes/SECURITY.md`
- `hermes-agent/INTEGRATIONS.md`
- `hermes-agent/TRADINGVIEW_INGESTION.md`
- `hermes-agent/WORKFLOW_ARCHITECTURE.md`
- `hermes-agent/OBSERVABILITY_SETUP.md`
- `hermes-agent/TIMESCALE_SETUP.md`
- `hermes-agent/NOTIFICATIONS_SETUP.md`

Findings:

- Architecture docs are ahead of `hermes/` code by a wide margin.
- `hermes-agent` docs describe the real shared backend much more accurately than the `hermes/` product repo.
- Some `hermes-agent` docs lag current code. Example: `INTEGRATIONS.md` still describes `get_execution_status` and `send_notification` as stubs, while real implementations now exist.
- Workspace-level reality is undocumented: the actual system depends on `hermes/`, `hermes-agent/`, `teams/trading-desk/`, `profiles/*`, root `config.yaml`, and root `litellm_config.yaml`, but no single top-level doc explains how those parts compose.

Required next steps:

- Create a single workspace architecture doc that explains the split between `hermes/` and `hermes-agent/`.
- Update all integration/setup docs to distinguish implemented backend utilities from still-scaffolded product surfaces.
- Document the actual bootstrap order: LiteLLM, Timescale/Postgres, Redis, TradingView ingestion, agent profiles, dashboard/API surfaces.

### Backend

Summary:

- `hermes/apps/api` is scaffolded.
- `hermes-agent/backend` contains the real backend implementation today.

Files reviewed:

- `hermes/apps/api/src/hermes_api/main.py`
- `hermes/apps/api/src/hermes_api/api/router.py`
- `hermes/apps/api/src/hermes_api/api/routes/*.py`
- `hermes/apps/api/src/hermes_api/core/config.py`
- `hermes/apps/api/src/hermes_api/domain/*.py`
- `hermes-agent/backend/models.py`
- `hermes-agent/backend/db/*`
- `hermes-agent/backend/event_bus/*`
- `hermes-agent/backend/integrations/**/*`
- `hermes-agent/backend/observability/*`
- `hermes-agent/backend/tools/*`
- `hermes-agent/backend/tradingview/*`
- `hermes-agent/backend/workflows/*`
- `hermes-agent/backend/evaluation/*`

Findings:

- `hermes/apps/api` exposes route groups for health, agents, execution, risk, resources, and observability, but every non-health route returns placeholder JSON.
- The domain modules in `hermes/apps/api/src/hermes_api/domain/` are catalog-style stubs, not real services.
- `hermes-agent/backend` is materially more advanced:
  - normalized Pydantic models exist for market, sentiment, execution, notifications, workflow outputs, and more
  - TradingView ingestion path is real and persists data
  - TimescaleDB/SQLite storage and observability repos exist
  - Redis Streams contracts and runtime exist
  - provider wrappers are real and normalized
  - a typed trading workflow graph exists
- Major backend incompleteness remains:
  - worker handlers in `backend/event_bus/workers.py` are scaffolds that only log and ack
  - there is no real execution-routing worker
  - portfolio/account synchronization is not wired to exchange data
  - strategy candidate generation is still placeholder/heuristic
  - risk approval is heuristic rather than policy-engine backed
  - workflow durability is local-only and not robustly orchestrated

Blockers:

- The platform backend has no single authoritative runtime entrypoint that merges `hermes/` product API with `hermes-agent/` backend services.
- `hermes-agent` observability/storage code attempts PostgreSQL when `DATABASE_URL` is present, but falls back only on `OperationalError`; missing `psycopg2` raises `ModuleNotFoundError`, causing 14 test failures instead of graceful fallback.

### Frontend

Summary:

- The intended Mission Control frontend in `hermes/apps/web` is scaffolded.
- The more functional operator UI is actually `hermes-agent/web`, which is Vite/React, not Next.js.

Files reviewed:

- `hermes/apps/web/app/layout.tsx`
- `hermes/apps/web/app/page.tsx`
- `hermes/apps/web/app/mission-control/page.tsx`
- `hermes/apps/web/app/agents/page.tsx`
- `hermes/apps/web/README.md`
- `hermes-agent/web/src/**/*`
- `hermes-agent/hermes_cli/web_server.py`

Findings:

- `hermes/apps/web` pages are static marketing/control-surface scaffolds with explicit TODO language.
- No API client, auth layer, data fetching, mutations, review queues, execution approvals, or observability widgets exist in the Next.js app.
- No frontend test suite was found for `hermes/apps/web`.
- `hermes-agent/web` is materially real:
  - status, sessions, config, env, logs, cron, skills, analytics, and observability pages exist
  - `hermes_cli/web_server.py` exposes many REST endpoints and serves that UI
- Architectural mismatch: the intended product architecture says Next.js Mission Control, but the real operator console today lives in `hermes-agent` as a separate Vite/FastAPI-like management UI.

### Agents

Summary:

- The five-agent trading desk exists as manifests, permissions, profiles, and role skill files.
- There are not five clearly separated runtime modules implementing each agent end-to-end.

Files reviewed:

- `teams/trading-desk/TEAM.md`
- `teams/trading-desk/agents.yaml`
- `teams/trading-desk/agent_profiles/*.yaml`
- `teams/trading-desk/skills/*.yaml`
- `profiles/*/config.yaml`
- `profiles/*/ROLE_SKILLS.yaml`
- `profiles/*/IDENTITY.md`
- `hermes/packages/agents/src/hermes_agents/*`
- `hermes-agent/backend/workflows/agents.py`
- `hermes-agent/backend/workflows/graph.py`

Findings:

- The clearest definition of the agent system is in YAML, not Python.
- `hermes/packages/agents` only contains placeholder `__init__.py` files with names/docstrings.
- The real runtime behavior appears in the workflow graph and tool composition, not dedicated per-agent classes.
- Team manifests are strong on boundaries and allowed tools.
- `agents.yaml` leaves `model` and `provider` blank for every agent, so the manifest is not the complete runtime source of truth.
- `profiles/*/config.yaml` routes all roles through LiteLLM route names, which is more operationally useful than the desk manifest.
- `profiles/*/IDENTITY.md` files are effectively copy-pasted across all roles and conflict with the intended role separation. The risk manager, market researcher, and portfolio monitor all describe themselves as the same apex profit-seeking trader rather than distinct governance/research/monitoring roles.

### Shared Intelligence Layer

Summary:

- Real normalized tools exist, but the layer is uneven and several key resource classes are absent.

Files reviewed:

- `hermes-agent/backend/tools/*.py`
- `hermes-agent/backend/models.py`
- `hermes/packages/resources/*`
- `hermes/packages/tools/*`

Findings:

- Shared resource logic is real mainly inside `hermes-agent/backend/tools`, not inside `hermes/packages/resources`.
- Tool wrappers are consistent and observable, but several capabilities are heuristic or synthetic.
- `hermes/packages/resources` and `hermes/packages/tools` are scaffolds only.

### Model Providers

Summary:

- LiteLLM route configuration is real and meaningful.
- OpenAI and Anthropic are concretely wired through route config.
- LM Studio is wired as a local provider path.
- Ollama appears in env/config scaffolds but was not found as a real active route in the current trading workspace.

Files reviewed:

- `litellm_config.yaml`
- `hermes-agent/litellm_config.yaml`
- `profiles/*/config.yaml`
- `hermes/apps/api/src/hermes_api/core/config.py`
- `hermes/.env.example`
- `hermes-agent/.env.example`

Findings:

- Root and `hermes-agent/` LiteLLM configs define named routes for `orchestrator-default`, `research-default`, `portfolio-default`, `risk-default`, and `strategy-default`.
- OpenAI and Anthropic are real upstreams behind LiteLLM.
- LM Studio is used for portfolio and strategy routes.
- `smart_model_routing.enabled` is false in profiles, so dynamic local/cloud selection is not currently active.
- No explicit timeout/retry/fallback code was found in `hermes/` product backend; provider control is mostly delegated to LiteLLM and individual SDK clients.
- Ollama is present only as config/env placeholders in the product scaffold and in unrelated profile skill archives; no active trading route currently points to Ollama.

### MCP / External Integrations

Summary:

- TradingView webhook ingestion is implemented.
- TradingView MCP is referenced, but the MCP server itself is outside the repo.
- Paperclip is treated as a compatibility target, not a resident implementation.

Files reviewed:

- root `config.yaml`
- `hermes-agent/backend/tradingview/*`
- `hermes-agent/TRADINGVIEW_INGESTION.md`
- `hermes-agent/EVENT_BUS_ARCHITECTURE.md`
- `hermes-agent/INTEGRATIONS.md`
- `teams/trading-desk/scripts/bitmart_paper_guard.py`

Findings:

- Root `config.yaml` defines `mcp_servers.tradingview` pointing to an external local TradingView MCP server path. That is an external local dependency, not vendored into this workspace.
- Real TradingView integration in-repo is webhook-based, not MCP-based.
- Paperclip appears throughout docs as a compatibility consumer of LiteLLM and Redis/TradingView events, but no Paperclip runtime is present here.
- Exchange connectivity is BitMart-focused through CCXT, but live end-to-end execution orchestration remains incomplete.

### Notifications / Channels

Summary:

- Telegram and Slack client wrappers are real in `hermes-agent`.
- The product repo only contains config placeholders.

Files reviewed:

- `hermes-agent/backend/integrations/notifications/telegram_client.py`
- `hermes-agent/backend/integrations/notifications/slack_client.py`
- `hermes-agent/backend/tools/send_notification.py`
- `hermes-agent/NOTIFICATIONS_SETUP.md`
- `hermes/.env.example`
- `hermes-agent/.env.example`

Findings:

- Notification clients exist and support outbound delivery.
- `send_notification` exists as a real tool wrapper.
- Team skills still describe alert delivery as stubbed/unwired, so team YAML has fallen behind code.
- No unified notification queue, retry policy dashboard, or delivery-status reconciliation was found in `hermes/`.

### Database / Persistence

Summary:

- Shared persistence is substantially implemented in `hermes-agent`.
- Product persistence in `hermes/` is mostly configuration only.

Files reviewed:

- `hermes/infrastructure/db/init/001-timescaledb.sql`
- `hermes-agent/backend/db/models.py`
- `hermes-agent/backend/db/bootstrap.py`
- `hermes-agent/backend/db/session.py`
- `hermes-agent/backend/tradingview/store.py`

Findings:

- TimescaleDB is genuinely used in `hermes-agent`; this is not just aspirational.
- `ensure_time_series_schema()` bootstraps extension/table/hypertable state.
- Persistence tables cover TradingView events, portfolio snapshots, risk events, notifications, workflow runs/steps, tool calls, decisions, execution events, and system errors.
- SQLite fallback exists for degraded/local operation.
- No migration framework like Alembic was found; schema management is bootstrap-driven.
- `hermes/` itself does not own an equivalent production data model yet.

### Infrastructure / DevOps

Summary:

- There are two partially overlapping deployment stories.

Files reviewed:

- `hermes/docker-compose.yml`
- `hermes/infrastructure/docker/*.Dockerfile`
- `hermes/infrastructure/scripts/*.sh`
- `hermes/.github/workflows/*.yml`
- `hermes-agent/docker-compose.yml`
- `hermes-agent/docker-compose.litellm.yml`

Findings:

- `hermes/docker-compose.yml` stands up Postgres/Timescale, API, and web.
- `hermes-agent/docker-compose.yml` stands up Redis, TimescaleDB, and Hermes dashboard runtime.
- `hermes-agent/docker-compose.litellm.yml` adds the LiteLLM gateway.
- There is no single compose stack that brings up the whole intended system coherently.
- Bootstrap scripts are minimal and do not verify provider keys, LiteLLM readiness, TradingView secret config, or MCP availability.
- CI exists for the scaffold repo, but not a comparable workspace-level pipeline that validates the integrated stack.

### Observability

Summary:

- Strong relative to the rest of the workspace, but not production-hardened.

Files reviewed:

- `hermes/packages/observability/*`
- `hermes-agent/backend/observability/*`
- `hermes-agent/OBSERVABILITY_SETUP.md`
- `hermes-agent/hermes_cli/web_server.py`

Findings:

- `hermes/packages/observability` is placeholder-only.
- `hermes-agent/backend/observability/service.py` is real and includes payload redaction, persistence, and query support.
- Observability endpoints/pages exist in the Hermes Agent dashboard.
- Current local test failures prove observability fallback is not robust against missing PostgreSQL driver packages when `DATABASE_URL` is set.

### Security / Governance

Summary:

- Governance intent is strong.
- Enforcement is incomplete and sometimes undermined by config/docs drift.

Files reviewed:

- `hermes/SECURITY.md`
- `teams/trading-desk/TEAM.md`
- `teams/trading-desk/PAPER_MODE.yaml`
- `teams/trading-desk/scripts/bitmart_paper_guard.py`
- `profiles/*/IDENTITY.md`
- root `config.yaml`
- `hermes-agent/hermes_cli/web_server.py`

Findings:

- Paper-mode enforcement is one of the strongest concrete safety controls in the workspace. `bitmart_paper_guard.py` actively rejects live BitMart base URLs.
- `hermes_cli/web_server.py` restricts CORS to localhost and uses an ephemeral session token for sensitive reveal endpoints.
- `hermes/SECURITY.md` correctly warns the scaffold is not production secure.
- Missing controls:
  - no operator auth layer in `hermes/apps/api` or `hermes/apps/web`
  - no end-to-end approval/veto enforcement in the product path
  - no robust secret management beyond `.env` conventions
  - no comprehensive webhook/auth verification beyond the TradingView shared secret
- Profile identities are unsafe from a governance standpoint because they blur risk/research/monitoring roles into a single aggressive trader persona.

### Tests / Quality

Summary:

- Test infrastructure exists.
- Coverage is narrow in `hermes/` and uneven in `hermes-agent/`.

Files reviewed:

- `hermes/apps/api/tests/test_health.py`
- `hermes/.github/workflows/python-ci.yml`
- `hermes/.github/workflows/node-ci.yml`
- `hermes-agent/tests/backend/*`
- `hermes-agent/tests/tools/*`
- `hermes-agent/pyproject.toml`

Execution evidence:

- `hermes`: `uv run pytest apps/api/tests` passed.
- `hermes`: `uv run ruff check .` passed.
- `hermes-agent`: targeted backend/tool test run produced `14 failed, 14 passed, 1 skipped`.

Primary observed failure pattern:

- Many `hermes-agent` tests fail because observability/storage paths attempt to instantiate PostgreSQL via SQLAlchemy `psycopg2` when `DATABASE_URL` is present.
- The project depends on `psycopg[binary]`, not `psycopg2`, so the SQLAlchemy driver assumption is mismatched.
- Because fallback only catches `OperationalError`, not driver import errors, tool/workflow tests fail before they can degrade to SQLite.

## 5. Detailed Findings by Agent

### Orchestrator & Trader

- Current files/modules: `teams/trading-desk/agents.yaml`, `profiles/orchestrator/*`, `hermes/packages/agents/.../orchestrator`, `hermes-agent/backend/workflows/graph.py`, `teams/trading-desk/skills/{workflow_routing,decision_aggregation,execution_requesting,incident_escalation}.yaml`
- Status: **Partial**
- What exists: role manifest, LiteLLM profile routing, workflow graph orchestration, paper-mode controls, notification and execution-status tool access.
- Missing: dedicated orchestrator runtime module in `hermes/`, persistent action queue, real execution-request pipeline, final-decision audit surface in Mission Control.
- Next actions: make the workflow graph the authoritative orchestrator service, expose it through a real API, and connect it to operator review and event workers.

### Market Research

- Current files/modules: `profiles/market-researcher/*`, team skill files for regime/narrative/watchlist/catalyst work, tool wrappers for prices/news/social/on-chain, provider clients for CoinGecko/CryptoPanic/NewsAPI/LunarCrush/Etherscan/Nansen/FRED.
- Status: **Partial**
- What exists: real data ingestion wrappers and context-building tools.
- Missing: dedicated research agent runtime, durable memo/research store, non-heuristic regime classification, ranked watchlist engine beyond simple synthesis.
- Next actions: formalize research outputs as persisted artifacts and connect them into the workflow graph and UI.

### Portfolio Monitor

- Current files/modules: `profiles/portfolio-monitor/*`, `get_portfolio_state`, `get_portfolio_valuation`, portfolio snapshot tables, reconciliation/drift/anomaly skill YAMLs.
- Status: **Partial**
- What exists: portfolio snapshot schema and read path.
- Missing: exchange-backed account sync, holdings reconciliation worker, realized/unrealized PnL computation against live balances, alert automation.
- Key evidence: tool warning states the portfolio adapter is not yet wired to an exchange/account backend.
- Next actions: implement snapshot ingestion from BitMart or canonical broker adapters and drive monitor outputs from that source.

### Risk Manager

- Current files/modules: `profiles/risk-manager/*`, `get_risk_approval`, vol/correlation/event/on-chain tools, risk event tables, paper-mode/team governance docs.
- Status: **Partial**
- What exists: risk-oriented toolset and approval surface.
- Missing: policy engine, concentration rules, kill switch enforcement, sizing model, operator overrides, immutable veto audit path.
- Key evidence: risk approval is currently heuristic and not tied to formal policy definitions.
- Next actions: implement a real risk policy engine and make execution impossible without policy results.

### Strategy Agent

- Current files/modules: `profiles/strategy-agent/*`, signal/setup/trade-plan skill YAMLs, indicator/on-chain/market tools, workflow graph output synthesis.
- Status: **Partial**
- What exists: tool access and workflow slots for strategy generation.
- Missing: true strategy library, backtest linkage, reusable setup registry, scoring calibration, non-placeholder candidate generation, automated retirement criteria, and pre-deployment validation loops.
- Key evidence: `list_trade_candidates` returns placeholder BTC/ETH watch candidates and skill YAMLs mark scoring as heuristic.
- Next actions: define strategy objects, candidate scanners, backtesting gates tied to stored market history, and retirement rules that disable strategies when Sharpe or win-rate degrades below operator-defined thresholds.

## 6. Detailed Findings by Shared Resource

### Market Price Feed

- Files/modules found: `hermes-agent/backend/integrations/market_data/*`, `backend/tools/get_crypto_prices.py`, `get_market_overview.py`
- Status: **Partial**
- Implemented capabilities: CoinGecko/CoinMarketCap/TwelveData wrappers, normalized price/overview outputs
- Pending work: source arbitration, caching, quality ranking, exchange-native feeds
- Config/secrets: `COINGECKO_API_KEY`, `COINMARKETCAP_API_KEY`, `TWELVEDATA_API_KEY`
- Testing gaps: no full provider failover integration test suite found

### Order Book / Depth Feed

- Files/modules found: none as a dedicated feed implementation
- Status: **Missing**
- Pending work: exchange-native order-book ingestion, normalization, storage, access tools, UI visualization

### Trades / Tape Feed

- Files/modules found: none as a dedicated live trade/tape pipeline
- Status: **Missing**
- Pending work: trade-stream adapter, persistence, replay, slippage analytics

### Technical Indicator Engine

- Files/modules found: `get_ohlcv.py`, `get_indicator_snapshot.py`, TwelveData client
- Status: **Partial**
- Implemented capabilities: OHLCV fetch, basic indicator snapshot
- Pending work: broader indicator library, deterministic local computation, test-calibrated signal logic
- Runtime risk: current indicator coverage is shallow and partly provider-dependent

### Derivatives & Funding Data

- Files/modules found: DefiLlama tools and models, some open-interest handling
- Status: **Partial**
- Implemented capabilities: DeFi/open-interest context
- Pending work: exchange funding rates, perp basis, liquidations, derivatives venue coverage
- Runtime risk: not sufficient for derivatives-aware risk controls yet

### Portfolio & Account State

- Files/modules found: `portfolio_snapshots` table, `get_portfolio_state.py`, `get_portfolio_valuation.py`
- Status: **Partial**
- Implemented capabilities: schema and read path
- Pending work: live account adapter, reconciliation, PnL, drift detection automation
- Config/secrets: exchange credentials, account IDs

### Risk Policy Engine

- Files/modules found: `get_risk_approval.py`, `hermes/packages/policies`, team risk skills
- Status: **Partial**
- Implemented capabilities: heuristic approval surface
- Pending work: policy-as-code rules, hard enforcement, kill switch, position limits, scenario controls

### Strategy Library

- Files/modules found: agent/profile YAMLs, placeholder candidates, no robust registry
- Status: **Scaffolded**
- Implemented capabilities: conceptual strategy role separation
- Pending work: actual strategy definitions, metadata, versioning, evaluation linkage, backtest promotion gates, and automated retirement policies based on rolling live performance

### Model Performance Tracking

- Files/modules found: LiteLLM route configs, profile route assignments, observability tables and service, no route-vs-outcome evaluation layer
- Status: **Missing**
- Implemented capabilities: route naming and some observability persistence exist
- Pending work: attribute decisions and downstream outcomes to specific LLM routes/models, compare decision quality over time, and use that evidence to inform routing policy changes

### News / Sentiment / Narrative Feed

- Files/modules found: CryptoPanic, NewsAPI, LunarCrush clients; related tools
- Status: **Partial**
- Implemented capabilities: normalized crypto/general/news/social inputs
- Pending work: deduping, source weighting, narrative memory, event materiality ranking

### On-Chain / Ecosystem Intelligence

- Files/modules found: Etherscan, Nansen, DefiLlama clients and tools
- Status: **Partial**
- Implemented capabilities: wallet tx history, smart-money flows, chain/protocol context
- Pending work: broader chain coverage, wallet/entity mapping, durable research memory

### Execution / Broker / Exchange Connector

- Files/modules found: `backend/integrations/execution/ccxt_client.py`, `place_order.py`, `cancel_order.py`, `get_execution_status.py`, BitMart paper guard
- Status: **Partial**
- Implemented capabilities: CCXT wrapper and order tool surface
- Pending work: complete BitMart normalization, execution worker, order-state reconciliation, fees/slippage/audit, live/paper separation across all paths
- Runtime risk: execution exists in pieces, but orchestration and governance enforcement are incomplete

### Memory / Knowledge / Research Store

- Files/modules found: session/state DBs, observability tables, agent session artifacts, no dedicated trading research store
- Status: **Partial**
- Implemented capabilities: generic Hermes memory/session mechanisms and audit persistence
- Pending work: structured research memo storage, retrieval by symbol/theme/strategy, reuse in agent workflow

## 7. Model / MCP / Integration Review

### OpenAI

- Real via LiteLLM route config and project dependencies
- Requires multiple `OPENAI_API_KEY_*` values plus LiteLLM master/client keys
- Operationally meaningful, but routed mostly through profile configs rather than agent manifest fields

### Anthropic

- Real via LiteLLM route config and project dependencies
- Requires multiple `ANTHROPIC_API_KEY_*` values
- Used heavily for orchestrator/research/risk routes

### Ollama

- Present in `hermes/.env.example` and config scaffolding
- No active trading route in current LiteLLM configs points to Ollama
- Status: **Scaffolded / not actively wired for this workspace**

### LM Studio

- Real in LiteLLM config for portfolio and strategy routes
- Requires a local LM Studio server exposing model names such as `qwen-3.5-9b` and `gemma4:e4b`
- No health/availability guard was found for local model runtime readiness

### TradingView MCP

- Referenced in root `config.yaml`
- External dependency path: local TradingView MCP server outside this workspace
- Status: **Partial and externally coupled**
- Risk: current workspace is not self-contained; MCP server versioning and startup are unmanaged here

### TradingView Webhooks

- Real FastAPI route in `hermes-agent/backend/tradingview/router.py`
- Shared-secret verification is implemented
- Stores normalized events and publishes to Redis
- This is the strongest market-event ingestion path in the workspace

### Telegram

- Real client wrapper exists
- Requires `TELEGRAM_BOT_TOKEN` and destination/chat settings
- Operational setup still manual; no delivery dashboard in `hermes/`

### Slack

- Real client wrapper exists
- Requires `SLACK_WEBHOOK_URL` or related app config
- Similar maturity to Telegram: transport exists, system-level workflow/UI does not

### Webhooks

- TradingView webhook handling exists
- Generic outbound webhook pipeline was not found
- `WEBHOOK_BASE_URL` appears in scaffold env config, but not as a mature runtime system

### Paperclip

- Present as a compatibility concept in docs, LiteLLM notes, Redis architecture, and migration summaries
- No in-repo Paperclip runtime or worker implementation found
- Status: **Conceptual compatibility, not implemented integration**

### Exchange / Broker Connectors

- CCXT/BitMart path exists
- No broad exchange abstraction or production-grade broker execution plane exists yet
- Requires `BITMART_API_KEY`, `BITMART_SECRET`, and likely account/demo environment details

## 8. Pending Configuration and Manual Setup Checklist

### Environment variables

- Configure `DATABASE_URL` for Timescale/Postgres.
- Configure `REDIS_URL` for event bus usage.
- Configure `LITELLM_MASTER_KEY` and `LITELLM_API_KEY`.
- Populate OpenAI and Anthropic upstream keys used by LiteLLM route names.
- Populate provider keys as needed: CoinGecko, CoinMarketCap, TwelveData, CryptoPanic, NewsAPI, LunarCrush, Etherscan, Nansen, FRED.
- Add BitMart demo credentials and account identifiers for paper trading.
- Add `TRADINGVIEW_WEBHOOK_SECRET` and header-name config.
- Add Telegram and/or Slack notification credentials.

### Local services

- Start Timescale/Postgres.
- Start Redis.
- Start LiteLLM with the route config.
- Start LM Studio if using local routes.
- Start Hermes Agent dashboard/API runtime.
- Start the `hermes/` API/web apps only after deciding whether they are the active product surface or just scaffolds.

### Accounts / API keys

- Create provider accounts for market/news/on-chain data sources actually intended for use.
- Provision BitMart demo environment credentials only; confirm live URLs remain blocked.
- Provision Telegram bot and Slack webhook/channel targets.

### Database / Timescale setup

- Enable Timescale extension in the target database.
- Verify schema bootstrap succeeds.
- Fix SQLAlchemy driver mismatch so fallback paths work in tests and local runs.
- Decide on migration ownership; current bootstrap-driven schema is not enough for long-term production evolution.

### Model runtime setup

- Run LiteLLM using `litellm_config.yaml`.
- Ensure route names in profiles match actual LiteLLM config.
- Verify LM Studio hosts the named local models.
- Decide whether Ollama is in scope; if so, add active routes and health checks.

### MCP setup

- Confirm the external TradingView MCP server path still exists and is runnable.
- Version or vendor that dependency if it is required for production workflows.

### Telegram / Slack setup

- Test outbound notification delivery.
- Decide escalation rules, retry policy, and failure visibility.

### Webhook setup

- Configure TradingView alerts to hit `/webhooks/tradingview`.
- Verify shared-secret header name/value match runtime config.
- Add ingress/reverse-proxy routing and TLS plan if exposing externally.

### CI/CD / deployment

- Add workspace-level CI that exercises `hermes-agent` plus `hermes/`.
- Add integrated smoke tests for Redis + DB + webhook + workflow path.
- Decide deployment topology: product app vs Hermes Agent dashboard vs both.

## 9. Code-Level TODO / FIXME / Placeholder Review

Notable placeholder/stub evidence found:

- `hermes/apps/api/src/hermes_api/api/routes/{agents,execution,risk,resources,observability}.py`: explicit placeholder responses.
- `hermes/apps/web/app/page.tsx`: “starter dashboard” and TODO text.
- `hermes/apps/web/app/mission-control/page.tsx`: explicit scaffold/TODO copy.
- `hermes/packages/agents`, `packages/resources`, `packages/tools`, `packages/policies`, `packages/observability`: mostly placeholder modules.
- `hermes-agent/backend/event_bus/workers.py`: worker scaffolds only; TODO to add BitMart execution routing worker.
- `teams/trading-desk/skills/market_regime_analysis.yaml`: placeholder logic limitation.
- `teams/trading-desk/skills/signal_scoring.yaml`: heuristic scoring limitation.
- `teams/trading-desk/skills/reconciliation.yaml`: exchange adapter not yet connected.
- `teams/trading-desk/skills/execution_requesting.yaml`: execution provider not yet wired.
- `teams/trading-desk/skills/send_structured_alert.yaml`: delivery backend described as stub until notification provider is wired, even though backend transport code now exists.
- `get_portfolio_state` tool warns portfolio adapter is not yet wired to an exchange/account backend.
- `list_trade_candidates` returns placeholder BTC/ETH candidates.

Additional repository hygiene note:

- The workspace includes many non-core profile session artifacts and large skill/reference archives under `profiles/*`. They add operational noise and can obscure the trading codebase unless clearly separated from source-of-truth trading implementation.

## 10. Risks and Technical Debt

### Architectural debt

- System is split across `hermes/`, `hermes-agent/`, `teams/`, `profiles/`, and root config without a single authoritative integration layer.
- Intended Next.js Mission Control architecture does not match the most real existing operator UI.

### Implementation debt

- Core agent logic remains heuristic or declarative in many places.
- Portfolio sync, execution routing, strategy library, risk engine, and live operator workflow are incomplete.

### Operational debt

- Local setup is multi-service and manual.
- External MCP dependency is unmanaged by the repo.
- No single integrated Compose stack validates the intended full system.

### Security debt

- No product-grade auth for operator surfaces.
- No strong secret-management system.
- Role separation is undermined by shared aggressive identity files.

### Documentation debt

- Docs are split and occasionally inconsistent with current code.
- No single runbook exists for the whole workspace.

### Testing debt

- Product repo test coverage is minimal.
- Backend tests fail due dependency/DB assumptions.
- No full end-to-end trading workflow smoke test exists.

## 11. Recommended Prioritized Action Plan

### Phase 0 — Critical Corrections

- Fix SQLAlchemy/Postgres driver mismatch in `hermes-agent/backend/db/session.py` and observability fallback paths so `psycopg` is used correctly or missing-driver errors degrade to SQLite.
- Define one authoritative runtime composition strategy for `hermes/` and `hermes-agent/`.
- Normalize `profiles/*/IDENTITY.md` to role-specific responsibilities.
- Align `teams/trading-desk/skills/*.yaml` with actual backend notification/execution capabilities.

### Phase 1 — Core Completion

- Replace placeholder FastAPI routes in `hermes/apps/api` with real service wiring into the `hermes-agent` backend.
- Replace static Mission Control pages in `hermes/apps/web` with real data fetching and operator actions.
- Implement exchange-backed portfolio snapshot ingestion and reconciliation.
- Implement a real execution worker on top of Redis Streams and CCXT/BitMart adapter.
- Replace heuristic `get_risk_approval` and `list_trade_candidates` logic with policy-backed and strategy-backed implementations.

### Phase 2 — Operational Hardening

- Add integrated Compose/dev bootstrap for Postgres/Timescale, Redis, LiteLLM, dashboard/API, and web.
- Add provider health checks, startup validation, and secrets completeness checks.
- Add notification retries, delivery visibility, and alert audit views.
- Add migration discipline for schema changes.

### Phase 3 — Production Readiness

- Add operator auth and authorization.
- Add stronger kill switches, approval gates, and paper/live segregation.
- Add end-to-end observability dashboards and runbooks.
- Add CI covering workspace integration, not only scaffold linting/tests.

### Phase 4 — Advanced Intelligence / Optimization

- Implement strategy library/versioning and evaluation loops.
- Add durable research memory and retrieval by symbol/theme/strategy.
- Add richer derivatives, order book, tape, and execution-quality analytics.
- Enable intentional smart model routing once health/cost/quality controls exist.

### Phase 7 — Continuous Improvement Loop

- Automatically retire or quarantine strategies when rolling Sharpe, win-rate, drawdown, or execution-quality metrics degrade below operator-defined thresholds.
- Run a mandatory backtesting and replay pipeline against stored market history before promoting new or materially changed strategies into paper or live workflows.
- Track decision outcomes by LiteLLM route, model, and agent role so the system can measure which model paths produce better trading decisions over time.
- Feed strategy and model performance data back into routing, strategy promotion, and review queues so the platform learns from live results rather than treating deployment as the finish line.

## 12. Production Readiness Assessment

- Local demo: **Moderate**
  - The Hermes Agent dashboard, webhook ingestion, and some provider tools can be demonstrated locally.
- Internal testing: **Early**
  - Enough exists for controlled backend validation, but the product surfaces and several workflows remain incomplete.
- Paper trading: **Early**
  - Paper-mode intent and BitMart demo guard are present, but end-to-end supervised paper trading is not yet fully wired.
- Supervised live trading: **Not Ready**
  - Risk enforcement, auth, execution hardening, reconciliation, and audit controls are insufficient.
- Autonomous live trading: **Not Ready**
  - The workspace contains too many heuristic, placeholder, and split-ownership components for safe autonomous deployment.

## 13. Appendix: File Inventory Reviewed

Important files and folders reviewed for this audit:

- Root: `docs/architecture/hermes-trader-architecture.md`, `config.yaml`, `litellm_config.yaml`, `teams/`, `profiles/`
- `hermes/`: `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `SECURITY.md`, `pyproject.toml`, `package.json`, `Makefile`, `.env.example`, `docker-compose.yml`, `.github/workflows/*`, `infrastructure/**`, `apps/api/**`, `apps/web/**`, `packages/**`
- `hermes-agent/`: `README.md`, `pyproject.toml`, `.env.example`, `docker-compose.yml`, `docker-compose.litellm.yml`, `litellm_config.yaml`, `backend/**`, `hermes_cli/web_server.py`, `web/src/**`, `tests/backend/**`, `tests/tools/**`, setup/integration docs
- Trading desk governance: `teams/trading-desk/TEAM.md`, `agents.yaml`, `PAPER_MODE.yaml`, `agent_profiles/*.yaml`, `skills/*.yaml`, `scripts/bitmart_paper_guard.py`
- Role profiles: `profiles/*/config.yaml`, `ROLE_SKILLS.yaml`, `TEAM.md`, `IDENTITY.md`, `.env`

## Terminal-Style Summary

```text
Major areas reviewed: 14
Implemented: 0
Partial: 12
Scaffolded: 2
Missing: 0

Top 10 next actions:
1. Fix the PostgreSQL driver/fallback breakage in hermes-agent DB + observability code.
2. Decide whether hermes-agent or hermes/apps/api is the authoritative backend surface.
3. Replace placeholder FastAPI routes in hermes/apps/api with real service wiring.
4. Replace static Next.js Mission Control pages with live data and operator actions.
5. Implement exchange-backed portfolio/account sync and reconciliation.
6. Add the missing execution-routing worker and end-to-end paper execution flow.
7. Replace heuristic risk approval with a real policy engine and hard veto path.
8. Replace placeholder strategy candidate generation with a real strategy library/scanner.
9. Add continuous improvement loops: backtest promotion gates, automatic strategy retirement, and route-level model outcome tracking.
10. Consolidate docs and CI around a single integrated workspace runbook with Redis + Timescale + LiteLLM + TradingView + workflow smoke coverage.
```
