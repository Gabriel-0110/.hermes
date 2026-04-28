#!/usr/bin/env bash
# Start LiteLLM proxy with .env file loaded
set -a
source "$(dirname "$0")/.env"
set +a

LITELLM_BIN=/Users/openclaw/.local/share/uv/tools/litellm/bin/litellm
CONFIG="$(dirname "$0")/litellm_config.yaml"
PORT="${LITELLM_PORT:-4000}"
LOG="$(dirname "$0")/logs/litellm.log"

echo "[$(date)] Starting LiteLLM on port $PORT" | tee -a "$LOG"
exec "$LITELLM_BIN" --config "$CONFIG" --port "$PORT" --host 0.0.0.0 >> "$LOG" 2>&1
