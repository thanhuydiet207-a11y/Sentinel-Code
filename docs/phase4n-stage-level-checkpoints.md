# Phase 4N — Stage-level checkpoint reuse

When checkpointing is enabled, the orchestrator now declares the stage plan `patch_risk`, `regression_scan`, and `orchestration`. The patch-risk and regression-scan outputs are persisted independently, then reused after state integrity and input-digest verification. The final orchestration result remains a whole-run cache.

The input digest now includes a repository content snapshot (SHA-256 over sorted relative paths and file bytes), excluding `.git`, Python caches, and the configured checkpoint-store directory. This prevents reuse when source files change and prevents the workflow state itself from invalidating the snapshot.

## Scope

This is partial stage-level reuse: patch-risk review and regression comparison are deterministic, local stages. Security review/provider calls, patch validation, sandbox execution, provenance, policy, report, and audit are still executed as part of the whole orchestration unless the final result checkpoint is available. This does not yet resume arbitrary interruption between all stages.

Checkpoint state is local, unsigned, single-writer, and may store sensitive data. Reuse requires identical serialized inputs and repository snapshot. Use a new workflow ID after changing inputs or source files.
