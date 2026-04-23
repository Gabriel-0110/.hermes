# Hermes Runtime Delivery Plan

## Goal

Make the current Hermes runtime conform to the target architecture by ensuring:

- the orchestrator focuses on market/result decisions only
- execution, portfolio movements, and operator-visible changes are persisted to canonical database tables
- audit trails are correlation-aware and queryable end-to-end
- notifications are emitted by risk, monitoring, or Mission Control paths
- TradingView and dashboard surfaces can visualize persisted movements and replay timelines

## Phased action plan

### Phase 1 — Persistence and audit backbone

1. Harden the execution observability contract so execution events persist complete context:
   - `symbol`
   - `payload`
   - `correlation_id`
   - `workflow_run_id`
   - `event_id`
2. Add a canonical `movement_journal` table for:
   - order submissions
   - fills / simulated fills
   - blocked orders
   - failed orders
   - portfolio balance and position changes
3. Add repository and service methods to query movement history by:
   - correlation ID
   - workflow run
   - symbol
   - account
4. Include movement entries in timeline APIs and dashboard snapshots.

### Phase 2 — Runtime wiring

1. Record execution outcome movements from the execution worker.
2. Record portfolio projection/sync movements from the position manager.
3. Ensure notifications retain correlation IDs and are traceable to decisions and executions.
4. Route incident and alert generation through risk / monitoring flows rather than orchestrator-only paths.

### Phase 3 — Mission Control and visualization

1. Expose movement journal endpoints in the Hermes Agent API.
2. Add Mission Control panels for:
   - movement journal
   - execution timeline
   - correlation trace drill-down
3. Feed TradingView overlays from persisted movement records.
4. Add replay / annotation support keyed by correlation ID and symbol.

### Phase 4 — Hardening

1. Add tests for end-to-end correlation integrity.
2. Add notification retry / escalation assertions.
3. Add portfolio reconciliation checks against execution movements.
4. Add smoke tests for TradingView webhook -> workflow -> execution -> movement journal -> timeline.

## Current sprint

### In progress now

- implement the persistence backbone for execution context and movement journal
- expose movement history through observability services and API endpoints
- add regression coverage for the new storage contract

## Definition of done for the first slice

- execution persistence accepts and stores full context without runtime argument mismatches
- movement journal rows are written for execution outcomes
- movement history is queryable from the API
- tests cover execution event + movement timeline persistence
