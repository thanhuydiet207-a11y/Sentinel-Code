"""Task execution adapter with explicit handler resolution and fail-closed validation."""
from __future__ import annotations

from typing import Any

from sentinel_core.task_handler_registry import TaskHandlerRegistry


class TaskExecutionAdapter:
    """Invoke registered handlers and normalize results/errors.

    This adapter is synchronous and deliberately does not schedule workers,
    persist checkpoints, or provide retries. Those are higher-level concerns.
    """

    def __init__(self, registry: TaskHandlerRegistry):
        self.registry = registry

    def execute(self, task: Any, context: dict | None = None) -> dict:
        if not isinstance(task, dict):
            return {"action": "blocked", "reason": "task_invalid"}
        name = task.get("handler")
        version = task.get("handler_version")
        payload = task.get("input", {})
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return {"action": "blocked", "reason": "task_id_invalid"}
        if not isinstance(name, str) or not name:
            return {"action": "blocked", "reason": "handler_name_invalid"}
        if version is not None and not isinstance(version, str):
            return {"action": "blocked", "reason": "handler_version_invalid"}
        if not isinstance(context, dict) and context is not None:
            return {"action": "blocked", "reason": "context_invalid"}
        validation = self.registry.validate_input(name, payload, version)
        if validation.get("action") != "valid":
            return {"action": "blocked", "reason": validation.get("reason", validation.get("action")), "task_id": task_id}
        resolved = self.registry.resolve(name, version)
        if resolved.get("action") != "resolved":
            return {"action": "blocked", "reason": resolved.get("reason", resolved.get("action")), "task_id": task_id}
        handler = resolved["handler"]
        try:
            result = handler(payload, context=context or {})
        except Exception as exc:
            return {"action": "failed", "task_id": task_id, "handler": name, "handler_version": resolved["version"], "error_type": type(exc).__name__, "error": str(exc)}
        return {"action": "completed", "task_id": task_id, "handler": name, "handler_version": resolved["version"], "result": result}
