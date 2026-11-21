# Phase 4P.19 — Expired Lease Recovery & Fault Injection

## Scope
Recover retry jobs left claimed by a crashed worker after their lease expires. Reclaim runs transactionally and requeues jobs without executing them.

## Safety
- Reclaim only leases expired at the supplied timezone-aware timestamp.
- Use bounded result count.
- Transactionally requeue payload and status, then delete the expired lease.
- Lease tokens use random UUID values to reduce stale-token reuse.
- Stale worker completion is rejected after reclaim.
- Caller must revalidate workflow state, retry policy, idempotency reservation, and side-effect status before execution.

## Fault injection coverage
- Crash after claim.
- Prevent second worker from claiming before expiration.
- Reclaim after expiry and allow another worker to claim.
- Reject stale worker completion.
- Invalid time/limit.
- Non-expired leases remain untouched.

## Limitations
No real process-kill test or external side-effect simulation. SQLite lease operations do not provide fencing for external systems.
