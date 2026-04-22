# Hermes Web

This Next.js app is the operator-facing Mission Control surface for Hermes.
It is not the trading runtime.

In the current architecture:

- `hermes-agent/backend` is the runtime source of truth
- `hermes/apps/api` is the bridge/product API
- `hermes/apps/web` is the operator shell over those surfaces

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

The current UI is intentionally minimal but production-shaped. It is meant to
become the operator control plane for reviewing proposals, execution state,
portfolio state, and runtime safety controls. It should not be read as evidence
that Hermes already has a unified or production-mature trading runtime.
