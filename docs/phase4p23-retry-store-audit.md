# Phase 4P.23 — Retry Store Consistency Audit

Adds a read-only audit over atomic reservation/job storage. Detects reservations without jobs, jobs without reservations, malformed job JSON, and persisted status versus serialized payload mismatch. The audit does not repair state or execute jobs. It reports counts and findings for operator review.
