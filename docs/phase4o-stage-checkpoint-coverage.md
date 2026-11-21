# Phase 4O — Stage checkpoint coverage

Checkpoint-enabled remediation orchestration now persists reusable outputs for these stages:

- `patch_validation`: validation result and candidate content (when valid)
- `patch_risk`: risk result and stage summary
- `sandbox`: sandbox result and command summaries
- `regression_scan`: comparison result and stage summary
- `provenance`: evidence verification result and stage summary
- `orchestration`: final result

The checkpoint plan is versioned by its declared stage list. Workflows created by earlier phases are not silently migrated; use a new workflow ID.

## Safety boundaries

- Reuse is opt-in through `checkpoint_store` and `workflow_id`.
- The workflow input digest and repository digest must match; state hash-chain and output digests are verified before reuse.
- Stored validation output may include candidate patch content. Store checkpoints in a private directory with restrictive filesystem permissions and treat them as sensitive.
- A cached sandbox result is historical evidence, not proof that current external dependencies, services, or side effects are unchanged. Revalidate external state before relying on it.
- The sandbox is not OS-level isolation. Do not run untrusted commands unless the environment is separately isolated.
- The checkpoint store is local, unsigned, and has no concurrent-writer coordination. Use one writer per workflow.
- The orchestration still runs AI provider review and policy/report assembly on partial resumes unless a completed final orchestration result is available. Provider calls may be repeated.
- This feature does not authorize patch application or merge; human approval remains required.

## Validation

Tests assert that completed checkpointed runs persist validation, risk, sandbox, regression, provenance, and final orchestration outputs and that repeated calls reuse the final result. CI remains the authoritative runtime verification for the PR.
