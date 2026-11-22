# Retry Policy and Crash Recovery

RetryPolicyEngine is a deterministic policy component. It classifies permanent failures and attempt exhaustion as stop conditions, otherwise calculates capped exponential delay with bounded jitter and an optional Retry-After minimum.

RetryRecoveryCoordinator plans a new schema-1 queue job preserving workflow, stage, execution identity and task ID, and links it to the failed job via parent_job_id. It persists through RetryQueueStore.enqueue; duplicate IDs and storage failures are surfaced as blocked, not treated as success.

## Usage

- Construct RetryPolicyEngine with max_attempts, base_delay_seconds, max_delay_seconds and jitter_ratio.
- Call decide with attempt_number, failure_kind, timestamp, and optional retry_after_seconds/jitter_sample.
- Call recover to plan and enqueue a retry. Use a unique retry_job_id from the caller.

Jitter is deterministic when the caller supplies jitter_sample (0..1); this keeps tests and audit records reproducible. The caller should generate an unbiased sample in production. attempt_number represents the attempt that failed; the retry job receives attempt_number + 1.

## Crash recovery boundary

The coordinator persists retry jobs in the existing queue. Worker lease expiry/reclaim remains responsible for returning abandoned claimed jobs to the queue. The queue's unique job_id protects against duplicate persistence, but this module does not create an idempotency ledger for external side effects and cannot guarantee exactly-once execution. Handlers should use stable idempotency keys derived from execution_id and task identity, and external systems should enforce them where possible.

## Non-goals

No automatic classification of arbitrary exceptions, background scheduler, dead-letter queue, or external side-effect transaction is implemented. The caller supplies failure_kind, retry-after, retry job ID, and jitter sample.
