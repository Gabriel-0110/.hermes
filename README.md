# Hermes Workspace

This repository is a **workspace-level container** for a split Hermes stack.
It exists to keep the product shell, the current backend runtime, workspace
docs, shared dev tooling, and operator-facing configuration in one place while
remaining safe to publish to GitHub.

The important top-level idea is:

- `hermes/` is the product shell and long-term monorepo target
- `hermes-agent/` is the current backend/runtime-heavy implementation
- the repository root provides the **workspace glue**: docs, integrated local
  development commands, shared Compose setup, helper scripts, and safe config
  templates

If someone lands on this repository first, this README should be enough to
understand what the workspace contains, how to run it locally, and what is
intentionally excluded from source control.

## What This Repo Contains

- `hermes/`
  Product-facing codebase. Contains the FastAPI bridge, the Mission Control web
  app, product docs, and the intended long-term architecture boundaries.

- `hermes-agent/`
  The current backend/runtime-heavy implementation. Contains the agent runtime,
  dashboard/backend, integrations, workflow engine, TradingView ingestion,
  observability, notifications, cron support, and the broader Hermes Agent
  codebase.

- `docs/`
  Workspace-level documentation that explains how the split stack is composed
  and how to run the integrated local development flow.

- `scripts/`
  Root helper scripts that belong to the workspace rather than to either
  subproject individually.

- `docker-compose.dev.yml`
  The unified local development stack that brings up the main services in one
  dependency-ordered flow.

- `Makefile`
  The canonical workspace-level developer entrypoint for starting, checking,
  and stopping the integrated stack.

- `.env.dev.example`
  Safe template for local development environment variables.

- `litellm_config.yaml`
  Workspace-level LiteLLM route map used by the workspace runtime/docs. This is
  intentionally separate from ignored live credentials and local `.env` files.

## What This Repo Does Not Contain

This repository intentionally excludes local runtime state and anything that
would make a GitHub upload unsafe or noisy.

Examples of excluded content:

- real secrets and `.env` files
- auth/session/cache artifacts
- local databases and Redis dumps
- logs, screenshots, temp images, and generated runtime output
- machine-specific config and editor state
- local profiles, team state, cron output, and other live workspace data
- dependency/build outputs like `node_modules/`, `.venv/`, `.next/`, and
  similar generated directories

The root `.gitignore` is set up so the repository captures the **workspace
shape**, not the live machine state.

## Workspace Layout

```text
.hermes/
├── hermes/                 # product shell / API bridge / web app
├── hermes-agent/           # current backend/runtime-heavy implementation
├── docs/                   # workspace docs
├── scripts/                # workspace helper scripts
├── docker-compose.dev.yml  # integrated local stack
├── Makefile                # root entrypoint
├── .env.dev.example        # local dev env template
└── litellm_config.yaml     # workspace LiteLLM route config
```

## Canonical Local Development Flow

The **main workspace entrypoint** is the repository root.

Use these commands first:

```bash
make dev-help
make dev-up
make dev-check
```

Those commands use the root [Makefile](Makefile) and
[docker-compose.dev.yml](docker-compose.dev.yml) to
bring up the integrated stack in dependency order.

The intended startup order is:

1. TimescaleDB
2. Redis
3. LiteLLM
4. Hermes Agent dashboard/backend
5. Hermes product API bridge
6. Hermes product web app

Additional useful commands:

```bash
make dev-logs
make dev-ps
make dev-down
```

More detail lives in:

- [docs/workspace/LOCAL_DEV.md](docs/workspace/LOCAL_DEV.md)
- [docs/workspace/GATEWAY_RUNTIME.md](docs/workspace/GATEWAY_RUNTIME.md)
- [hermes/README.md](hermes/README.md)
- [hermes-agent/README.md](hermes-agent/README.md)

## How To Read The Two Main Subprojects

### `hermes/`

Treat `hermes/` as:

- the product shell
- the API bridge layer
- the operator-facing web surface
- the long-term monorepo target architecture

It contains the product docs and the future package boundaries, but not all of
that architecture is fully realized yet.

### `hermes-agent/`

Treat `hermes-agent/` as:

- the current backend source of truth for many real runtime capabilities
- the place where integrations, workflows, observability, TradingView
  ingestion, tool wiring, and runtime-heavy logic currently live

In practical terms, a lot of the “real system behavior” is still here even when
the long-term product direction points toward `hermes/`.

## LiteLLM and Model Routing

The workspace includes a root
[litellm_config.yaml](litellm_config.yaml) because the
workspace runtime and docs treat LiteLLM as an important shared integration
point.

This file is safe to publish because it maps **route names** and environment
variable references, not live secrets.

Live keys remain excluded and should come from local env files or runtime
environment configuration.

Related docs:

- [docs/workspace/LITELLM_VIRTUAL_KEYS.md](docs/workspace/LITELLM_VIRTUAL_KEYS.md)
- [hermes-agent/litellm_config.yaml](hermes-agent/litellm_config.yaml)

## Files You May See Locally But Should Ignore

If you are working in a live Hermes home, you may still see local-only files in
the root such as:

- `auth.json`
- `auth.lock`
- `config.yaml`
- `gateway_state.json`
- `feishu_seen_message_ids.json`
- `models_dev_cache.json`
- `processes.json`
- `.env`
- `.env.dev`

These are **runtime or machine-local files**, not repository content. They are
intentionally ignored by Git and should stay that way.

When the active Hermes profile is a named profile like `orchestrator`, the
authoritative messaging runtime state is the profile-scoped file under
`profiles/<name>/gateway_state.json`; the root-level `gateway_state.json` may
be stale and should not be treated as authoritative.

For example:

- `auth.lock` is just a local lock file
- `feishu_seen_message_ids.json` is tiny deduplication/runtime state

Neither belongs in a publishable repository snapshot.

## Publishing Boundary

This workspace is being prepared for GitHub as a **clean, source-oriented
snapshot**, not as a dump of a live `~/.hermes` home directory.

That means:

- publish source, docs, templates, and reproducible setup
- exclude identity files, local memory, sessions, auth state, caches, and live
  operator data
- keep root-level content focused on explaining and operating the workspace

## Before Pushing

Use the checklist here:

- [docs/workspace/GITHUB_UPLOAD_CHECKLIST.md](docs/workspace/GITHUB_UPLOAD_CHECKLIST.md)

Recommended final checks:

```bash
git status --short
git add -n .
```

Confirm that only intended source files, docs, templates, and workspace-level
configuration are included.

## Notes

- `hermes-agent/` is included as normal source files, not as a submodule.
- The repository root is a **workspace coordinator**, not a third full
  application.
- If a file at the root is not helping explain, configure, or run the workspace,
  it probably should not be tracked.
