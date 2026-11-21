# Phase 4P.7 — Checkpoint Concurrency and Crash Safety

## Changes
- Writers for a workflow serialize through an exclusive local lock file, protecting read-modify-write sequences in create, checkpoint, and retry operations.
- Lock acquisition is bounded (3 seconds); a busy lock fails closed without modifying workflow state.
- Lock metadata includes process ID and timestamp. Stale locks are deliberately not removed automatically; inspect the owner and remove the lock manually only when safe.
- Atomic replacement writes and fsyncs a temporary file before replace; directory fsync is attempted after replacement where supported.
- Tests cover concurrent distinct-stage writes, lock timeout/no mutation, and lock cleanup.

## Limits
- Lock files coordinate processes sharing a local filesystem with reliable exclusive-create semantics. Network filesystems may not provide equivalent guarantees.
- A process crash can leave a lock file; recovery is manual to avoid deleting an active lock based on unreliable PID/age heuristics.
- Atomic replacement prevents readers from seeing partial JSON, but does not make external side effects transactional.

## Verification
Tests added; execution must be confirmed by GitHub Actions.
