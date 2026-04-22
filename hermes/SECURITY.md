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
- maintain explicit approval and override records

## Current State

This repository is a starter scaffold. It does not yet implement a complete security model, operator auth layer, or production secret management system. Treat all future execution, exchange connectivity, and model-provider integrations as high-risk surfaces that require dedicated review.
