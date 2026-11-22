# Durable Workflow Runtime Store

SQLite persistence for workflow execution snapshots and append-only lifecycle events.

## API
- `create(execution_id, workflow_id, snapshot, status, at, events=[])`: create version 1.
- `load(execution_id, include_events=False)`: load snapshot/version; optionally ordered event journal.
- `save(execution_id, expected_version, snapshot, status, at, events=[])`: compare-and-swap snapshot and append events in one transaction.
- `list_recoverable(limit=100)`: list ready/running execution metadata for recovery orchestration.

## Guarantees
- Snapshot update and event append are transactional.
- Optimistic version checks reject stale writers.
- Duplicate event sequences fail and roll back the snapshot update.
- Input/status/timestamp validation fails closed.
- Event journal is append-only through this API.

## Boundaries
This adapter does not automatically restore a runtime object, execute handlers, reclaim worker leases,
or resume side effects. Recovery callers must load the snapshot, validate its schema, coordinate leases,
and use idempotent task adapters before resuming. The caller owns connection lifecycle and durability settings.
