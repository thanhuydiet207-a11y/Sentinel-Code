# Phase 4P.5 — AI Review Checkpoint Replay

## Change
The remediation workflow now declares `security_review` as a checkpoint stage. When checkpointing is enabled, the security pipeline's normalized review output, findings used downstream, scanner/reviewer evidence, AI adjudication evidence, and stage summaries are persisted as one immutable checkpoint.

On resume, the orchestrator restores this checkpoint and skips the provider pipeline, avoiding duplicate provider requests when a later remediation stage was interrupted.

## Safety and integrity
- Existing workflow input digest still binds the checkpoint to the complete supplied input package and repository digest.
- A changed input package requires a new workflow ID.
- Review output is treated as data and does not grant approval or bypass policy.
- A failed/not-run security review is recorded as its own output and is not represented as a successful review.
- Local checkpoint files remain unsigned and are not protected against concurrent writers; they are integrity-checked but not authenticity-verified.

## Verification
This change was reviewed statically against the orchestrator and checkpoint state API. No local test runner is available through the GitHub connector. CI results must be checked on the pull request before merge.
