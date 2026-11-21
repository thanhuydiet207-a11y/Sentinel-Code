# Phase 4P.9 — Workflow State Consistency Audit

## Integrity checks added
- Derive workflow status from latest stage checkpoint events and compare against the persisted workflow status.
- Reject completed state unless every declared stage has a latest completed or skipped event.
- Reject failed state when no stage's latest attempt is failed.
- A retry marker is treated as a running attempt; it does not preserve a failed terminal status.
- Validate event semantics: failed events require a non-empty error, completed events cannot contain errors, and skipped/retry events cannot contain outputs. Retry events cannot contain errors.
- Resume planning blocks on any structural, chain, event-semantic, or workflow-status inconsistency.

## Tests
- Tampered running/completed status mismatch blocks resume.
- Failed checkpoint and running workflow mismatch is detected.
- Event semantic violation is detected even when the event hash is recomputed.

## Verification
Tests added; CI must run before merge.
