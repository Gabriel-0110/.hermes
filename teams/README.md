# Teams

This folder contains source-controlled Hermes team definitions.

Purpose:
- define team-level operating models separate from runtime code
- publish desk manifests, policies, role descriptors, and shared workflow skills
- keep local-only dry runs and operator artifacts out of Git

Tracked here:
- team manifests
- desk policy documents
- agent profile descriptors
- publishable scripts
- shared skill YAMLs

Not tracked here:
- local dry-run outputs
- operator-only runtime artifacts
- any future team-local secrets or generated state

Current published team:
- `trading-desk`

Layout:
- [`trading-desk/`](./trading-desk):
  the current five-agent trading desk definition
