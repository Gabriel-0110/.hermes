#!/bin/zsh
set -euo pipefail

ROOT="/Users/openclaw/.hermes"
COMPOSE_FILE="$ROOT/docker-compose.dev.yml"
ENV_FILE="$ROOT/.env.dev"
DOCKER_BIN="$(command -v docker)"
SOCKET_PATH="${HOME}/.docker/run/docker.sock"

log() { echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $*"; }

if [[ -z "$DOCKER_BIN" ]]; then
  log "ERROR: docker not found on PATH" >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  # Open Docker Desktop if not already running (safe — open is idempotent).
  if ! [[ -S "$SOCKET_PATH" ]]; then
    open -a Docker >/dev/null 2>&1 || true
    log "Docker Desktop launched."
  fi
fi

# Wait for the Docker socket to appear (VM fully initialized).
# Checking the socket file is more reliable than 'docker info', which can
# return client-only data before the daemon VM is ready.
max_socket_attempts=72  # 72 x 5s = 6 minutes
socket_attempt=1
log "Waiting for Docker socket at ${SOCKET_PATH}..."
until [[ -S "$SOCKET_PATH" ]]; do
  if (( socket_attempt >= max_socket_attempts )); then
    log "ERROR: Docker socket did not appear within 6 minutes." >&2
    exit 1
  fi
  socket_attempt=$((socket_attempt + 1))
  sleep 5
done
log "Docker ready (attempt ${socket_attempt})."

cd "$ROOT"
log "Starting Docker Compose stack..."
exec "$DOCKER_BIN" compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --wait
