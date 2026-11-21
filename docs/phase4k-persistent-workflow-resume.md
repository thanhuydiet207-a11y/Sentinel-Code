# Phase 4K — Persistent Workflow Checkpoints and Resume

Phase 4K provides a local persistent state engine for callers that execute long remediation workflows. It records an ordered stage plan, immutable checkpoints, stage outputs, output digests, and a hash-chained checkpoint history. It computes a resume plan without rerunning completed stages.

## CLI

Create a workflow (input digest must be SHA-256 of the canonical input package or another stable caller-defined representation):

```bash
sentinel-security workflow-start \
  --store .sentinel-workflows \
  --workflow-id remediation-2026-001 \
  --stages validate risk sandbox regression provenance policy report \
  --input-digest <64-hex-sha256>
```

Record a completed stage and its JSON output:

```bash
sentinel-security workflow-checkpoint \
  --store .sentinel-workflows \
  --workflow-id remediation-2026-001 \
  --stage validate --status completed \
  --output validation-result.json
```

Check integrity and determine what remains:

```bash
sentinel-security workflow-resume-plan \
  --store .sentinel-workflows \
  --workflow-id remediation-2026-001 \
  --input-digest <same-input-sha256>
```

Verify a copied state file:

```bash
sentinel-security workflow-verify workflow-state.json
```

## State semantics

- `completed`: checkpointed stage output is retained in state and protected by an output digest and event hash chain.
- `failed`: failure and error string are recorded. This version blocks automatic resume for failed workflows; start a new workflow ID after fixing the failure.
- `skipped`: stage is explicitly recorded as skipped and excluded from the remaining-stage plan.
- Duplicate checkpoints are rejected; checkpoints are immutable.
- Input digest mismatch or corrupted checkpoint chain blocks the resume plan.
- State writes use a temporary file, flush/fsync, and atomic replace.

## Security and limitations

The checkpoint file contains output payloads, which may include sensitive data. Protect the store with appropriate filesystem permissions and do not commit it to source control. The state is local, unsigned, and not immutable storage; a user who can modify the file can replace the state and hashes. Hash chaining detects accidental/tamper changes only when the expected chain/head is retained independently. Concurrent writers are not coordinated. This module is a persistence primitive; it does not yet automatically wrap every Phase 4I orchestrator stage or revalidate external side effects during resume. Before continuing, callers must confirm input digest and re-check any external side effects (scanner/provider calls, remote artifacts, filesystem state).
