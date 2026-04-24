# BitMart Execution Support Matrix

This document defines the current operator-facing boundary for BitMart execution in this workspace.

## Supported target lane

The supported target lane is direct BitMart futures execution through the backend API integration:

- `VenueExecutionClient("bitmart")`
- BitMart account type `swap`, `contract`, or `futures`
- backend-only credentials from `BITMART_API_KEY`, `BITMART_SECRET`, and `BITMART_MEMO`
- readiness surfaced through `get_execution_status`
- order submission through the guarded `place_order` tool

Direct futures live order placement requires `readiness_status == "api_execution_ready"`.

## What `api_execution_ready` means

`api_execution_ready` means all of the following are true for the direct futures API lane:

- live execution env unlock is present
- BitMart credentials are configured
- private futures reads are working
- signed futures write capability has been remotely verified
- copy-trading API automation remains marked unsupported/unverified
- no current readiness blockers are present

The runtime support matrix exposes these fields:

- `live_env_unlocked`
- `credentials_configured`
- `private_futures_reads_working`
- `signed_futures_writes_verified`
- `readiness_state`
- `read_failure_category`
- `write_failure_category`
- `copy_trading_api_automation_supported`
- `copy_trading_api_automation_verified`
- `blockers`

## What `api_execution_ready` does not mean

`api_execution_ready` does not mean BitMart copy trading is API-ready.

It also does not mean:

- browser/UI automation is safe for autonomous execution
- copy-trading settings can be changed by agents
- follower/copy-trade allocation can be managed through a proven API path
- unsupported venue modes are approved for live writes
- risk, approval, sizing, and operator-confirmation gates can be bypassed

`api_execution_ready` is scoped only to the direct futures API execution lane.

## Copy-trading boundary

BitMart copy-trading API automation is unsupported or unproven in this workspace.

No autonomous workflow may treat copy trading as an API-first execution lane unless a future task proves and documents a supported API surface, including tests, telemetry, readiness classification, and operator status output.

Until then:

- copy-trading API automation must remain `false` / unverified in readiness output
- copy-trading browser flows are operator-assisted fallback only
- browser/UI actions must not be confused with backend API execution readiness
- direct futures readiness must not be used as evidence that copy trading is ready

## Browser/UI fallback

Browser or UI interaction is allowed only as an operator-assisted fallback for inspection or manual operations. It is not an autonomous execution mechanism and must not be used to bypass backend readiness, approval, or telemetry gates.

If the backend API lane is not `api_execution_ready`, the correct behavior is to block direct live execution and report the readiness blockers. The system must not silently switch to browser/UI execution.
