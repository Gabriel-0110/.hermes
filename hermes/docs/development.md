# Development

## Local Setup

1. Copy `.env.example` to `.env`.
2. Install Python and Node prerequisites.
3. Run `make setup`.
4. Start the API with `make api` and the web app with `make web`, or use `make up`.

## Tooling

- Python dependency and task runner: `uv`
- Python lint and format: `ruff`
- Python tests: `pytest`
- Frontend framework: Next.js with TypeScript
- Frontend formatting: Prettier
- Pre-commit hooks: `.pre-commit-config.yaml`

## Environment Variable Overview

### Model providers

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `OLLAMA_BASE_URL`
- `LM_STUDIO_BASE_URL`

### Database

- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DB`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `DATABASE_URL`

### Channels and webhooks

- `TELEGRAM_BOT_TOKEN`
- `SLACK_BOT_TOKEN`
- `SLACK_SIGNING_SECRET`
- `WEBHOOK_BASE_URL`

### Runtime

- `APP_ENV`
- `LOG_LEVEL`

## Folder Structure

- `apps/` contains deployable applications
- `packages/` contains reusable Python package boundaries
- `infrastructure/` contains local runtime support assets
- `docs/` contains operator and developer documentation

## Future Notes

- add database migrations once schemas stabilize
- add queue workers when workflows become long-running
- keep execution paths behind feature flags or explicit runtime modes
