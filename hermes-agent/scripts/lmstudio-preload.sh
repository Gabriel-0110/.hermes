#!/usr/bin/env bash
# Preload both LM Studio models so they stay resident in memory.
# Run once after LM Studio server starts, or add to login items / launchd.
#
# Context note: both models fit together at 65536 tokens (~12.5 GB total).
# To push higher (e.g. 131072), disable LM Studio's memory guardrail first:
#   LM Studio → Settings → Advanced → "Model loading guardrails" → off
# Then set LMS_CONTEXT=131072 and re-run.
set -euo pipefail

LMS="${LMS_CLI:-$HOME/.lmstudio/bin/lms}"
TTL="${LMS_TTL:-86400}"            # 24 h; set to 0 for permanent (no auto-unload)
CONTEXT_LENGTH="${LMS_CONTEXT:-65536}"

if ! "$LMS" --version >/dev/null 2>&1; then
  echo "lms CLI not found at $LMS" >&2
  exit 1
fi

load_model() {
  local model="$1"
  local identifier="$2"

  local ps_line
  ps_line=$("$LMS" ps 2>/dev/null | grep "^${identifier}" || true)

  if [[ -n "$ps_line" ]]; then
    local loaded_ctx status
    loaded_ctx=$(echo "$ps_line" | awk '{print $5}')
    status=$(echo "$ps_line" | awk '{print $3}')

    # Skip if actively inferring — reload would interrupt the user
    if [[ "$status" == "GENERATING" || "$status" == "PROCESSINGPROMPT" ]]; then
      echo "  [busy]  $identifier is $status — reload skipped (run again when idle)"
      return
    fi

    # Re-load if context or TTL doesn't match target
    local loaded_ttl
    loaded_ttl=$(echo "$ps_line" | awk '{print $NF}' | cut -d/ -f2)
    if [[ "$loaded_ctx" == "$CONTEXT_LENGTH" && "$loaded_ttl" == "${TTL}s" ]]; then
      echo "  [ok]    $identifier already loaded (ctx=${loaded_ctx}, ttl=${loaded_ttl})"
      return
    fi

    echo "  [reload] $identifier (ctx: ${loaded_ctx}→${CONTEXT_LENGTH}, ttl: ${loaded_ttl}→${TTL}s)"
    "$LMS" unload "$identifier" 2>/dev/null || true
    sleep 1
  fi

  echo "  [load]  $identifier (ctx=${CONTEXT_LENGTH}, ttl=${TTL}s)..."
  if ! "$LMS" load "$model" \
      --identifier "$identifier" \
      --context-length "$CONTEXT_LENGTH" \
      --ttl "$TTL" \
      -y; then
    echo ""
    echo "  Failed to load $identifier. If this is a memory error, disable" >&2
    echo "  LM Studio's guardrail: Settings → Advanced → Model loading guardrails → off" >&2
    return 1
  fi
}

echo "=== LM Studio model preload ==="
load_model "qwen/qwen3.5-9b"    "qwen/qwen3.5-9b"
load_model "google/gemma-4-e4b" "google/gemma-4-e4b"

echo ""
echo "Loaded models:"
"$LMS" ps
