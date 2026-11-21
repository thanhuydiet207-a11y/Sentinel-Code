# Phase 4P.4 — AI Security Review and Resume Replay Audit

## Scope
Static integration review of the merged remediation orchestrator, checkpoint state, provider adapters, and security pipeline. This review is not a runtime test.

## Finding: AI review occurs before checkpoint restoration is used for stage results
In `run_remediation_orchestration`, provider security review is invoked before the patch-validation/risk/sandbox/regression/provenance checkpoint reuse blocks. The checkpoint stage plan does not include security review or adjudication. A process interruption after provider calls but before the final orchestration checkpoint can therefore repeat external provider requests on resume.

### Impact
- Provider quota and cost may be duplicated.
- Provider outputs may differ between attempts.
- The workflow lacks a durable record of the AI review stage's completion before later remediation stages.
- Resume behavior is not exactly-once for provider requests.

### Recommendation
Add explicit checkpoint stages for security review and adjudication. Persist normalized outputs and provider metadata, keyed by the complete input digest. Restore them before making provider calls. Use a durable idempotency key where provider support exists; otherwise document at-least-once semantics. Ensure failed provider stages are represented as completed checkpoints containing a failure result only if the workflow design permits retry policy to be encoded separately—do not mark a failed stage as successful merely to advance state.

## Other observations
- Provider adapters validate response IDs and aggregate review schema before accepting results.
- The provider transport caps response reads and redacts HTTP response bodies on errors.
- Gemini API key is currently placed in query parameters; transport error messages intentionally do not include the URL. Avoid logging URLs and ensure proxy/access logs redact query credentials.
- Checkpoint state is local, unsigned, and not concurrency-coordinated; its hash chain detects accidental/tampered data only when verification is performed and does not provide trusted authenticity.
- The orchestrator reports that scanner executables are not launched and sandbox is not OS-level isolation; these limitations are surfaced in result output.

## Verification
Static inspection only. No local test execution was available through the GitHub connector. No runtime behavior or CI result is claimed.
