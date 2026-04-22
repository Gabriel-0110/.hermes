#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/generate-litellm-key.sh ROLE [--route ROUTE] [--user-id ID] [--team-id ID] [--write-env /path/to/.env]

Examples:
  scripts/generate-litellm-key.sh orchestrator
  scripts/generate-litellm-key.sh research --user-id paperclip-research
  scripts/generate-litellm-key.sh risk-manager --write-env ~/.hermes/profiles/risk-manager/.env

Environment:
  LITELLM_API_BASE           LiteLLM base URL (default: http://localhost:4000)
  LITELLM_MASTER_KEY         Admin key for /key/generate (required, must start with sk-)
  LITELLM_KEY_DURATION       Default key lifetime (default: 30d)
  LITELLM_KEY_MAX_BUDGET     Optional budget to attach to the generated key
  LITELLM_KEY_TPM_LIMIT      Optional TPM limit
  LITELLM_KEY_RPM_LIMIT      Optional RPM limit
EOF
  exit 1
}

ROLE="${1:-}"
if [[ -z "$ROLE" ]]; then
  usage
fi
shift || true

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

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

ROUTE=""
WRITE_ENV=""
USER_ID=""
TEAM_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --route)
      ROUTE="${2:-}"
      shift 2
      ;;
    --user-id)
      USER_ID="${2:-}"
      shift 2
      ;;
    --team-id)
      TEAM_ID="${2:-}"
      shift 2
      ;;
    --write-env)
      WRITE_ENV="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      ;;
  esac
done

if [[ -z "$ROUTE" ]]; then
  case "$ROLE" in
    orchestrator) ROUTE="orchestrator-default" ;;
    market-researcher|research) ROUTE="research-strong" ;;
    portfolio-monitor|portfolio) ROUTE="risk-stable" ;;
    risk-manager|risk) ROUTE="risk-stable" ;;
    strategy-agent|strategy) ROUTE="strategy-default" ;;
    local) ROUTE="local-fast" ;;
    *)
      echo "Could not infer a route for role '$ROLE'. Pass --route explicitly." >&2
      exit 1
      ;;
  esac
fi

API_BASE="${LITELLM_API_BASE:-http://localhost:4000}"
API_BASE="${API_BASE%/}"
MASTER_KEY="${LITELLM_MASTER_KEY:-}"
if [[ -z "$MASTER_KEY" ]]; then
  echo "LITELLM_MASTER_KEY is required." >&2
  exit 1
fi

if [[ "$MASTER_KEY" != sk-* ]]; then
  echo "LITELLM_MASTER_KEY must start with 'sk-'." >&2
  exit 1
fi

KEY_DURATION="${LITELLM_KEY_DURATION:-30d}"

REQUEST_JSON="$(ROLE="$ROLE" ROUTE="$ROUTE" KEY_DURATION="$KEY_DURATION" USER_ID="$USER_ID" TEAM_ID="$TEAM_ID" python3 - <<'PY'
import json
import os

role = os.environ["ROLE"]
route = os.environ["ROUTE"]
payload = {
    "models": [route],
    "duration": os.environ.get("KEY_DURATION", "30d"),
    "key_alias": f"hermes-{role}",
    "metadata": {
        "hermes_role": role,
        "hermes_route": route,
        "generated_by": "scripts/generate-litellm-key.sh",
    },
}

user_id = os.environ.get("USER_ID", "").strip()
team_id = os.environ.get("TEAM_ID", "").strip()
if user_id:
    payload["user_id"] = user_id
if team_id:
    payload["team_id"] = team_id

if os.environ.get("LITELLM_KEY_MAX_BUDGET"):
    payload["max_budget"] = float(os.environ["LITELLM_KEY_MAX_BUDGET"])
if os.environ.get("LITELLM_KEY_TPM_LIMIT"):
    payload["tpm_limit"] = int(os.environ["LITELLM_KEY_TPM_LIMIT"])
if os.environ.get("LITELLM_KEY_RPM_LIMIT"):
    payload["rpm_limit"] = int(os.environ["LITELLM_KEY_RPM_LIMIT"])

print(json.dumps(payload))
PY
)"

RESPONSE="$(ROLE="$ROLE" ROUTE="$ROUTE" KEY_DURATION="$KEY_DURATION" \
  curl --silent --show-error --fail \
    -X POST "$API_BASE/key/generate" \
    -H "Authorization: Bearer $MASTER_KEY" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_JSON")"

printf '%s\n' "$RESPONSE"

if [[ -n "$WRITE_ENV" ]]; then
  KEY_VALUE="$(RESPONSE_JSON="$RESPONSE" python3 - <<'PY'
import json
import os

data = json.loads(os.environ["RESPONSE_JSON"])
key = data.get("key") or data.get("token")
if not key:
    raise SystemExit("LiteLLM response did not include a generated key")
print(key)
PY
)"

  python3 - "$WRITE_ENV" "$KEY_VALUE" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1]).expanduser()
key = sys.argv[2]
existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
lines = existing.splitlines()
updated = False
for idx, line in enumerate(lines):
    if line.startswith("LITELLM_API_KEY="):
        lines[idx] = f"LITELLM_API_KEY={key}"
        updated = True
        break
if not updated:
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(f"LITELLM_API_KEY={key}")
env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

  echo "Wrote LITELLM_API_KEY to $WRITE_ENV" >&2
fi
