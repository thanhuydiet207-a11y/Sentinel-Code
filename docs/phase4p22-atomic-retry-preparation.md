# Phase 4P.22 — Atomic Retry Preparation

## Scope
SQLite transaction stores an idempotency reservation and retry job together. A unique key digest binds payload digest and execution ID to the job.

## Safety
- `BEGIN IMMEDIATE` protects reservation and job creation.
- Unique key digest, execution ID, job ID, and reservation/job relationship.
- Replay returns the original reservation without creating another job.
- Payload conflict blocks.
- Job insert failure rolls back reservation.
- Raw key is never stored.

## Limitations
No worker lease integration in this store, execution, distributed transactions, retention or external side-effect guarantee.
