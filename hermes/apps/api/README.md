# Hermes API

This FastAPI service is the backend entrypoint for Hermes. In the scaffold phase it exposes:

- a root metadata endpoint
- a health check
- versioned bridge routes for agents, execution, risk, resources, portfolio, and observability

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
- move reusable business logic into `packages/` over time
- treat risk and execution routes as high-scrutiny surfaces
- treat `/resources` as a descriptive capability catalog unless and until a
	dedicated operational health surface exists
