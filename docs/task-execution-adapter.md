# Task Execution Adapter

Synchronous adapter connecting task specifications to the Task Handler Registry.

## Task contract
- `task_id`: non-empty identifier.
- `handler`: registered handler name.
- `handler_version`: optional exact version.
- `input`: payload passed to the handler (defaults to an empty object).

Handlers are invoked as `handler(payload, context=context)`.

## Behavior
- Resolve handler and validate payload before invocation.
- Unknown handlers, version mismatches, validator errors, and invalid task/context fail closed.
- Handler exceptions are normalized to a failed result with task/handler metadata.
- Successful results are normalized to completed results.

## Boundaries
This adapter is synchronous and does not schedule, persist, lease, retry, checkpoint,
or guarantee idempotency. It should be called by the worker layer that will provide those guarantees.
