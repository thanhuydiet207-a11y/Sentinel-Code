"""Adapter that persists and restores WorkflowExecutionRuntime instances."""
from __future__ import annotations

from typing import Any

from sentinel_core.workflow_runtime import WorkflowExecutionRuntime
from sentinel_core.workflow_runtime_store import DurableWorkflowRuntimeStore


_VALID_STAGE_STATES = {"pending", "running", "completed", "failed", "cancelled", "skipped"}


def _runtime_snapshot(runtime: WorkflowExecutionRuntime) -> dict:
    return {
        "stages": list(runtime.stages),
        "dependencies": runtime.dependencies,
        "max_parallelism": runtime.max_parallelism,
        "stage_states": dict(runtime.stage_states),
        "deadlines": dict(runtime.deadlines),
        "cancelled": runtime.cancelled,
    }


class DurableWorkflowRuntime:
    """Versioned persistence wrapper; callers still own task execution and lease checks."""

    def __init__(self, store: DurableWorkflowRuntimeStore, execution_id: str, workflow_id: str, runtime: WorkflowExecutionRuntime, version: int, event_count: int):
        self.store = store
        self.execution_id = execution_id
        self.workflow_id = workflow_id
        self.runtime = runtime
        self.version = version
        self.event_count = event_count

    @classmethod
    def create(cls, store: DurableWorkflowRuntimeStore, execution_id: str, workflow_id: str, runtime: WorkflowExecutionRuntime, at: str) -> dict:
        snapshot = _runtime_snapshot(runtime)
        status = runtime.snapshot()["action"]
        if status not in {"ready", "running", "completed", "failed", "cancelled", "blocked"}:
            status = "blocked"
        result = store.create(execution_id, workflow_id, snapshot, status, at, runtime.events)
        if result.get("action") != "created":
            return result
        return {"action": "created", "durable_runtime": cls(store, execution_id, workflow_id, runtime, result["version"], len(runtime.events))}

    @classmethod
    def restore(cls, store: DurableWorkflowRuntimeStore, execution_id: str) -> dict:
        loaded = store.load(execution_id, include_events=True)
        if loaded.get("action") != "loaded":
            return loaded
        snapshot = loaded.get("snapshot")
        required = {"stages", "dependencies", "max_parallelism", "stage_states", "deadlines", "cancelled"}
        if not isinstance(snapshot, dict) or not required.issubset(snapshot):
            return {"action": "blocked", "reason": "snapshot_schema_invalid"}
        if not isinstance(snapshot["stage_states"], dict) or set(snapshot["stage_states"]) != set(snapshot["stages"]):
            return {"action": "blocked", "reason": "stage_state_invalid"}
        if any(state not in _VALID_STAGE_STATES for state in snapshot["stage_states"].values()):
            return {"action": "blocked", "reason": "stage_state_invalid"}
        if not isinstance(snapshot["deadlines"], dict) or not isinstance(snapshot["cancelled"], bool):
            return {"action": "blocked", "reason": "snapshot_fields_invalid"}
        runtime = WorkflowExecutionRuntime(snapshot["stages"], snapshot["dependencies"], snapshot["max_parallelism"])
        if runtime.invalid:
            return {"action": "blocked", "reason": "workflow_graph_invalid"}
        runtime.stage_states = dict(snapshot["stage_states"])
        runtime.deadlines = dict(snapshot["deadlines"])
        runtime.cancelled = snapshot["cancelled"]
        events = loaded.get("events", [])
        if not isinstance(events, list) or [event.get("sequence") for event in events] != list(range(1, len(events) + 1)):
            return {"action": "blocked", "reason": "event_journal_invalid"}
        runtime.events = events
        return {"action": "restored", "durable_runtime": cls(store, execution_id, loaded["workflow_id"], runtime, loaded["version"], len(events))}

    def persist(self, at: str) -> dict:
        snapshot = _runtime_snapshot(self.runtime)
        status = self.runtime.snapshot()["action"]
        new_events = self.runtime.events[self.event_count:]
        result = self.store.save(self.execution_id, self.version, snapshot, status, at, new_events)
        if result.get("action") == "saved":
            self.version = result["version"]
            self.event_count = len(self.runtime.events)
        return result

    def snapshot(self) -> dict:
        return {"execution_id": self.execution_id, "workflow_id": self.workflow_id, "version": self.version, "runtime": self.runtime.snapshot()}
