# Execution Engine Integration Audit

This suite exercises the execution components against one shared in-memory SQLite connection and the actual adapters/stores:

1. RetryQueueStore enqueue and status persistence.
2. RetryWorkerLeaseStore claim and finalization through WorkerExecutionCoordinator.
3. TaskHandlerRegistry resolution and TaskExecutionAdapter invocation.
4. RetryPolicyEngine and RetryRecoveryCoordinator create a linked retry preserving execution identity.
5. Retry attempt succeeds and queue state transitions to completed.
6. Blocked task/job identity mismatch prevents handler invocation and releases the claim.
7. DurableWorkflowRuntime snapshot/event persistence, restoration, and optimistic version conflict.

Run with: python -m unittest tests.test_execution_engine_integration

## Guarantees tested

- Handler calls receive worker and retry context from the coordinator.
- Failed attempt is finalized before retry scheduling.
- Retry job retains execution identity and parent linkage.
- Successful retry reaches completed queue status.
- Dispatch validation prevents mismatched task execution.
- Durable runtime restore reflects persisted stage state and stale writes are rejected.

## Boundaries

These tests are deterministic, local SQLite integration tests, not distributed load tests. They do not prove exactly-once external side effects, multi-process contention under production load, heartbeat scheduling, or end-to-end workflow stage orchestration. The existing components still expose caller-owned scheduling and connection lifecycle.
