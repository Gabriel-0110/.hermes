# Hermes gateway runtime policy

This document is the workspace-level source of truth for **launchd gateway ownership**, **authoritative runtime state**, and **safe restart procedure** after the April 2026 runtime verification.

## Current ownership

- **Slack owner:** `orchestrator`
- **Telegram owner:** `orchestrator`
- **Authoritative runtime state:** `profiles/orchestrator/gateway_state.json`
- **Non-authoritative root state file:** `gateway_state.json`

The root-level `gateway_state.json` can remain on disk as stale local runtime residue, but it is **not** the runtime source of truth while the active profile is `orchestrator`.

## Allowed gateway services

These launchd labels may exist on disk under `~/Library/LaunchAgents/`, but they do **not** all belong in the active runtime.

| Launchd label | Role | Policy |
| --- | --- | --- |
| `ai.hermes.gateway-orchestrator` | Human-facing gateway owner | **Enabled** and expected to run |
| `ai.hermes.gateway` | Default/root profile gateway | **Disabled** while `orchestrator` owns Slack/Telegram |
| `ai.hermes.gateway-market-researcher` | Profile-scoped research bot | **Disabled by default** unless explicitly assigned a distinct Slack/Telegram bot identity and documented here |
| `ai.hermes.gateway-portfolio-monitor` | Profile-scoped monitoring bot | **Disabled by default** unless explicitly assigned a distinct Slack/Telegram bot identity and documented here |
| `ai.hermes.gateway-risk-manager` | Profile-scoped risk bot | **Disabled by default** unless explicitly assigned a distinct Slack/Telegram bot identity and documented here |
| `ai.hermes.gateway-strategy-agent` | Profile-scoped strategy bot | **Disabled by default** unless explicitly assigned a distinct Slack/Telegram bot identity and documented here |
| `ai.hermes.gateway-execution-agent` | No verified launchd service in current runtime | Leave disabled/off until a real gateway owner is assigned |

## Why the policy is conservative

Hermes already has scoped Slack/Telegram lock support in code, so duplicate tokens should not be allowed to connect at the same time. Even so, launchd can still auto-respawn old profile services and create operator confusion if multiple profiles are left enabled without a clearly documented bot-ownership map.

Operational rule:

- **Only keep a profile gateway enabled if its Slack and Telegram identities are intentionally assigned, distinct, and documented here.**
- If that ownership is not explicit, leave the launchd job disabled.

## Safe restart procedure

Use this exact flow when you want to restart the human-facing gateway without breaking the verified orchestrator runtime:

```bash
hermes profile use orchestrator
hermes gateway doctor
hermes gateway restart
hermes gateway status --deep
```

On macOS, if you need to inspect launchd directly:

```bash
launchctl print gui/$(id -u)/ai.hermes.gateway-orchestrator
ps -axo pid,ppid,stat,start,time,command | grep -E 'hermes_cli\.main .*gateway' | grep -v grep
```

## Avoiding token contention

To keep Slack/Telegram stable:

1. Do **not** run `ai.hermes.gateway` and `ai.hermes.gateway-orchestrator` at the same time.
2. Do **not** re-enable other profile-scoped gateway jobs just because their plist exists.
3. If a profile gets its own dedicated bot identity later, update this document first.
4. Run `hermes gateway doctor` after any `.env`, profile, or launchd change.

If you intentionally introduce a second concurrently running gateway profile in the future, verify all of the following before enabling it:

- distinct `SLACK_BOT_TOKEN`
- distinct `SLACK_APP_TOKEN`
- distinct `TELEGRAM_BOT_TOKEN`
- no duplicate identity warnings from `hermes gateway doctor`
- the new profile is explicitly added to the ownership table above

## Quick operator checklist

- `orchestrator` is the only approved Slack/Telegram owner right now
- `profiles/orchestrator/gateway_state.json` is authoritative
- root/default `gateway_state.json` is not authoritative
- use `hermes gateway doctor` before and after launchd changes
- keep non-owner profile gateway jobs disabled until ownership is explicitly assigned

## Cron runtime scope for `orchestrator`

When the active profile is `orchestrator`, the gateway and cron scheduler read **profile-scoped** state from `profiles/orchestrator/`, not from the root `~/.hermes/` home.

That means the authoritative cron assets are:

- `profiles/orchestrator/cron/jobs.json`
- `profiles/orchestrator/scripts/`
- `profiles/orchestrator/cron/output/<job_id>/<timestamp>.md`
- `profiles/orchestrator/logs/agent.log`
- `profiles/orchestrator/logs/errors.log`

The root-level `cron/jobs.json` and root `scripts/` directory are useful for workspace development and manual verification, but they are **not scheduled automatically** while `orchestrator` owns the runtime.

For the runtime risk jobs added in April 2026:

- `portfolio_sync.py` should run first so exchange-backed `PortfolioSnapshotRow` data exists before `drawdown_guard.py` evaluates 30-day drawdown.
- `drawdown_guard.py` should run with `HERMES_HOME=profiles/orchestrator` (or another explicit profile) so it reads the correct `.env`, Redis keys, DB path, logs, and notification channels.
- `whale_tracker.py` should also run inside the active profile because it emits `whale_flow` events onto the profile-scoped Redis/event-bus runtime.

The wrappers in `scripts/` now self-bootstrap by:

1. locating the workspace root dynamically,
2. re-execing under `~/.hermes/.venv/bin/python` when available,
3. inferring `HERMES_HOME` from either the enclosing profile path or `active_profile`,
4. loading `HERMES_HOME/.env`, and
5. initializing profile-scoped cron logging.

If you want these jobs to be scheduled by the live `orchestrator` runtime, install matching wrapper files under `profiles/orchestrator/scripts/` and create the corresponding entries in `profiles/orchestrator/cron/jobs.json`.

That rollout is now in place for:

- `portfolio-sync` — every 5 minutes
- `drawdown-guard` — every 15 minutes
- `whale-tracker` — every 30 minutes