# Phase 4P.16 — Retry Queue Persistence

## Scope
SQLite adapter persists retry job records and supports transactional enqueue, retrieval, due listing, and cancellation.

## Safety
- Unique job ID enforced by database primary key.
- Enqueue validates queued jobs and commits atomically.
- Cancellation uses `BEGIN IMMEDIATE` and updates only queued jobs.
- Query values are parameterized.
- Storage errors fail closed.
- Caller owns connection lifecycle, backup policy, and SQLite durability configuration.

## Limitations
No worker claim/lease, execution, cross-host queue, retry scheduling timer, or automatic cleanup. Due listing is read-only and does not claim jobs; concurrent workers require Phase 4P.17 leases.
