# Deployment

## Local Topology

The starter deployment model is Docker Compose with three core services:

- `postgres`: primary database using a TimescaleDB-enabled Postgres image
- `api`: FastAPI backend service
- `web`: Next.js frontend

## PostgreSQL and TimescaleDB

PostgreSQL is the base transactional database. TimescaleDB is included because Hermes is expected to store time-oriented workloads such as:

- market candles and trade streams
- order book snapshots
- indicator materializations
- portfolio telemetry
- observability series

The local init script enables the extension. Hypertable definitions are intentionally not included yet because domain schemas are still scaffold-level.

## Docker Compose Notes

- the compose file is intentionally dev-friendly and small
- source directories are mounted for local iteration
- the API waits on Postgres health before startup
- Adminer is left commented out as an optional convenience, not a default dependency

## Future Deployment Considerations

- separate worker processes from API ingress
- add secrets management and environment promotion strategy
- isolate paper trading from live execution
- introduce durable queues and replayable workflows
- define backup, restore, and migration procedures
