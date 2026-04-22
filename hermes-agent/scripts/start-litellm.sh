#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
DEFAULT_CONFIG_PATH="$ROOT_DIR/litellm_config.yaml"
if [[ -f "$HERMES_HOME/litellm_config.yaml" ]]; then
  DEFAULT_CONFIG_PATH="$HERMES_HOME/litellm_config.yaml"
fi
CONFIG_PATH="${LITELLM_CONFIG_PATH:-${LITELLM_CONFIG:-$DEFAULT_CONFIG_PATH}}"
PORT="${LITELLM_PORT:-4000}"

load_env_file() {
  local env_path="$1"
  [[ -f "$env_path" ]] || return 0

  while IFS= read -r -d '' line; do
    export "$line"
  done < <(python3 - "$env_path" <<'PY'
from pathlib import Path
import sys

for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    stripped = raw.strip()
    if not stripped or stripped.startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key or key.startswith("#"):
        continue
    sys.stdout.buffer.write(f"{key}={value.strip()}".encode())
    sys.stdout.buffer.write(b"\0")
PY
)
}

load_env_file "${HERMES_ENV_FILE:-$HERMES_HOME/.env}"

LITELLM_DB_URL="${LITELLM_DATABASE_URL:-${DATABASE_URL:-}}"

if [[ -n "${LITELLM_DB_URL:-}" ]]; then
  if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
    echo "LiteLLM database URL is set, but LITELLM_MASTER_KEY is missing." >&2
    echo "Virtual keys require an admin key that starts with 'sk-'." >&2
    exit 1
  fi

  if [[ "${LITELLM_MASTER_KEY}" != sk-* ]]; then
    echo "LITELLM_MASTER_KEY must start with 'sk-' for LiteLLM virtual keys." >&2
    exit 1
  fi

  if [[ "${LITELLM_DB_URL}" == postgresql+* ]]; then
    echo "LiteLLM database URL uses SQLAlchemy driver syntax (${LITELLM_DB_URL%%://*}://...)." >&2
    echo "LiteLLM expects a standard Postgres URL such as postgresql://user:pass@host:5432/dbname." >&2
    exit 1
  fi

  if ! python3 - <<'PY' >/dev/null 2>&1
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("prisma") else 1)
PY
  then
    echo "LiteLLM local CLI is missing the database runtime dependency 'prisma'." >&2
    echo "Use scripts/start-litellm-docker.sh for the DB-backed virtual-key setup," >&2
    echo "or reinstall LiteLLM with the database runtime extras." >&2
    exit 1
  fi
elif [[ "${LITELLM_REQUIRE_DB:-0}" == "1" ]]; then
  echo "LITELLM_REQUIRE_DB=1, but LITELLM_DATABASE_URL / DATABASE_URL is not set." >&2
  exit 1
fi

if ! command -v litellm >/dev/null 2>&1; then
  echo "litellm CLI not found. Install it with: uv tool install 'litellm[proxy]'" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "LiteLLM config not found at $CONFIG_PATH" >&2
  exit 1
fi

EXTRA_ARGS=()
if [[ -n "${LITELLM_EXTRA_ARGS:-}" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS=(${LITELLM_EXTRA_ARGS})
fi

exec litellm --config "$CONFIG_PATH" --port "$PORT" "${EXTRA_ARGS[@]}"
