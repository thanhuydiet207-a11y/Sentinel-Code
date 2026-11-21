# Retry Worker Lifecycle Hardening

This track strengthens lease ownership and job-state transitions across claim, renew,
release, completion, and expired-lease reclamation.

## Safety properties
- Each claimed job receives a distinct lease fencing token.
- Claiming validates persisted payload shape and rolls back the whole batch on malformed data.
- Renew, release, and completion verify worker/token ownership, lease expiry, and claimed job state.
- Release and completion update the job and delete the lease in one transaction.
- Missing or malformed job payloads fail closed without silently discarding a valid lease.
- Reclamation requeues only expired leases with valid claimed-job payloads.
- Expired orphan leases are removed with an explicit diagnostic result.

## Tests
The lifecycle tests cover multi-job token uniqueness, state mismatch, missing jobs,
malformed payloads, transactional behavior, and expired lease recovery.
