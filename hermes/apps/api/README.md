# Hermes API

This FastAPI service is the product/API bridge for Hermes. It is not the
runtime source of truth for trading logic.

In the current split architecture:

- `hermes-agent/backend` owns workflows, typed proposal/risk/execution state,
  approvals, observability, and canonical portfolio state
- `hermes/apps/api` exposes a product-facing bridge over that runtime

The bridge currently exposes:

- a root metadata endpoint
- a health check
- versioned bridge routes for agents, execution, risk, resources, portfolio, and observability

Current control-path coverage in the bridge includes:

- proposal evaluation and submission
- execution safety state
- approval queue actions
- position monitor and portfolio snapshot views
- observability and timeline readouts

## Local Run

```bash
uv run uvicorn hermes_api.main:app --reload --app-dir apps/api/src
```

## Operator auth for mutating routes

Mutating/operator endpoints (kill switch, portfolio sync, order placement,
approval actions) now fail closed unless one of these is true:

- `HERMES_API_KEY` is set and the caller sends `Authorization: Bearer <key>`
- `HERMES_API_DEV_BYPASS_AUTH=true` is set explicitly in a development/test
	environment

The canonical integrated local stack (`make dev-up` from the workspace root)
uses `.env.dev` / `.env.dev.example` to set that bypass explicitly for the
local-only happy path. The compose file itself no longer enables it silently.
Repo-local and deployed runs should prefer `HERMES_API_KEY`.

## Design Notes

- keep API boundaries thin
- keep `hermes-agent/backend` as the runtime source of truth
- treat risk and execution routes as high-scrutiny surfaces
- preserve current route families rather than duplicating bridge surfaces
- treat `/resources` as a descriptive capability catalog unless and until a
	dedicated operational health surface exists
