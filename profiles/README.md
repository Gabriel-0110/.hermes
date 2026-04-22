# Profiles

This folder contains the publishable role-profile definitions for the Hermes trading desk.

Tracked in GitHub:
- `*/config.yaml`
- `*/IDENTITY.md`
- `*/ROLE_SKILLS.yaml`
- `*/SOUL.md`
- `*/TEAM.md`
- `*/USER.md`
- [`profiles/.gitignore`](./.gitignore)

Not tracked:
- local secrets such as `.env`, `auth.json`, and `auth.lock`
- runtime databases and state files
- gateway/session/cache artifacts
- generated workspace directories such as `cache/`, `logs/`, `sandboxes/`, `sessions/`, and `workspace/`

Current role profiles:
- `orchestrator`
- `market-researcher`
- `portfolio-monitor`
- `risk-manager`
- `strategy-agent`

GitHub readiness rule:
- treat this folder as source-controlled profile definitions plus local runtime leftovers
- if a new file is required for sharing or review, add an allowlist entry to [`profiles/.gitignore`](./.gitignore)
- do not commit live credentials, local auth state, or profile runtime output
