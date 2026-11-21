# Phase 4P.11 — Execution Receipts & Audit Reconciliation

## Scope
Introduces pure functions to create and verify execution receipts and reconcile them against workflow checkpoint events. No execution or persistence is performed.

## Receipt fields
- workflow, stage, execution IDs
- approved decision reason
- start/finish timestamps and outcome
- SHA-256 digest of an idempotency key (raw key is never stored)
- details object and receipt digest

## Safety
Receipt creation rejects denied decisions. Receipt digests detect accidental or malicious edits but are not signatures and do not prove authorship. Started receipts with no finish time are reported as abandoned candidates. Reconciliation is advisory and never mutates workflow/checkpoint data.

## Verification
Unit tests cover digest validation, denial, key privacy, abandoned detection, matching and unmatched checkpoint reporting. CI is responsible for running the tests.
