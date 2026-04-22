# Hermes Runtime Consolidation Plan

## Problem

The workspace currently has two overlapping runtime layers:

- `hermes/`
  - intended product repo
  - Next.js Mission Control UI
  - FastAPI product API
  - shared package boundaries
  - mostly scaffolded
- `hermes-agent/`
  - actual backend-heavy runtime
  - TradingView ingestion
  - shared persistence
  - Redis event bus
  - observability APIs
  - provider integrations
  - typed trading workflow graph
  - operator dashboard

This split creates four immediate problems:

1. There is no single authoritative backend surface.
2. Product docs point at `hermes/`, but real backend capability lives in `hermes-agent/`.
3. The Next.js Mission Control app is not wired to the backend that actually exists.
4. Local bootstrap and deployment are ambiguous because the two repos define different stacks.

## Phase 0 Goal

Create one clear runtime contract:

- `hermes-agent/` remains the backend system of record for now.
- `hermes/` becomes the product shell and integration surface.
- `hermes/apps/api` should stop inventing placeholder domain models and instead mount or proxy real backend services from `hermes-agent`.

This is the fastest path because it reuses real code instead of rewriting backend functionality into the scaffold.

## Recommended Target Shape

### Backend ownership

`hermes-agent/` should own:

- provider clients
- TradingView ingestion
- shared DB schema and repositories
- Redis event bus
- workflow graph and orchestration logic
- notifications
- observability service
- execution adapters

`hermes/` should own:

- public product API surface
- Mission Control UI
- operator-focused workflows
- product-level auth and access control
- deployment packaging for the integrated app

### API strategy

Short term:

- expose `hermes-agent` backend capabilities behind stable API routes
- have `hermes/apps/api` call those services directly as Python imports where feasible
- only use HTTP proxying when process boundaries are required

Medium term:

- extract a backend service package from `hermes-agent` that `hermes/apps/api` imports directly
- eliminate duplicate route/domain scaffolds in `hermes/apps/api`

### Frontend strategy

Short term:

- wire `hermes/apps/web` to real endpoints for:
  - observability
  - recent TradingView alerts
  - workflow runs
  - notifications
  - execution status
  - portfolio state

Medium term:

- decide whether to:
  - migrate the useful `hermes-agent/web` operator pages into Next.js, or
  - treat `hermes-agent/web` as an internal admin console and keep `hermes/apps/web` as the main operator product

Recommendation:

- migrate the useful data surfaces, not the full Vite app wholesale
- keep one operator UI long term: `hermes/apps/web`

## Concrete Integration Sequence

### Step 1

Make `hermes-agent` importable from `hermes/apps/api`.

Options:

- add a workspace packaging strategy so `hermes-agent` is installed as a dependency
- or extract `backend/` into a shared package consumed by both repos

Preferred direction:

- extract the reusable backend layer into a shared internal package once route wiring is proven

### Step 2

Replace placeholder API routes in `hermes/apps/api/src/hermes_api/api/routes/`:

- `agents.py`
- `execution.py`
- `risk.py`
- `resources.py`
- `observability.py`

Initial real endpoints should expose:

- workflow status
- recent TradingView alerts
- recent internal events
- portfolio snapshot
- risk approval status
- notification delivery history
- execution status

### Step 3

Define a single environment contract.

Current sprawl:

- `hermes/.env.example`
- `hermes-agent/.env.example`
- root `config.yaml`
- root `litellm_config.yaml`
- `profiles/*/config.yaml`

Needed outcome:

- one operator-facing setup doc
- one canonical env var matrix
- one precedence rule for profile config vs `.env` vs root runtime config

### Step 4

Unify local runtime startup.

Create one integrated stack that starts:

- Timescale/Postgres
- Redis
- LiteLLM
- Hermes backend runtime
- Hermes web UI

This should replace the current ambiguity between:

- `hermes/docker-compose.yml`
- `hermes-agent/docker-compose.yml`
- `hermes-agent/docker-compose.litellm.yml`

### Step 5

Port real operator workflows into Mission Control.

Priority UI slices:

- alert intake and signal history
- workflow run history
- execution approvals and state
- portfolio state and drift
- notification delivery
- system errors and failures

## Immediate Code Targets

These are the first files to change after Phase 0 fixes:

- `hermes/apps/api/src/hermes_api/api/routes/observability.py`
- `hermes/apps/api/src/hermes_api/api/routes/execution.py`
- `hermes/apps/api/src/hermes_api/api/routes/risk.py`
- `hermes/apps/api/src/hermes_api/api/routes/resources.py`
- `hermes/apps/web/app/mission-control/page.tsx`
- `hermes/apps/web/app/page.tsx`

Backend sources to reuse:

- `hermes-agent/backend/observability/service.py`
- `hermes-agent/backend/tradingview/service.py`
- `hermes-agent/backend/tradingview/store.py`
- `hermes-agent/backend/workflows/graph.py`
- `hermes-agent/backend/tools/*.py`
- `hermes-agent/hermes_cli/web_server.py`

## Decision Rules

- Do not re-implement backend logic in `hermes/` if equivalent logic already exists in `hermes-agent`.
- Do not keep parallel operator UIs long term.
- Do not add more placeholder domain modules in `hermes/apps/api`.
- Treat `hermes-agent` as the current source of backend truth until extracted into shared packages.

## Success Criteria

Phase 0 consolidation is complete when:

- `hermes/apps/api` serves at least a minimal set of real backend-backed routes
- `hermes/apps/web` renders live data from those routes
- local startup has one documented path
- the workspace has one authoritative backend surface
- the audit no longer needs to describe the system as split-state
