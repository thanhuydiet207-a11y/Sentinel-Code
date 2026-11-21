# Phase 4P.25 — Retry Queue Health Assessment

## Scope
Pure function that evaluates operational snapshots against configurable thresholds and emits healthy/warning/critical status with structured findings.

## Default policy
- Due queued backlog above 100: warning.
- Any expired worker lease: critical.
- Active leases above 1000: warning.

## Safety
No DB access, no mutation, no automatic remediation. Thresholds can be supplied by the caller. Invalid snapshots or thresholds fail closed.

## Limitations
Thresholds are defaults, not tuned production SLOs. The assessor does not emit metrics or alerts.
