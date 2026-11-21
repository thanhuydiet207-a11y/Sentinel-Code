# Phase 4P.18 — Recovery & Retry Integration

## Scope
Compose the existing receipt recovery classifier, bounded retry policy, idempotency reservation and scheduler into a pure preparation pipeline.

## Gate order
1. Verify receipt and classify recovery against checkpoint events.
2. Require `safe_to_retry`.
3. Apply attempt limit, retry marker, and idempotency-key policy.
4. Reserve key digest bound to canonical execution payload.
5. Return replay without creating a duplicate retry job.
6. Build retry job only after all gates pass.

## Safety
No registry or queue is mutated. This is a proposal/preparation function; persistence must be transactional by the caller. Before execution, revalidate workflow state, checkpoint, retry marker, registry reservation, and worker lease. It does not guarantee exactly-once external effects.

## Validation
Tests cover successful preparation, side-effect uncertainty, missing marker, key/payload conflict, replay suppression and scheduling errors.
