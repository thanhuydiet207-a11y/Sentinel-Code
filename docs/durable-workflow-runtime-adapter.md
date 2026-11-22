# Durable Workflow Runtime Adapter

Connects `WorkflowExecutionRuntime` to `DurableWorkflowRuntimeStore`.

## Operations
- `create(...)`: persist initial runtime state and event journal.
- `restore(...)`: validate stored snapshot and reconstruct runtime coordinator.
- `persist(at)`: compare-and-swap the snapshot and append only new runtime events.
- `snapshot()`: expose runtime snapshot plus execution identity/version.

## Recovery contract
Restore validates graph, stage states, required snapshot fields, and contiguous event sequence.
Concurrent adapters are protected by store version checks. A stale adapter receives a conflict
and must reload before attempting further persistence.

## Not included
This adapter does not execute tasks, recover worker leases, decide whether external effects
are safe to replay, or automatically retry stale writes.
