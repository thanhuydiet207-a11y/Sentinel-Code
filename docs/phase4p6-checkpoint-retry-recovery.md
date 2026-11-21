# Phase 4P.6 — Failed Checkpoint Retry Recovery

## Behavior
- A failed stage remains immutable in the checkpoint chain.
- `retry_stage()` appends a hash-chained retry marker only when the latest attempt for that stage is failed.
- The workflow transitions back to `running` after a retry marker.
- A subsequent stage checkpoint records the new attempt result; successful completion is based on the latest stage result.
- Resume planning reports the latest attempt per stage and only marks a running workflow without unresolved failures as safe to resume.
- Completed or skipped stages cannot be retried. Retry markers cannot be forged through `checkpoint_stage()`.
- Retry operations first validate the checkpoint chain and refuse corrupted state.

## Limits
This is a local JSON checkpoint store. Atomic file replacement reduces partial-write risk, but the implementation does not coordinate concurrent writers or provide signed authenticity. Callers must ensure one writer per workflow and revalidate external side effects before retrying.

## Verification
New unit tests cover failed-stage retry, latest-attempt planning, completed output retrieval, invalid retry requests, and hash-chain tampering. Tests have not been run through this GitHub connector; CI must validate before merge.
