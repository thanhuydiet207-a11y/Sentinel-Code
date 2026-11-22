# Worker Execution Coordinator

## Scope

WorkerExecutionCoordinator composes the existing RetryWorkerLeaseStore and
TaskExecutionAdapter. It adds a worker-facing API without creating a second
lease table or replacing retry scheduling and persistence.

The coordinator provides expired-lease reclamation followed by due-job
claiming, lease renewal/release/completion, pre-execution ownership checking,
task dispatch with reserved worker/retry context, conditional finalization,
and release of jobs whose dispatch is blocked before the handler runs.

## Usage

Create the queue and lease stores over the same SQLite connection. Register
handlers in TaskHandlerRegistry, wrap it in TaskExecutionAdapter, then
construct WorkerExecutionCoordinator.

A worker calls claim_due(now, worker_id, lease_seconds, limit). For each
claimed item it passes the returned job and lease to execute_claimed(), along
with the task resolved for that job and explicit start/finish timestamps.

The retry job may include task_id; when present, the coordinator checks it
against the task task_id. The task always needs a valid task_id because that
is part of the execution adapter contract.

## Lease and stale-worker behavior

The lease token is opaque and unique per claim. Before invoking a handler,
execute_claimed() renews the lease using that exact token. An unknown, expired,
or superseded token cannot start execution through this API. Completion or
release is also conditional on that token and on the supplied finish time.
If the lease expires during execution or another worker reclaims it,
finalization is rejected.

Long-running handlers require caller-managed heartbeats through renew().
This adapter is synchronous and does not start a heartbeat thread, background
poller, or scheduler. A handler can still perform external side effects before
the final lease check; handlers that mutate external systems must use
idempotency or downstream conditional-write controls. The opaque token is not
a globally monotonic fencing number.

## Outcomes

- completed: handler returned successfully and the job was finalized.
- failed: handler raised and the job was finalized as failed.
- blocked: validation/dispatch was blocked; when safe, the lease is released
  so the job can be tried again after the underlying issue is corrected.
- blocked / lease_finalize_rejected: execution ran, but the worker no longer
  had a valid lease at completion. The coordinator does not overwrite the
  newer lease owner's state.

## Non-goals

This component does not implement retry policy, backoff, dead-letter routing,
automatic heartbeats, parallel worker pools, task lookup, distributed
coordination outside the existing SQLite store, or exactly-once side effects.
