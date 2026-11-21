# Phase 4P.20 — End-to-End Retry Pipeline Audit

## Scope
End-to-end tests compose execution receipt verification, checkpoint recovery, retry policy gates, idempotency reservation, retry scheduling, SQLite persistence, worker leases, completion, and expired-lease recovery.

## Coverage
- Prepare and persist a retry job, claim it, and finalize it.
- Simulate worker crash via lease expiration, reclaim, and claim by another worker.
- Reject stale worker finalization after reclaim.
- Verify receipt/checkpoint reconciliation.

## Limitations
Tests use in-memory SQLite and controlled timestamps; they do not exercise external side effects, multi-host coordination, actual worker processes, or production filesystem/database durability.
