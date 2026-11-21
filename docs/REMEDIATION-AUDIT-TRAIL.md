# Remediation Audit Trail (Phase 4G)

Build a hash-chained event record:

    python3 -m sentinel_core audit-trail events.json --output audit.json
    python3 -m sentinel_core verify-audit-trail audit.json --output verification.json
    python3 -m sentinel_core audit-lifecycle events.json --output lifecycle.json

Events require a timestamp, type, and optional object payload. Supported event types cover creation, finding selection, AI review, patch proposal/validation, risk assessment, sandbox, scans, reports, evidence sealing/verification, approval request, approval/rejection, and closure.

Each event hash binds its contents and previous event hash. Lifecycle checks detect missing prerequisites for approval/closure. The caller supplies events; this CLI does not execute remediation steps or enforce access controls.

Hash chaining detects edits/reordering relative to the chain but is not cryptographic authenticity: no signing key, immutable storage, trusted timestamp, or external anchoring is included.
