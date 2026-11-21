# Phase 4M — Orchestrator Checkpointed Result Reuse

The remediation orchestrator now accepts optional `checkpoint_store` and `workflow_id` arguments.

```python
result = run_remediation_orchestration(
    findings_payload, proposal, repository_root,
    policy=policy,
    checkpoint_store=".sentinel-workflows",
    workflow_id="remediation-run-001",
)
```

When checkpointing is enabled, the orchestrator computes a SHA-256 digest over the JSON-serialized inputs (including the resolved repository root and timeout). It creates a workflow with one declared stage, `orchestration`. After a successful return, the complete result object is persisted in the checkpoint. A subsequent call with the same workflow ID and matching inputs verifies the checkpoint and returns the stored result without re-running the orchestration. Reusing the ID with changed inputs is rejected; use a new workflow ID.

## Scope and limitations

This is **completed-result reuse**, not stage-level resume. If the process is interrupted before the final result checkpoint is written, the orchestration may run again from the beginning. This release does not checkpoint AI provider requests, sandbox commands, or individual policy gates, and it cannot safely resume side effects in progress. The single checkpoint output includes the report and audit trail and may contain sensitive evidence; protect the checkpoint directory. State is local, unsigned, and single-writer.
