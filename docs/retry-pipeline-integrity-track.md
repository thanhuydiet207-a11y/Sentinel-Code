# Retry Pipeline Integrity Track

## Scope
This read-only audit validates consistency across the durable retry queue, worker leases,
idempotency reservations, and atomic retry-job records.

## Invariants checked
- Queue payload job ID and status agree with indexed database columns.
- Claimed retry jobs have leases; leases reference existing claimed jobs.
- Atomic retry jobs have matching reservations.
- Atomic job JSON identity and status match indexed columns.
- Malformed JSON and unexpected payload shapes are reported as findings.

## Safety
The audit performs SELECT-only operations and does not reclaim leases, rewrite payloads,
delete records, expose idempotency keys, or attempt remediation. Findings are structured
codes and job IDs. Missing tables and SQLite failures fail closed.

## Usage
Call `audit_retry_pipeline(connection)` with the SQLite connection shared by the retry
stores. A valid result has `action=audited` and `valid=true`; callers should treat
`valid=false` as a diagnostic signal and require explicit recovery procedures.

## Input validation included in this track

The durable retry queue rejects blank identifiers, invalid or timezone-naive ISO timestamps, and invalid attempt numbers (including booleans). Query timestamps and cancellation timestamps must also be timezone-aware. SQLite write failures return a structured blocked result rather than escaping from enqueue.
