#!/bin/zsh
# hermes live — start all Hermes services: Docker stack + all 6 agent gateways
# Usage: hermes live [--status]
set -uo pipefail

ROOT="/Users/openclaw/.hermes"
VENV_PYTHON="$ROOT/.venv/bin/python"
COMPOSE_FILE="$ROOT/docker-compose.dev.yml"
ENV_FILE="$ROOT/.env.dev"

PROFILES=(orchestrator market-researcher portfolio-monitor risk-manager strategy-agent execution-agent)
GATEWAY_LABELS=(
  ai.hermes.gateway-orchestrator
  ai.hermes.gateway-market-researcher
  ai.hermes.gateway-portfolio-monitor
  ai.hermes.gateway-risk-manager
  ai.hermes.gateway-strategy-agent
  ai.hermes.gateway-execution-agent
)

log()  { printf '\033[0;36m[hermes live]\033[0m %s\n' "$*"; }
ok()   { printf '\033[0;32m  ✓\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m  !\033[0m %s\n' "$*"; }
err()  { printf '\033[0;31m  ✗\033[0m %s\n' "$*" >&2; }

# ── 1. Docker stack ───────────────────────────────────────────────────────────
log "Starting Docker Compose stack..."
if ! command -v docker &>/dev/null; then
  err "docker not found — is Docker Desktop installed?"
  exit 1
fi

# Launch Docker Desktop if daemon not reachable
if ! docker info &>/dev/null 2>&1; then
  warn "Docker daemon not running — launching Docker Desktop..."
  open -a Docker 2>/dev/null || true
  log "Waiting for Docker (up to 60s)..."
  for i in {1..60}; do
    sleep 1
    docker info &>/dev/null 2>&1 && break
    (( i == 60 )) && { err "Docker failed to start within 60s"; exit 1; }
  done
fi

cd "$ROOT"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --wait 2>&1 | tail -5
ok "Docker Compose stack is up"

# ── 2. Agent gateways (via launchd) ──────────────────────────────────────────
log "Starting agent gateways..."
for label in "${GATEWAY_LABELS[@]}"; do
  pid=$(launchctl list | awk -v l="$label" '$3==l {print $1}')
  if [[ "$pid" != "-" && -n "$pid" ]]; then
    ok "$label (PID $pid)"
  else
    # Try to kickstart (load) the agent
    launchctl kickstart "gui/$(id -u)/$label" 2>/dev/null || \
      launchctl load -w "$HOME/Library/LaunchAgents/${label}.plist" 2>/dev/null || \
      warn "$label — could not start (plist may be missing)"
    sleep 1
    pid=$(launchctl list | awk -v l="$label" '$3==l {print $1}')
    if [[ "$pid" != "-" && -n "$pid" ]]; then
      ok "$label (PID $pid)"
    else
      warn "$label — still not running after kickstart"
    fi
  fi
done

# ── 3. Status summary ─────────────────────────────────────────────────────────
echo ""
log "── Docker services ──────────────────────────────────────────────────────"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null

echo ""
log "── Agent gateways ───────────────────────────────────────────────────────"
for i in {1..${#PROFILES[@]}}; do
  profile="${PROFILES[$i]}"
  label="${GATEWAY_LABELS[$i]}"
  pid=$(launchctl list | awk -v l="$label" '$3==l {print $1}')
  if [[ "$pid" != "-" && -n "$pid" ]]; then
    printf '  \033[0;32m✓\033[0m %-20s PID %s\n' "$profile" "$pid"
  else
    printf '  \033[0;31m✗\033[0m %-20s NOT RUNNING\n' "$profile"
  fi
done

echo ""
log "── Cron scheduler ───────────────────────────────────────────────────────"
"$VENV_PYTHON" -m hermes_cli.main --profile orchestrator cron status 2>/dev/null | grep -v "^$" | head -5 || warn "Could not check cron status"

echo ""
ok "Hermes trading desk is LIVE"
