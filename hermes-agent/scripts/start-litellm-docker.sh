#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
ENV_FILE="${HERMES_ENV_FILE:-$HERMES_HOME/.env}"
CONFIG_PATH="${LITELLM_CONFIG_PATH:-$ROOT_DIR/litellm_config.yaml}"
if [[ -z "${LITELLM_CONFIG_PATH:-}" && -f "$HERMES_HOME/litellm_config.yaml" ]]; then
  CONFIG_PATH="$HERMES_HOME/litellm_config.yaml"
fi

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

load_env_file "$ENV_FILE"

LITELLM_DB_URL="${LITELLM_DATABASE_URL:-${DATABASE_URL:-}}"

derive_docker_database_url() {
  local raw_url="$1"
  python3 - "$raw_url" <<'PY'
from urllib.parse import urlsplit, urlunsplit
import sys

parts = urlsplit(sys.argv[1])
hostname = parts.hostname or ""
if hostname in {"localhost", "127.0.0.1", "::1"}:
    netloc = parts.netloc.replace(hostname, "host.docker.internal", 1)
    print(urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)))
else:
    print(sys.argv[1])
PY
}

if [[ -z "${LITELLM_DB_URL:-}" ]]; then
  echo "LITELLM_DATABASE_URL or DATABASE_URL is required for LiteLLM virtual keys." >&2
  echo "Set it in your environment or ~/.hermes/.env before starting the Docker proxy." >&2
  exit 1
fi

if [[ -z "${LITELLM_MASTER_KEY:-}" ]]; then
  echo "LITELLM_MASTER_KEY is required for LiteLLM virtual keys." >&2
  exit 1
fi

if [[ "${LITELLM_MASTER_KEY}" != sk-* ]]; then
  echo "LITELLM_MASTER_KEY must start with 'sk-' for LiteLLM virtual keys." >&2
  exit 1
fi

if [[ "${LITELLM_DB_URL}" == postgresql+* ]]; then
  echo "LiteLLM database URL must use a standard Postgres URL (postgresql://...), not SQLAlchemy driver syntax." >&2
  exit 1
fi

LITELLM_DOCKER_DATABASE_URL="${LITELLM_DOCKER_DATABASE_URL:-$(derive_docker_database_url "$LITELLM_DB_URL")}"
export LITELLM_DOCKER_DATABASE_URL

ARGS=("$@")
if [[ ${#ARGS[@]} -eq 0 ]]; then
  ARGS=(up litellm)
fi

LITELLM_CONFIG_PATH="$CONFIG_PATH" exec docker compose --env-file "$ENV_FILE" -f docker-compose.litellm.yml "${ARGS[@]}"
