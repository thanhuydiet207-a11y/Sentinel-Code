# Workflow Execution Runtime State Machine

## Scope
This module is a deterministic coordinator/state model. It does not execute user task
handlers or persist events to a database. Persistence, leases, and external side effects
must be supplied by an adapter.

## Lifecycle
- Pending stages may start only when dependencies are satisfied and parallelism allows.
- Running stages must finish with completed, failed, or skipped outcomes.
- Optional deadlines expire running stages into failed.
- Cancellation is terminal and idempotent for this runtime instance.
- Events receive monotonically increasing sequence numbers.

## Safety
Every transition validates stage identity, current state, timestamp, dependency readiness,
and concurrency. Invalid transitions return structured blocked results without mutation.
