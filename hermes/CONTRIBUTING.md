# Contributing

## Principles

Hermes is intended to be a production-oriented trading system. Contributions should optimize for clarity, auditability, and operational safety over speed of feature accumulation.

## Development Workflow

1. Create a focused branch.
2. Install dependencies with `make setup`.
3. Run local validation with `make lint` and `make test`.
4. Keep changes scoped and documented.
5. Update docs when changing architecture, configuration, or operator workflows.

## Coding Standards

- Python uses `ruff` for linting and formatting.
- TypeScript uses Next.js linting and Prettier.
- Prefer small modules with explicit boundaries.
- Label placeholders and future work with `TODO:` instead of implying implementation exists.

## Commit Expectations

- Write descriptive commits.
- Keep refactors separate from behavior changes where practical.
- Do not commit secrets, API keys, or local `.env` files.

## Pull Request Checklist

- explain the operational impact
- note any new environment variables
- describe testing performed
- call out risk or policy implications
- update docs if architecture or runtime behavior changed

## Safety

Any change that touches trade execution, position sizing, risk controls, model routing, or external account connectivity should be reviewed with extra scrutiny. The scaffold in this repository is not sufficient for live trading without additional hardening.
