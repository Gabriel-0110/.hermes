# Trading Desk

This directory contains the source-controlled definition of the Hermes trading desk.

Primary files:
- [`agents.yaml`](./agents.yaml): canonical desk agent roster and role metadata
- [`TEAM.md`](./TEAM.md): desk laws, topology, and operating rules
- [`PAPER_MODE.yaml`](./PAPER_MODE.yaml): paper-trading constraints and mode guidance
- [`ORCHESTRATOR_PAPER_CHECKLIST.md`](./ORCHESTRATOR_PAPER_CHECKLIST.md): operator checklist for paper execution

Subdirectories:
- [`agent_profiles/`](./agent_profiles): per-role desk profile descriptors
- [`skills/`](./skills): shared workflow and policy skill definitions
- [`scripts/`](./scripts): publishable desk support scripts

Local-only:
- `dry-runs/` is intentionally ignored and reserved for operator dry-run artifacts

GitHub publishing rule:
- publish desk definitions, policies, and reusable scripts
- do not publish dry-run outputs, local operator notes, or generated state
