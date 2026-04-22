---
name: trading-desk-profile-team-setup
description: Set up a Hermes trading desk as multiple named profiles with a shared team manifest, synchronized identity files, blank model slots, role-specific skills, and optional paper-mode guardrails. Use when the user wants an orchestrator plus specialized trading agents that stay in sync.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [trading, profiles, multi-agent, hermes, paper-trading, orchestration]
    related_skills: [hermes-agent, manual-skill-install-from-github]
---

# Trading Desk Profile Team Setup

Use this when the user wants a persistent Hermes trading desk with multiple agents such as:
- orchestrator
- market researcher
- strategy agent
- risk manager
- portfolio monitor

This skill captures the working pattern for building the desk as native Hermes profiles instead of inventing an external config format.

## Why this approach

Hermes profiles are the clean native abstraction for separate agents because each profile gets its own:
- `config.yaml`
- `.env`
- `SOUL.md`
- memory
- sessions
- skills
- gateway/runtime state

That makes profiles better than an ad hoc JSON file if the goal is real long-lived agent separation.

## Recommended workflow

### 1. Use named Hermes profiles as the agent boundary
Create one profile per agent, usually by cloning the default profile so tools, credentials, and baseline context stay aligned:

```bash
hermes profile create orchestrator --clone --no-alias
hermes profile create market-researcher --clone --no-alias
hermes profile create strategy-agent --clone --no-alias
hermes profile create risk-manager --clone --no-alias
hermes profile create portfolio-monitor --clone --no-alias
```

Why `--clone`:
- copies `config.yaml`, `.env`, and `SOUL.md`
- keeps shared credentials/tool availability consistent
- avoids redoing setup from scratch

Why `--no-alias`:
- avoids creating command wrappers unless the user explicitly wants them

### 2. Blank model/provider fields after cloning
If the user wants to choose models later, explicitly blank these fields in each profile’s `config.yaml`:

```yaml
model:
  default: ''
  provider: ''
  base_url: ''
  api_key: ''

delegation:
  model: ''
  provider: ''
  base_url: ''
  api_key: ''
```

Do not assume cloning is enough if the user requested empty model slots.

### 3. Create a shared team manifest under the Hermes home
Write a durable team source of truth such as:

```text
~/.hermes/teams/trading-desk/TEAM.md
~/.hermes/teams/trading-desk/agents.yaml
```

The manifest should include:
- top-level source-of-truth paths
- shared authority chain
- critical action confirmation boundary
- trading mode (`paper` or `live`)
- execution base URL if relevant
- per-agent role descriptions
- per-agent assigned skills

### 4. Synchronize profile identity files
For each profile, write or update:
- `IDENTITY.md`
- `USER.md`
- `SOUL.md`
- `memories/MEMORY.md`
- `memories/USER.md`

Best practice:
- keep the root `~/.hermes/IDENTITY.md`, `USER.md`, and `SOUL.md` as the desk’s top-level identity
- make each profile `SOUL.md` explicitly defer to the shared identity files and team manifest
- give each profile a specialized role section
- explicitly state that the orchestrator is the final source of truth for desk state

### 5. Add per-profile role files for clarity
Write a small manifest per profile, e.g.:

```text
~/.hermes/profiles/orchestrator/ROLE_SKILLS.yaml
```

Include:
- profile name
- assigned skills
- source-of-truth manifest path

This makes auditing much easier later.

## Suggested role split

### Orchestrator
Use for:
- combining outputs
- enforcing rules
- final decisions
- exchange execution
- order amend/cancel/fill confirmation
- syncing balances and positions
- retries and error handling

Suggested skill set:
- `hermes-agent`
- `native-mcp`
- exchange skill(s)
- market-data/chart skill(s)
- planning + verification skills
- delegation/orchestration skills
- browser skills if execution/monitoring needs UI workflows

### Market Researcher
Use for:
- macro state
- trend structure
- volatility regime
- news/events
- sentiment

Suggested skill set:
- `native-mcp`
- chart/data-view skills
- browser/web research skills
- verification skill

### Strategy Agent
Use for:
- long/short/no-trade
- entry/stop/take-profit
- confidence score
- strategy type

Suggested skill set:
- `native-mcp`
- chart/data-view skills
- relevant market data skill
- verification skill

### Risk Manager
Use for:
- max allocation
- daily loss limit
- exposure control
- R:R rejection
- revenge/overtrading blocks

Suggested skill set:
- `native-mcp`
- exchange skill
- chart/data-view skill
- verification skill
- debugging skill for state/rule conflicts

### Portfolio Monitor
Use for:
- open positions
- unrealized PnL
- stop movement rules
- invalidation alerts
- closure recommendations
- reporting exposure

Suggested skill set:
- `native-mcp`
- exchange skill
- browser/agent-browser if UI monitoring is useful
- verification skill
- debugging skill

## Prune skills per profile
Do not leave every profile with the full global skill set if the user wants role discipline.

Working pattern:
1. Build an explicit assignment map from profile → skill names
2. Resolve source skill directories from `~/.hermes/skills`
3. Replace each profile’s `skills/` directory with only the assigned skills
4. Keep a backup of the previous `skills/` directory before pruning

Useful backup convention:

```text
skills_backup_before_role_prune/
```

## Paper mode guardrails
If the user wants paper trading first, add hard policy guardrails to:
- shared team manifest
- shared team markdown
- orchestrator `SOUL.md`
- risk manager `SOUL.md`
- portfolio monitor `SOUL.md`

Include:
- `mode: paper`
- demo execution base URL only
- explicit list of forbidden live base URLs
- rule that demo balance must be non-zero before execution
- rule that all write actions still require explicit human confirmation
- a hard technical enforcement path, not just persona/policy text

Useful audit file:

```text
~/.hermes/teams/trading-desk/PAPER_MODE.yaml
```

Recommended hard-block pattern:
1. Create a tiny wrapper script such as `~/.hermes/teams/trading-desk/scripts/bitmart_paper_guard.py`
2. Have it load `PAPER_MODE.yaml`
3. Normalize the candidate `base_url`
4. Reject any URL/hostname matching forbidden live BitMart hosts
5. Reject any URL that differs from the configured paper `execution_base_url`
6. Exit non-zero before running the wrapped network command
7. Record the wrapper path in both `PAPER_MODE.yaml` and `agents.yaml`, e.g.:
   - `enforcement_script`
   - `enforcement_mode: hard_block`
   - `required_execution_wrapper`

This is materially better than policy-only instructions because it blocks accidental live execution even if an agent drifts.

## Demo readiness check pattern
For BitMart-style demo trading, do not claim readiness until you verify all of:
1. charting / market-data connection works
2. exchange credentials are present
3. demo endpoint is reachable
4. private read against demo endpoint succeeds
5. demo balance is non-zero

If demo balance is zero, use the documented demo claim/reset endpoint before declaring readiness.

## Safe first dry-run pattern
Before any paper write, run an end-to-end dry run and stop at prepared-order stage:
1. Read demo balance through the hard guard wrapper
2. Read symbol details, depth/top-of-book, fees, open orders, positions, and position mode
3. Size the smallest practical operational test trade, fee-aware
4. Prepare the exact order payload and guarded command stub
5. Save a dry-run artifact (JSON) and prepared order payload to disk
6. Stop before execution unless the user explicitly confirms

A reusable companion artifact is an orchestrator checklist such as:
- market check
- strategy proposal
- risk approval
- execution confirmation
- monitoring loop
- end-of-run log

This gives the desk a deterministic preflight process instead of relying on ad hoc chat reasoning.

## Important findings

- `hermes profile create --clone --no-alias` is the cleanest starting point for multi-agent trading desks.
- Cloning is not enough when the user wants models empty later; blank the model and delegation fields explicitly.
- Profiles should defer back to shared identity files under the active Hermes home so the whole desk stays synchronized.
- A shared `agents.yaml` manifest plus per-profile `ROLE_SKILLS.yaml` files makes the setup inspectable and maintainable.
- Paper-mode guardrails are worth writing into both shared manifests and execution-facing persona files, not just saying them in chat.
- Policy guardrails in manifests/persona files are strong workflow controls, but they do not equal a full source-code-level live-endpoint block. Say this clearly if it matters.

## Verification checklist

Before saying the desk is ready:
- confirm all profile directories exist
- confirm each profile config has the expected blank or assigned model fields
- confirm the team manifest exists
- confirm assigned skills exist in each profile `skills/` folder
- confirm TradingView or equivalent chart connection is live if required
- confirm paper/demo balance is non-zero if paper mode is active
- confirm paper/live guardrail files contain the expected endpoint restrictions

## Output summary format

When done, summarize:
- profiles created
- shared manifest paths
- model slot status
- role-based skill assignments
- paper/live mode status
- what is ready vs what still blocks trading

## Pitfalls

- Do not invent a custom team schema first if Hermes profiles already solve the isolation problem.
- Do not forget to blank model settings after cloning if the user asked for empty model slots.
- Do not leave all profiles with the same bloated skill set if the user requested role-specific skills only.
- Do not declare paper mode ready if the demo account balance is still zero.
- Do not rely only on chat memory for guardrails; write them to files the desk profiles actually load.
