# Dependency-aware Workflow Execution Planner

## Purpose
Create a deterministic execution plan for a workflow's stages based on dependencies
and the latest checkpoint state. This is a planning layer: it does not run tasks,
write checkpoints, launch processes, or mutate workflow state.

## Features
- Validate stage identifiers and dependency declarations.
- Reject unknown, duplicate, self, and cyclic dependencies.
- Compute a deterministic topological order.
- Identify ready, waiting, failed/blocked, terminal, and remaining stages.
- Group ready stages into bounded execution waves using max_parallelism.
- Treat a latest retry marker as a runnable attempt after dependencies are satisfied.

## API
`build_execution_plan(stages, dependencies=None, checkpoints=None, max_parallelism=4)`

Invalid graphs and checkpoint inputs fail closed with a structured blocked result.
The planner is advisory; an executor must re-check state, lease ownership, cancellation,
and idempotency immediately before executing side-effecting work.
