# Phase 4P.12 — Execution Recovery & Reconciliation

## Scope
Pure, advisory classification of execution receipts against checkpoint events. Does not execute, retry, write checkpoints, or mutate inputs.

## Actions
- `completed`: verified completed receipt and matching completed checkpoint.
- `safe_to_retry`: failed/abandoned execution and explicit `details.side_effects = "none"`, with checkpoint evidence.
- `manual_review`: missing checkpoint or side-effect status confirmed/unknown.
- `blocked`: invalid receipt or receipt/checkpoint status mismatch.

## Safety
Fail closed. A safe-to-retry classification is not authorization to retry; callers must still use workflow retry markers, execution gates, idempotency, and revalidate external state. The classifier cannot prove external side effects did not occur; it trusts explicit receipt details.

## Validation
Unit tests cover safe retry, confirmed/unknown side effects, missing checkpoint, completed reconciliation, mismatches, tampering, and batch decisions. CI must run these tests.
