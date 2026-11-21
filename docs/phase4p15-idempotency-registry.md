# Phase 4P.15 — Idempotency Registry Primitives

## Scope
Pure registry operations over caller-owned mapping data. Reservation, transition and verification helpers do not persist data or execute jobs.

## Guarantees
- Store SHA-256 digest of idempotency key, not raw key.
- Bind key digest to canonical execution payload digest.
- Same key and payload reports replay of original reservation.
- Same key with different payload fails closed.
- Explicit state transitions: reserved -> running -> completed/failed; reserved -> failed.
- Transition helper returns a copied registry and does not mutate input.
- Registry verifier detects malformed entries and duplicate execution IDs.

## Limitations
This is not a durable registry and does not provide atomic reservation, locking, transaction isolation, expiry, cross-process coordination, or exactly-once execution. Production callers must provide storage with atomic compare-and-set/unique constraints and re-check execution gates.
