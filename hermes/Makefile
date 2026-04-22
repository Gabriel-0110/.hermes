SHELL := /bin/sh
HERMES_AGENT_DIR := ../hermes-agent

.PHONY: setup dev api web test lint format up down logs backend-infra backend-dashboard backend-litellm workspace-dev-up workspace-dev-down workspace-dev-check workspace-dev-logs

setup:
	uv sync
	npm install

dev:
	@printf "Run API and web in separate terminals using 'make api' and 'make web', or use 'make up' for Docker Compose.\n"

api:
	uv run uvicorn hermes_api.main:app --reload --app-dir apps/api/src --host 0.0.0.0 --port 8000

web:
	npm run dev --workspace @hermes/web

test:
	uv run pytest apps/api/tests

lint:
	uv run ruff check .
	npm run lint --workspace @hermes/web

format:
	uv run ruff format .
	npm run format

up:
	docker compose up --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f

backend-infra:
	cd $(HERMES_AGENT_DIR) && docker compose up -d redis timescaledb

backend-dashboard:
	cd $(HERMES_AGENT_DIR) && uv sync && uv run python -m hermes_cli.main dashboard --host 0.0.0.0 --port 9119

backend-litellm:
	cd $(HERMES_AGENT_DIR) && docker compose -f docker-compose.litellm.yml up -d

workspace-dev-up:
	cd .. && $(MAKE) dev-up

workspace-dev-down:
	cd .. && $(MAKE) dev-down

workspace-dev-check:
	cd .. && $(MAKE) dev-check

workspace-dev-logs:
	cd .. && $(MAKE) dev-logs
