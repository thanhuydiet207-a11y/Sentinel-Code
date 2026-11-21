# Phase 4P.21 — Durable Idempotency Store

## Scope
SQLite-backed reservation registry with unique key digest and unique execution ID, transactional reservation, replay/conflict detection, and guarded status transitions.

## Safety
- Raw idempotency keys are never stored.
- Key digest binds to canonical payload digest.
- `BEGIN IMMEDIATE` serializes reservations.
- Database uniqueness constraints prevent duplicate key/execution records.
- Replay returns original execution record; conflicting payload fails closed.
- Status transitions are explicit and terminal states cannot be reopened.

## Limitations
No multi-database transaction with retry queue, expiry/retention, distributed database guarantees, or external exactly-once side-effect guarantee.
