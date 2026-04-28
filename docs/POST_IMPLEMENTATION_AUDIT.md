# Hermes Post-Implementation Audit (Prompts A–H)

**Date:** 2026-04-26
**Reviewer role:** Independent senior trading-systems architect / production-readiness reviewer
**Repo:** `/Users/openclaw/.hermes`
**Repo HEAD:** `d8387ff` ("feat: update model configurations and API keys in litellm_config.yaml and docker-compose.dev.yml")
**Working tree:** clean except `M hermes-agent/litellm_config.yaml`
**Default trading mode:** `paper` (verified)

---

## 1. Executive Summary

I independently re-executed every verification claim in [POST_REMEDIATION_AUDIT.md](POST_REMEDIATION_AUDIT.md) §Prompts A–H. All headline numbers reproduce: the full test suite is **5238 passed / 25 skipped / 0 failed / 0 errors**, the alembic DAG is a single linear chain ending at **`0009`**, `ruff check backend/` is clean, the regime/exit/learning/rotation/policy-trace modules implement what the prompts describe, and the `tirith` 10 MB binary is genuinely gone from git history (only the small Python source files `tools/tirith_security.py` and its test remain). The repo `.git` directory is **12 MB** — under the 15 MB threshold.

**Two real follow-ups surfaced that the prior audit did not flag:**

1. **Hardcoded HMAC fallback secret** in [approval_signing.py:17](hermes-agent/backend/trading/approval_signing.py#L17) (`_DEFAULT_SECRET = "hermes-approval-default-key"`) silently masks an unset `HERMES_APPROVAL_HMAC_SECRET`. Any attacker with source-code access can forge approve/decline callbacks. Should fail-closed (raise `RuntimeError`) when the env var is missing in production.
2. **Root `.gitignore` does NOT cover the runtime artifacts** the prior audit claimed (`tirith`, `port*.html`, `.tick.lock`, `.bundled_manifest`, `gateway_state.json`, `processes.json`). Those files are still committable. Today they are clean only because no one has run `git add` on them since the filter-repo. This contradicts §2a finding #6 of [POST_AUDIT_VERIFICATION.md](POST_AUDIT_VERIFICATION.md) and §"Repo hygiene completed" of [POST_REMEDIATION_AUDIT.md](POST_REMEDIATION_AUDIT.md).

Other minor items: `mypy` reports 4 typing issues in new files (none functional), `dispatch_trade_proposal` is called with a `dict` instead of a `TradeProposal` from capital rotation (works because of pydantic coercion downstream, but type-unsafe), the dry-run path of `learning_loop` increments `overrides_written` instead of a separate counter, and Telegram callback authorization silently skips the user-allowlist check when `TELEGRAM_ALLOWED_USERS` is empty.

**Verdict (consistent with [RELEASE_READINESS.md](RELEASE_READINESS.md), with caveat below):**
- ✅ Paper trading: **READY**
- ✅ Approval-required paper: **READY**
- ⚠️ Limited live: **CONDITIONAL** (now also gated on setting `HERMES_APPROVAL_HMAC_SECRET` and tightening `.gitignore`)
- ❌ Full live automation: **NOT READY** (≥30 days paper validation + closed live reconciliation)

---

## 2. Phase-by-Phase Verification Table

| Phase | Claim under test | Result | Evidence |
|---|---|---|---|
| **1. Test suite** | 5238+ passed, 0 failed, 0 errors | ✅ | `pytest tests/backend tests/tools tests/hermes_cli -q` → `5238 passed, 25 skipped, 5258 warnings in 105.51s` |
| **3. Alembic head** | Single head `0009` | ✅ | `alembic heads` → `0009 (head)` |
| **3. Migrations apply** | All 9 migrations run cleanly on fresh sqlite | ✅ | `DATABASE_URL=sqlite:////tmp/audit_verify.db alembic upgrade head` ran upgrades 0001 → 0002 → … → 0009 with no errors |
| **4. ruff** | `ruff check backend/` clean | ✅ | `All checks passed!` |
| **4. mypy (new files)** | Strict-mode clean on new files | ⚠️ | 4 errors total (3 pre-existing-style "None vs float", 1 Pydantic Awaitable type stub mismatch). Listed in §3.1 below. |
| **5. Regime detector** | log-close lin reg + ATR vol-of-vol; fail-closed UNKNOWN | ✅ | [detector.py:38–53](hermes-agent/backend/regime/detector.py#L38), [detector.py:56–73](hermes-agent/backend/regime/detector.py#L56), `get_current_regime()` returns `MarketRegime.UNKNOWN` when cache miss |
| **5. Strategy mappings** | momentum/breakout→trends, mean_reversion→range, delta_neutral_carry→all, whale_follower→all−high_vol | ✅ | [registry.py:54](hermes-agent/backend/strategies/registry.py#L54), [L68](hermes-agent/backend/strategies/registry.py#L68), [L82](hermes-agent/backend/strategies/registry.py#L82), [L95](hermes-agent/backend/strategies/registry.py#L95), [L110](hermes-agent/backend/strategies/registry.py#L110) — all match spec exactly |
| **6. Trailing ratchets only** | New SL only widens toward profit; never widens toward loss | ✅ | [exit_manager.py:83](hermes-agent/backend/trading/exit_manager.py#L83): long path requires `new_sl > current_sl_trigger`; [L94](hermes-agent/backend/trading/exit_manager.py#L94): short requires `new_sl < current_sl_trigger` |
| **6. Time stop deterministic** | Uses provided `now`; injectable | ✅ | [exit_manager.py:120](hermes-agent/backend/trading/exit_manager.py#L120): `now = now or datetime.now(UTC)` |
| **6. Adverse excursion formula** | Long: `(entry-mark)/entry*1e4`; Short: `(mark-entry)/entry*1e4` | ✅ | [exit_manager.py:158–161](hermes-agent/backend/trading/exit_manager.py#L158) |
| **6. modify_bracket_order fail-closed** | Returns failure dict on any error; never cancels existing bracket | ✅ | [multi_venue.py:1240–1252](hermes-agent/backend/integrations/execution/multi_venue.py#L1240) (network exception path) and [L1262–1278](hermes-agent/backend/integrations/execution/multi_venue.py#L1262) (HTTP error path) — both return without state mutation |
| **7. Weight clamp [0.1, 3.0]** | Both bounds enforced | ✅ | [learning_loop.py:27–28](hermes-agent/backend/jobs/learning_loop.py#L27), [L60](hermes-agent/backend/jobs/learning_loop.py#L60) |
| **7. Idempotency** | Same input → no DB write | ✅ | [learning_loop.py:138–141](hermes-agent/backend/jobs/learning_loop.py#L138): `if abs(existing.weight - weight) < 0.0001: overrides_unchanged += 1; continue` |
| **7. Reads only closed trades** | `resolved_at IS NOT NULL AND pnl_pct IS NOT NULL` | ✅ | [learning_loop.py:81–84](hermes-agent/backend/jobs/learning_loop.py#L81) |
| **7. Override read** | `scale_confidence_by_prior` prefers DB override over computed prior | ✅ | [performance_priors.py:148–151](hermes-agent/backend/strategies/performance_priors.py#L148): `multiplier = override if override is not None else prior.multiplier` |
| **7. Strategy evaluator writes** | Evaluator persists override rows | ✅ | `grep -n StrategyWeightOverrideRow backend/jobs/strategy_evaluator.py` confirms write path; matches Prompt D claim |
| **8. Regime gate rejects UNKNOWN** | UNKNOWN regime + gated strategy → REGIME_MISMATCH | ✅ | [policy_engine.py:136–141](hermes-agent/backend/trading/policy_engine.py#L136): `if current_regime not in strategy_def.allowed_regimes` adds `REGIME_MISMATCH` rejection. UNKNOWN is absent from momentum/breakout/mean_reversion sets, so they reject. |
| **8. persist_policy_trace tolerates DB failure** | `try/except` with debug log; never raises | ✅ | [policy_engine.py:21–41](hermes-agent/backend/trading/policy_engine.py#L21) |
| **8. HMAC-SHA256, 10-min TTL** | Algorithm + TTL constants present; constant-time compare | ✅ | [approval_signing.py:14](hermes-agent/backend/trading/approval_signing.py#L14): `_TTL_SECONDS = 600`; [L26](hermes-agent/backend/trading/approval_signing.py#L26): `hashlib.sha256`; [L52](hermes-agent/backend/trading/approval_signing.py#L52): `hmac.compare_digest` |
| **8. Telegram TTL+sig+auth** | All three checked in `ta:` callback | ✅ | [telegram.py:1557–1583](hermes-agent/gateway/platforms/telegram.py#L1557) verifies HMAC; expired returns "⏰ This approval has expired"; `TELEGRAM_ALLOWED_USERS` check at [L1581](hermes-agent/gateway/platforms/telegram.py#L1581) |
| **9. Softmax sums to 1.0** | Probabilities sum to 1 before/after capping | ✅ | [rebalancer.py:79–84](hermes-agent/backend/portfolio/rebalancer.py#L79) — standard softmax with max-stabilisation; `_cap_and_renormalize` re-sums to 1 |
| **9. 40% cap enforced** | Iterative cap-and-renorm | ✅ | [rebalancer.py:18](hermes-agent/backend/portfolio/rebalancer.py#L18): `MAX_ALLOCATION_PCT = 0.40`; [L88–110](hermes-agent/backend/portfolio/rebalancer.py#L88) iterative |
| **9. require_operator_approval=True** | All dispatched proposals | ✅ | [capital_rotation.py:187](hermes-agent/backend/jobs/capital_rotation.py#L187) — single dispatch path always sets `True` |
| **9. min-delta filter** | Skip < 50 bps | ✅ | [rebalancer.py:142–149](hermes-agent/backend/portfolio/rebalancer.py#L142): `if delta_bps < min_rebalance_bps: proposal.skipped.append(...)` |
| **10. tirith binary purged from history** | `git rev-list --objects --all -- "*/tirith" "bin/tirith" "tirith"` returns 0 binary refs | ✅ | Only matches are `hermes-agent/tools/tirith_security.py` and `hermes-agent/tests/tools/test_tirith_security.py` (small Python source) |
| **10. Repo size** | < 15 MB | ✅ | `du -sh .git` → `12M` |
| **10. .gitignore covers runtime artifacts** | `tirith`, `port*.html`, `.tick.lock`, `gateway_state.json`, `processes.json`, `.bundled_manifest` patterns present | ❌ **Discrepancy** | Root `.gitignore` does NOT contain any of these patterns. See §3.2. |

---

## 3. New Issues Discovered

### 3.1 Mypy errors in new files (severity: low)

```text
backend/trading/exit_manager.py:79  Unsupported operand types for / ("None" and "int")
backend/trading/exit_manager.py:90  Unsupported operand types for / ("None" and "int")
backend/regime/detector.py:142     model_validate_json incompatible type "Awaitable[Any] | Any"
backend/jobs/capital_rotation.py:174 dispatch_trade_proposal expects "TradeProposal", got "dict[str, object]"
```

- exit_manager errors are spurious (the `None` branch is guarded by `if state.trailing_stop_distance_bps is None: return` earlier). Add an `assert` or `# type: ignore[operator]`.
- detector.py:142 stems from `redis_client.get()` typing returning `Awaitable | Any`. Cast or narrow.
- capital_rotation.py:174 — the actual function accepts dict via Pydantic but the signature is `TradeProposal`. Either update the call site to construct `TradeProposal(**...)` or broaden the parameter type.

None affect runtime correctness.

### 3.2 `.gitignore` does not cover claimed runtime artifacts (severity: medium)

The root `.gitignore` ([.gitignore](.gitignore)) covers virtualenvs, secrets, caches and a few app-specific paths but **omits** every pattern listed under "Gitignore runtime state files" in [POST_AUDIT_VERIFICATION.md](POST_AUDIT_VERIFICATION.md) §2b:

- `bin/tirith` — not present
- `port*.html` — not present (and `port3000.html`, `port3100.html`, `hermes/response_3000.html`, `hermes/response_3100.html` exist in the working tree)
- `cron/.tick.lock` — not present
- `gateway_state.json` — not present (file exists at repo root)
- `processes.json` — not present (file exists at repo root)
- `.bundled_manifest` — not present
- `feishu_seen_message_ids.json` — not present (file exists at repo root)

**Risk:** any operator running `git add -A` will commit live runtime state and large response dumps back into the repo, undoing the filter-repo cleanup. The 10 MB `tirith` binary itself is correctly absent from history; that part is solid.

**Fix:** append to root `.gitignore`:

```gitignore
# Runtime artifacts (do not commit)
bin/tirith
profiles/*/bin/tirith
port*.html
*.html
gateway_state.json
processes.json
feishu_seen_message_ids.json
cron/.tick.lock
profiles/*/cron/.tick.lock
**/.bundled_manifest
hermes/response_*.html
hermes-agent/temp_vision_images/
```

(Adjust `*.html` if there are tracked HTMLs that must remain.)

### 3.3 Hardcoded HMAC fallback secret (severity: medium-high)

[approval_signing.py:17](hermes-agent/backend/trading/approval_signing.py#L17):

```python
_DEFAULT_SECRET = "hermes-approval-default-key"
```

If `HERMES_APPROVAL_HMAC_SECRET` is unset, all signed callbacks use this constant — an attacker can compute valid signatures from the public source code. The current `RELEASE_READINESS.md` lists "Set HERMES_APPROVAL_HMAC_SECRET env var" as an operator action but the code does not enforce it.

**Fix (recommended):**

```python
def _get_secret() -> str:
    secret = os.getenv(_SECRET_ENV)
    if not secret:
        if os.getenv("HERMES_TRADING_MODE", "paper").lower() == "live":
            raise RuntimeError(f"{_SECRET_ENV} must be set when trading mode is 'live'")
        return _DEFAULT_SECRET  # paper-only fallback
    return secret
```

Pair with a startup-time assertion in the gateway boot path.

### 3.4 Telegram allow-list silently no-ops when env var is empty (severity: low-medium)

[telegram.py:1581–1586](hermes-agent/gateway/platforms/telegram.py#L1581):

```python
allowed_csv = os.getenv("TELEGRAM_ALLOWED_USERS", "").strip()
if allowed_csv:
    allowed_ids = {uid.strip() for uid in allowed_csv.split(",") if uid.strip()}
    if "*" not in allowed_ids and caller_id not in allowed_ids:
        await query.answer(text="⛔ You are not authorized.")
        return
```

If the env var is empty, the entire authorization branch is skipped — anyone whose Telegram chat reaches the bot can approve trades. The comment in the code indicates this is intentional but it is a footgun. Suggest fail-closed when both `HERMES_TRADING_MODE=live` and `TELEGRAM_ALLOWED_USERS` is empty.

### 3.5 `learning_loop --dry-run` increments `overrides_written` (severity: cosmetic)

[learning_loop.py:131–133](hermes-agent/backend/jobs/learning_loop.py#L131):

```python
if dry_run:
    summary.overrides_written += 1
    continue
```

Reports "1 written" in the dry-run summary even though nothing is written. Either rename the counter to `overrides_proposed` or use a separate `overrides_dry_run` field.

### 3.6 `dispatch_trade_proposal` typed contract violation from capital rotation (severity: low)

See §3.1 mypy item. Functional today (the function presumably normalizes via Pydantic) but a refactor that tightens the signature will break capital rotation silently.

---

## 4. Updated Readiness Verdict

| Mode | Verdict | Conditions |
|---|---|---|
| ✅ Paper trading | **READY** | Default; approval gate + tri-state mode + regime gate + exit manager all functional |
| ✅ Approval-required paper | **READY** | `HERMES_REQUIRE_APPROVAL=true` honoured in paper |
| ⚠️ Limited live | **CONDITIONAL** | Now requires (a) `HERMES_APPROVAL_HMAC_SECRET` set & code enforces it, (b) `.gitignore` patched (§3.2), (c) `TELEGRAM_ALLOWED_USERS` set, (d) ≥7 days operator-snapshot reconciliation < 1% divergence, (e) full live unlock chain |
| ❌ Full live automation | **NOT READY** | ≥30 days paper validation + closed learning-loop feedback validation (Prompt D needs ≥1 weekly cycle observed) |

---

## 5. Prioritised Next Steps

1. **(High) Patch `.gitignore`** per §3.2 to prevent recommitting purged runtime artifacts.
2. **(High) Harden `approval_signing._get_secret()`** per §3.3 — fail-closed when live and secret unset.
3. **(Medium) Tighten Telegram authorization** per §3.4.
4. **(Medium) Fix mypy errors in new files** per §3.1; add `mypy --strict` on `backend/regime/`, `backend/trading/exit_manager.py`, `backend/jobs/learning_loop.py`, `backend/jobs/capital_rotation.py`, `backend/portfolio/`, `backend/trading/approval_signing.py` to CI.
5. **(Low) Rename `learning_loop` dry-run counter** per §3.5.
6. **(Low) Adopt `TradeProposal` constructor** in `_dispatch_rebalance_proposal` per §3.6.
7. **(Operator)** Run live BitMart sandbox bracket round-trip on a fresh demo account weekly until limited-live promotion (already passing once per Prompt G).
8. **(Operator)** Begin ≥7-day operator-snapshot reconciliation with `<1%` divergence before flipping any limited-live env unlock.

---

## 6. Execution Prompts for Remaining Work

> **Global rules:** Do not stop running services. Default trading mode stays `paper`. Do not modify `.env` secrets without operator approval. Do not push to remote without operator approval. Do not rewrite git history.

### Prompt I — Repo hygiene gitignore patch ✅ COMPLETED

- Added `hermes/response_*.html` pattern to `.gitignore`
- Added `skills/.bundled_manifest` and `**/.bundled_manifest` patterns
- Untracked `hermes/response_3000.html`, `hermes/response_3100.html`, `skills/.bundled_manifest` via `git rm --cached`
- Note: audit §3.2 was partially incorrect — most patterns were already present (`port*.html`, `gateway_state.json`, `processes.json`, `feishu_seen_message_ids.json`, `bin/tirith`, `.tick.lock`). Only `hermes/response_*.html` subdirectory and `skills/.bundled_manifest` were uncovered.

### Prompt J — HMAC secret hardening ✅ COMPLETED

- `_get_secret()` in `approval_signing.py` now raises `RuntimeError` when `HERMES_TRADING_MODE=live` and `HERMES_APPROVAL_HMAC_SECRET` is unset
- Paper mode still uses default secret (unchanged behavior)
- 3 new tests: `test_live_mode_without_secret_raises`, `test_paper_mode_without_secret_uses_default`, `test_live_mode_with_secret_works`

### Prompt K — Telegram allow-list fail-closed ✅ COMPLETED

- `ta:` callback handler now refuses with "⛔ Authorization not configured." when `HERMES_TRADING_MODE=live` and `TELEGRAM_ALLOWED_USERS` is empty
- Paper mode behavior unchanged (open access for testing)
- 5 new tests covering live+empty, paper+empty, live+configured, live+unauthorized user logic

### Prompt L — Mypy clean-up on new code ✅ COMPLETED

- Added `assert state.trailing_stop_distance_bps is not None` in `exit_manager.py` (mypy guard for early-return pattern)
- Narrowed `raw` type in `detector.py` Redis cache read with `isinstance(raw, str)` check
- Replaced dict literal with `TradeProposal(...)` constructor in `capital_rotation.py`
- Fixed dry-run counter: renamed to `overrides_proposed` (was incorrectly incrementing `overrides_written`)
- Added `make typecheck-new` Makefile target — exits 0 on all new files
- 0 mypy errors in new code

### Prompt M — Live promotion gate (operator + agent collaboration)

Once Prompts I–L are merged, run a **7-day operator-snapshot reconciliation observation window** in paper:

1. Daily, run `python -m backend.jobs.operator_snapshot` (or equivalent cron entry).
2. Each run: assert `divergence_pct < 1.0` between Hermes-internal totals and BitMart-reported equity.
3. Log results to `reports/operator_snapshot_window.md` daily.
4. After 7 consecutive green days with no divergence > 1%, propose flipping `HERMES_TRADING_MODE` to `live` with a manual operator approval ceremony (set `LIVE_TRADING_ACK_PHRASE`, set `HERMES_ENABLE_LIVE_TRADING=true`).

Do NOT auto-promote. The promotion is operator-driven.

---

## 7. Verification command transcript (key results)

```text
$ cd hermes-agent && ../.venv/bin/pytest tests/backend tests/tools tests/hermes_cli -q
5238 passed, 25 skipped, 5258 warnings in 105.51s

$ ../.venv/bin/alembic heads
0009 (head)

$ rm -f /tmp/audit_verify.db && DATABASE_URL=sqlite:////tmp/audit_verify.db ../.venv/bin/alembic upgrade head
INFO  alembic.runtime.migration  Running upgrade  -> 0001
INFO  alembic.runtime.migration  Running upgrade 0001 -> 0002
INFO  alembic.runtime.migration  Running upgrade 0002 -> 0003
INFO  alembic.runtime.migration  Running upgrade 0003 -> 0004
INFO  alembic.runtime.migration  Running upgrade 0004 -> 0005
INFO  alembic.runtime.migration  Running upgrade 0005 -> 0006
INFO  alembic.runtime.migration  Running upgrade 0006 -> 0007
INFO  alembic.runtime.migration  Running upgrade 0007 -> 0008
INFO  alembic.runtime.migration  Running upgrade 0008 -> 0009

$ ../.venv/bin/ruff check backend/
All checks passed!

$ ../.venv/bin/mypy --ignore-missing-imports backend/regime/ backend/trading/exit_manager.py \
    backend/trading/approval_signing.py backend/jobs/learning_loop.py \
    backend/jobs/capital_rotation.py backend/portfolio/rebalancer.py \
    | grep -E "^(backend/regime|backend/trading/exit_manager|backend/trading/approval_signing|backend/jobs/learning_loop|backend/jobs/capital_rotation|backend/portfolio/rebalancer)"
backend/trading/exit_manager.py:79: error: Unsupported operand types for / ("None" and "int")
backend/trading/exit_manager.py:90: error: Unsupported operand types for / ("None" and "int")
backend/regime/detector.py:142: error: Argument 1 to "model_validate_json" of "BaseModel" has incompatible type "Awaitable[Any] | Any"
backend/jobs/capital_rotation.py:174: error: Argument 1 to "dispatch_trade_proposal" has incompatible type "dict[str, object]"; expected "TradeProposal"
(approval_signing.py — 0 errors)

$ git rev-list --objects --all -- "bin/tirith" "*/tirith" "tirith" | grep -v "tirith_security"
(empty — binary fully purged from history)

$ du -sh .git
 12M    /Users/openclaw/.hermes/.git
```
