#!/bin/zsh
set -euo pipefail

ROOT="/Users/openclaw/.hermes"
COMPOSE_FILE="$ROOT/docker-compose.dev.yml"
ENV_FILE="$ROOT/.env.dev"
DOCKER_BIN="$(command -v docker)"

if [[ -z "$DOCKER_BIN" ]]; then
  echo "docker not found on PATH" >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  if ! "$DOCKER_BIN" info >/dev/null 2>&1; then
    open -a Docker >/dev/null 2>&1 || true
  fi
fi

# Wait for Docker Desktop / daemon to become available after login.
max_attempts=60
attempt=1
until "$DOCKER_BIN" info >/dev/null 2>&1; do
  if (( attempt >= max_attempts )); then
    echo "docker daemon did not become ready in time" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep 5
done

cd "$ROOT"
exec "$DOCKER_BIN" compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --wait
