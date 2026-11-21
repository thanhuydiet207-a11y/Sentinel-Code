# Phase 4P.14 — Retry Scheduler Decisions

## Scope
Pure helpers build retry job records, evaluate due-time status, and cancel queued jobs. No worker, timer, persistence, or execution is included.

## Job lifecycle
- `queued`: created from an approved retry policy.
- `due`: current time is at or after due time.
- `cancelled`: cancellation requested or job cancelled.

## Safety
- Only `retry_scheduled` policy results can create a job.
- Timestamp strings must include timezone.
- Negative delay/jitter and invalid inputs fail closed.
- Cancellation returns a copy and does not mutate source job.
- Due status is advisory; execution must re-check workflow state, retry marker, idempotency and recovery policy.

## Limitations
No persistent queue, worker lease, race prevention, jitter generation, or automatic execution is implemented. Jitter is an explicit caller-supplied non-negative value.
