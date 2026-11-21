# Phase 4P.17 — Worker Lease & Concurrency

## Scope
SQLite lease primitives claim due queued jobs transactionally, renew/release leases, and finalize jobs when lease ownership is valid.

## Safety
- Claim uses `BEGIN IMMEDIATE` and conditional status update.
- A job can be claimed only while queued.
- Worker identity and lease token are required for renew/release/finalize.
- Expired leases cannot be renewed, released, or finalized by this API.
- Failed storage operations roll back and fail closed.

## Limitations
No automatic reclaim of expired claimed jobs, worker process, execution, fencing token across external side effects, or heartbeat. Expired leases need a later recovery/requeue policy. A lease token is ownership validation, not external exactly-once guarantee.
