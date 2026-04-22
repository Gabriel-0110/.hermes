# Security

## Reporting

Do not open public issues for security vulnerabilities that could expose credentials, accounts, trade paths, or infrastructure details. Report security concerns privately to the maintainers through the designated security contact for the deployment environment using this scaffold.

## Scope

Security-sensitive areas for Hermes include:

- API keys and exchange credentials
- operator authentication and authorization
- model prompt and context leakage
- webhook verification
- order execution and approval bypass
- audit trail integrity
- database access and backup handling

## Secure Development Expectations

- keep secrets out of source control
- prefer environment-based configuration with rotation support
- log carefully and avoid writing sensitive payloads by default
- gate execution paths behind policy evaluation
- gate live execution behind explicit runtime mode and unlock requirements
- keep a kill switch and approval queue in the control path
- maintain explicit approval and override records

## Current Control Boundaries

The current Hermes control path is implemented across a split runtime:

- `hermes-agent/backend` is the source of truth for proposal normalization,
  risk/policy decisions, live-paper mode checks, kill switch reads, approval
  queue behavior, execution requests/results, observability, and portfolio
  state
- `hermes/apps/api` is a bridge layer that exposes those controls and states
- `hermes/apps/web` is an operator-facing shell over the bridge

Current live order placement is intended to be blocked unless all required
conditions are satisfied:

- trading mode is `live`
- live trading is explicitly enabled
- acknowledgment phrase is present
- kill switch is inactive
- approval requirements are satisfied where configured

## Current State

This repository still does not implement a complete security model, operator
auth layer, or production secret management system. Treat exchange execution,
approval state, bridge authentication, and model-provider integrations as
high-risk surfaces that require dedicated review. Current controls improve the
runtime path, but they do not make Hermes production-ready for unattended live
trading.
