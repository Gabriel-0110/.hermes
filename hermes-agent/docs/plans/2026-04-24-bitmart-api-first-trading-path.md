# BitMart API-First Trading Path Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build and verify a reliable API-first BitMart trading path for live direct futures trading, with clear boundaries between supported direct futures execution and unsupported copy-trading automation.

**Architecture:** Harden the existing BitMart/CCXT live execution lane rather than relying on browser/UI flows. Add explicit readiness checks, execution smoke tests, telemetry, and operator-facing status so the orchestrator can trust API-based futures order lifecycle actions. Keep copy trading out of the autonomous execution lane unless a proven API surface exists.

**Tech Stack:** Python, Hermes Agent, BitMart futures REST API, CCXT execution adapter, pytest

---

## Context and constraints

- The environment already has live unlock env vars and BitMart credentials, but live readiness is inconsistent.
- BitMart private endpoints are intermittently affected by Cloudflare / 403 / 503 / 429 conditions.
- Supporting-agent telemetry is not yet fully wired to live exchange truth.
- Browser-side copy-trading controls are not reliable enough to count as autonomous execution.
- The immediate target is **direct futures API execution**, not copy-trading API automation.
- Preserve the desk boundary: orchestrator makes decisions, supporting agents own recurring monitoring loops.

---

## Deliverables

1. A documented, testable BitMart direct futures execution path.
2. Explicit runtime readiness checks for live API trading.
3. A safe smoke-test flow for signed/private BitMart futures operations.
4. Better execution telemetry/audit records for live order lifecycle events.
5. Clear status output that distinguishes:
   - live env unlock present
   - private reads working
   - signed writes working
   - copy-trading API unsupported/unproven

---

## Files likely involved

**Inspect first:**
- `hermes-agent/backend/integrations/execution/ccxt_client.py`
- `hermes-agent/backend/tools/place_order.py`
- `hermes-agent/backend/tools/cancel_order.py`
- `hermes-agent/backend/tools/get_execution_status.py`
- `hermes-agent/backend/tools/get_recent_trades.py`
- `hermes-agent/backend/tools/get_trade_history.py`
- `hermes-agent/backend/tools/get_portfolio_state.py` or equivalent if present
- `hermes-agent/tools/` any BitMart-facing wrappers used by runtime
- `hermes-agent/docs/trading/CCXT_EXECUTION_MIGRATION_SUMMARY.md`
- `hermes-agent/docs/trading/` related trading docs
- `hermes-agent/tests/` existing execution + backend integration tests
- `~/.hermes/teams/trading-desk/TEAM.md`
- `~/.hermes/teams/trading-desk/agents.yaml`

**Expected plan outputs to create/modify:**
- Modify: `backend/integrations/execution/ccxt_client.py`
- Modify: relevant backend execution tools under `backend/tools/`
- Modify: possibly status/execution API routes if they expose readiness state
- Create: focused tests under `tests/backend/` or nearest existing execution test directory
- Create/Modify: trading docs explaining supported live lane vs unsupported copy-trade lane

---

### Task 1: Inspect current BitMart live execution surface

**Files:**
- Read: `backend/integrations/execution/ccxt_client.py`
- Read: `backend/tools/place_order.py`
- Read: `backend/tools/cancel_order.py`
- Read: `backend/tools/get_execution_status.py`
- Read: `docs/trading/CCXT_EXECUTION_MIGRATION_SUMMARY.md`

**Step 1: Read the execution client and map current capabilities**
- Identify which methods already exist for:
  - balances
  - positions
  - open orders
  - place order
  - cancel order
  - order history / trades
- Note whether BitMart futures open/close paths are actually implemented or only partially supported.

**Step 2: Write a capability matrix in notes**
Include columns:
- capability
- implemented?
- tested?
- live-safe?
- current blocker

**Step 3: Inspect tool entrypoints**
Confirm how the runtime currently reaches the execution client and what schemas/params are exposed.

**Step 4: Commit nothing yet**
This is analysis only.

---

### Task 2: Add failing tests for live-readiness state classification

**Files:**
- Create/Modify: `tests/.../test_bitmart_live_readiness.py`
- Modify: readiness/status code wherever runtime execution state is computed

**Step 1: Write failing tests**
Cover at least these cases:
- env unlock absent -> status = not_live
- env unlock present but credentials absent -> status = blocked_missing_credentials
- credentials present but private reads fail -> status = degraded_private_access
- private reads succeed but signed-write capability unverified -> status = read_only_live
- signed write verification succeeds -> status = api_execution_ready
- copy trading marked unsupported/unverified -> separate flag remains false

**Step 2: Run targeted test to confirm failure**
Run the exact pytest target for the new readiness test file.
Expected: missing symbols / failing assertions.

**Step 3: Implement minimal readiness model**
Create a small structured status object or helper function rather than hardcoding booleans in many places.

**Step 4: Run tests to passing**
Run the new readiness test file.

**Step 5: Commit**
`git commit -m "feat: classify bitmart live execution readiness states"`

---

### Task 3: Add failing tests for signed futures order smoke-test plumbing

**Files:**
- Create/Modify: `tests/.../test_bitmart_futures_smoke_checks.py`
- Modify: `backend/integrations/execution/ccxt_client.py`

**Step 1: Write failing tests**
Test a smoke-check method that does **not** place a real market-risking order by default. It should verify:
- signed auth can be generated / request prepared
- exchange venue config resolves to futures
- minimum order metadata can be loaded
- client can distinguish dry-run capability check from real order placement

Also test failure modes:
- 403/Cloudflare -> degraded_write_access
- 429 -> rate_limited_write_access
- invalid signature -> auth_failed

**Step 2: Run tests and confirm failure**
Target only this file.

**Step 3: Implement minimal smoke-check method**
Add a helper such as:
- `check_futures_write_capability()`
or
- `probe_futures_execution_path()`
that returns structured status and error classification.

**Step 4: Run tests to passing**

**Step 5: Commit**
`git commit -m "feat: add bitmart futures write-capability smoke check"`

---

### Task 4: Add failing tests for execution event telemetry

**Files:**
- Create/Modify: `tests/.../test_execution_telemetry.py`
- Modify: execution event writing path used by the backend/runtime

**Step 1: Write failing tests**
Verify that API execution attempts emit telemetry for:
- capability probe started/finished
- order submit requested
- order submit accepted/rejected
- cancel requested
- cancel accepted/rejected
- error classified (Cloudflare, auth, rate limit, exchange reject)

**Step 2: Run tests to see failure**

**Step 3: Implement minimal telemetry writes**
Write to the existing execution/telemetry store instead of inventing a new one if possible.

**Step 4: Re-run tests**

**Step 5: Commit**
`git commit -m "feat: log bitmart execution lifecycle telemetry"`

---

### Task 5: Harden private read paths with explicit error classification

**Files:**
- Modify: `backend/integrations/execution/ccxt_client.py`
- Test: extend execution client tests

**Step 1: Write failing tests for read-path errors**
Simulate:
- 403 Cloudflare
- 503 HTML challenge page
- 429 rate limit
- malformed JSON
- valid BitMart error payloads

**Step 2: Run tests and confirm failure**

**Step 3: Implement targeted classification helpers**
Add a single helper that maps raw HTTP/API failures into canonical categories.
Do not duplicate logic across balance/position/order methods.

**Step 4: Run tests to passing**

**Step 5: Commit**
`git commit -m "fix: classify bitmart private read failures explicitly"`

---

### Task 6: Expose a direct futures execution support matrix to operators

**Files:**
- Modify: status/execution route or CLI status surface where exchange readiness is shown
- Test: corresponding API/CLI tests

**Step 1: Write failing tests**
Status output should expose at least:
- live env unlock present?
- credentials configured?
- private futures reads working?
- signed futures writes verified?
- copy-trading API automation supported? false/unverified
- current blockers list

**Step 2: Run tests and confirm failure**

**Step 3: Implement minimal status surface**
Prefer augmenting existing execution status rather than creating a new command/path.

**Step 4: Run tests to passing**

**Step 5: Commit**
`git commit -m "feat: expose bitmart execution support matrix"`

---

### Task 7: Add a safe manual approval path for real direct futures execution

**Files:**
- Modify: order placement tool / execution adapter as needed
- Test: order validation + approval-gate tests

**Step 1: Write failing tests**
Cover that real live order placement requires:
- live readiness = api_execution_ready
- symbol + side + size validation
- explicit approval state if required by current desk rules
- proper venue routing to BitMart futures

**Step 2: Run tests to confirm failure**

**Step 3: Implement minimal gating changes**
Keep this narrow. Do not build full strategy automation here.
The goal is: if orchestrator has a valid trade, the API lane can actually submit it safely.

**Step 4: Run tests**

**Step 5: Commit**
`git commit -m "feat: gate live futures order placement on verified api readiness"`

---

### Task 8: Document unsupported/unproven copy-trading automation explicitly

**Files:**
- Modify: `docs/trading/CCXT_EXECUTION_MIGRATION_SUMMARY.md`
- Create/Modify: a new doc such as `docs/trading/BITMART_LIVE_EXECUTION_STATUS.md`

**Step 1: Write/update docs**
Document clearly:
- direct futures API lane: supported target
- copy trading API lane: unsupported or unproven in current workspace
- browser UI remains operator-assisted fallback only
- what “API-first live ready” actually means

**Step 2: Verify docs reflect code reality**
Check against implementation from Tasks 2–7.

**Step 3: Commit**
`git commit -m "docs: clarify bitmart api-first execution support boundaries"`

---

### Task 9: Run focused verification suite

**Files:**
- No new files unless fixing tests

**Step 1: Run targeted execution tests**
Run the specific pytest files touched in Tasks 2–7.

**Step 2: Fix any failing tests one at a time**
No bundle-fixing. Root cause each failure.

**Step 3: Re-run the focused suite**
Confirm all touched tests pass.

**Step 4: If environment allows, run a broader backend/execution subset**
Examples:
- backend integration tests
- execution tool tests
- readiness/status tests

**Step 5: Commit**
`git commit -m "test: verify bitmart api-first execution path"`

---

### Task 10: Manual runtime verification checklist

**Files:**
- Update docs if needed with the checklist

**Step 1: Verify live env surface**
Check:
- `HERMES_TRADING_MODE`
- `HERMES_ENABLE_LIVE_TRADING`
- `HERMES_LIVE_TRADING_ACK`
- BitMart credentials

**Step 2: Verify private futures reads**
Confirm:
- balances
- positions
- open orders

**Step 3: Verify write-capability probe**
Run the new smoke-check path and record result.

**Step 4: Verify status output**
Ensure operator-facing status now truthfully says whether API execution is ready.

**Step 5: Verify copy trading remains marked unsupported/unverified**
Do not blur this boundary.

---

## Non-goals for this plan

- Do **not** automate copy-trading lifecycle unless a real API path is discovered and tested.
- Do **not** build full 15-minute strategy cron ownership inside orchestrator.
- Do **not** add new trading strategies here.
- Do **not** bypass approval gates for risky live actions.

---

## Definition of done

This plan is complete when:
- the system can truthfully report whether BitMart direct futures API trading is ready,
- private read failures and signed-write failures are classified clearly,
- execution telemetry is written for key lifecycle events,
- direct live futures order submission is gated on verified readiness,
- documentation clearly separates supported direct futures execution from unsupported copy-trading automation.

---

Plan complete and saved to `docs/plans/2026-04-24-bitmart-api-first-trading-path.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**