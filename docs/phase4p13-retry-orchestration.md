# Phase 4P.13 — Retry Orchestration Policy

## Scope
A pure retry-policy evaluator. It calculates bounded exponential backoff and returns a decision; it does not sleep, schedule jobs, execute stages, or mutate workflow state.

## Safety gates
- Recovery classification must be `safe_to_retry`.
- Retry marker must be present.
- Idempotency key must be present.
- Attempt number must be below configured maximum.
- Invalid policy inputs fail closed.
- `manual_review`, `blocked`, and `completed` recovery decisions are never retried.

## Backoff
Delay is `min(base_delay * 2^(attempt_number - 1), max_delay)`. Defaults: base 30 seconds, cap 300 seconds, maximum 3 attempts.

## Limitations
No jitter, persistence, scheduler integration, or real retry execution is implemented. The returned `retry_scheduled` action is advisory only.
