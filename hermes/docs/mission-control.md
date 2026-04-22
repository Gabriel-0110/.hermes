# Mission Control

Mission Control is the human-facing control plane for Hermes.

## Responsibilities

- surface system state and agent activity
- present trade proposals and approval queues
- route notifications and exception alerts
- provide observability, replay, and review context
- make human override paths explicit

## Operator Channels

Hermes is designed to support operator interaction through:

- web/dashboard
- Slack
- Telegram
- CLI

The dashboard is the primary rich interface. Slack and Telegram are expected to support alerts, acknowledgements, and lightweight approvals. CLI support remains useful for development, debugging, and incident handling.

## Future Implementation Notes

- approval workflows must be auditable
- notifications should include severity, source, and suggested action
- operator notes should be attached to proposal and incident records
- Mission Control should expose both real-time and historical views
