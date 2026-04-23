SHELL := /bin/sh

DEV_ENV_FILE ?= .env.dev
DEV_COMPOSE_FILE ?= docker-compose.dev.yml
DEV_COMPOSE := docker compose -f $(DEV_COMPOSE_FILE) --env-file $(DEV_ENV_FILE)
LEGACY_PRODUCT_COMPOSE := docker compose -f hermes/docker-compose.yml --project-directory hermes
LEGACY_AGENT_COMPOSE := docker compose -f hermes-agent/docker-compose.yml --project-directory hermes-agent
LEGACY_LITELLM_COMPOSE := docker compose -f hermes-agent/docker-compose.litellm.yml --project-directory hermes-agent
LEGACY_CONTAINER_NAMES := hermes-postgres hermes-api hermes-web hermes-redis hermes-timescaledb hermes-litellm hermes-agent-hermes-1 hermes-dashboard

.PHONY: dev-bootstrap dev-help dev-up dev-down dev-logs dev-ps dev-check dev-clean-legacy

dev-help:
	@echo "Hermes local development"
	@echo ""
	@echo "Canonical happy path (workspace root):"
	@echo "  make dev-up      # start backend infra + LiteLLM + dashboard + API + web"
	@echo "  make dev-check   # verify health endpoints and expected ports"
	@echo "  make dev-logs    # follow container logs"
	@echo "  make dev-down    # stop the unified stack"
	@echo ""
	@echo "Reference: docs/workspace/LOCAL_DEV.md"

dev-bootstrap:
	@if [ ! -f "$(DEV_ENV_FILE)" ]; then \
		cp .env.dev.example $(DEV_ENV_FILE); \
		echo "Created $(DEV_ENV_FILE) from .env.dev.example"; \
		echo "Review $(DEV_ENV_FILE) before relying on external providers or notification channels."; \
	fi

dev-clean-legacy:
	@$(LEGACY_PRODUCT_COMPOSE) down --remove-orphans >/dev/null 2>&1 || true
	@$(LEGACY_AGENT_COMPOSE) down --remove-orphans >/dev/null 2>&1 || true
	@$(LEGACY_LITELLM_COMPOSE) down --remove-orphans >/dev/null 2>&1 || true
	@for name in $(LEGACY_CONTAINER_NAMES); do \
		id=$$(docker ps -aq -f name="^$$name$$" 2>/dev/null || true); \
		if [ -n "$$id" ]; then docker rm -f $$id >/dev/null 2>&1 || true; fi; \
	done

dev-up: dev-bootstrap dev-clean-legacy
	$(DEV_COMPOSE) up -d --build --wait
	@echo "Hermes local dev stack is starting. Legacy split-stack containers were shut down first. Run 'make dev-check' for the canonical health verification, or 'make dev-help' for the happy path summary."

dev-down:
	$(DEV_COMPOSE) down --remove-orphans

dev-logs:
	$(DEV_COMPOSE) logs -f

dev-ps:
	$(DEV_COMPOSE) ps

dev-check:
	@set -eu; \
	$(DEV_COMPOSE) ps; \
	echo ""; \
	echo "HTTP health checks:"; \
	for target in \
		"LiteLLM|http://127.0.0.1:$${LITELLM_PORT:-4000}/health/liveliness" \
		"Dashboard|http://127.0.0.1:$${HERMES_DASHBOARD_PORT:-9119}/api/status" \
		"API|http://127.0.0.1:$${HERMES_API_PORT:-8000}/api/v1/healthz" \
		"Web|http://127.0.0.1:$${HERMES_WEB_PORT:-3000}" \
		"Mission Control|http://127.0.0.1:$${HERMES_MISSION_CONTROL_PORT:-3100}"; \
	do \
		name=$${target%%|*}; \
		url=$${target#*|}; \
		code=$$(curl -s -o /tmp/hermes-dev-check.$$ -w '%{http_code}' "$$url" || true); \
		printf '  %-10s %s %s\n' "$$name" "$$code" "$$url"; \
		rm -f /tmp/hermes-dev-check.$$; \
	done; \
	echo ""; \
	echo "Expected host ports:"; \
	echo "  TimescaleDB  $${HERMES_TIMESCALE_PORT:-5433}"; \
	echo "  Redis        $${HERMES_REDIS_PORT:-6379}"; \
	echo "  LiteLLM      $${LITELLM_PORT:-4000}"; \
	echo "  Dashboard    $${HERMES_DASHBOARD_PORT:-9119}"; \
	echo "  API          $${HERMES_API_PORT:-8000}"; \
	echo "  Web          $${HERMES_WEB_PORT:-3000}"; \
	echo "  Mission Ctrl $${HERMES_MISSION_CONTROL_PORT:-3100}"