# Phase 4P.10 — Resume Execution Safety

## Scope
This phase adds a fail-closed decision API; it does not run arbitrary workflow stages.

## API
`stage_execution_decision(store, workflow_id, stage, input_digest, side_effecting=False, idempotency_key=None)`

The gate verifies:
- checkpoint structure, hash chain, output digests, and status consistency;
- input digest matches the persisted workflow;
- requested stage exists and workflow is running;
- completed/skipped stages are not executed again;
- failed stages require an explicit retry marker;
- earlier stages are completed or skipped before a later stage can execute;
- side-effecting execution requires a caller-provided idempotency key.

## Safety
The API returns an allow/deny decision and reason. It does not invoke commands, scanners, providers, or remediation. The caller must pass the idempotency key through to the downstream system; merely supplying it here does not guarantee exactly-once external effects.

## Tests
Covers terminal stage skip, ordering guard, idempotency-key requirement, input mismatch, and corrupt checkpoint blocking.
