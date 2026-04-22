# Hermes Web

This Next.js app is the starter Mission Control surface for Hermes.

For the full local product stack, use the workspace-root launcher:

```bash
make dev-help
make dev-up
make dev-check
```

That flow starts backend infra, LiteLLM, the Hermes Agent backend/dashboard,
the Hermes API bridge, and this web app in one path.

Current scaffold pages:

- `/` dashboard overview
- `/mission-control` operator workflow placeholder
- `/agents` agent roster placeholder

The current UI is intentionally minimal but production-shaped. It is meant to become the operator control plane rather than a marketing site.
