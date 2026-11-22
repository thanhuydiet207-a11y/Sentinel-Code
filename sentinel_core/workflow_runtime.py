"""Deterministic workflow execution lifecycle state machine."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sentinel_core.workflow_execution import build_execution_plan


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class WorkflowExecutionRuntime:
    """State coordinator for stages; task handlers and external effects are injected elsewhere."""

    def __init__(self, stages: list[str], dependencies: dict | None = None, max_parallelism: int = 4):
        self.stages = list(stages) if isinstance(stages, list) else stages
        self.dependencies = dependencies or {}
        self.max_parallelism = max_parallelism
        self.stage_states = {stage: "pending" for stage in self.stages} if isinstance(self.stages, list) else {}
        self.deadlines: dict[str, str] = {}
        self.cancelled = False
        self.events: list[dict] = []
        self.created_at = None
        self._initial_plan = build_execution_plan(self.stages, self.dependencies, max_parallelism=max_parallelism)
        if self._initial_plan.get("action") == "blocked":
            self.invalid = self._initial_plan
        else:
            self.invalid = None

    def _event(self, event_type: str, stage: str | None, at: str, details: dict | None = None) -> dict:
        event = {"sequence": len(self.events) + 1, "type": event_type, "stage": stage, "at": at, "details": details or {}}
        self.events.append(event)
        return event

    def snapshot(self) -> dict:
        running = [stage for stage, state in self.stage_states.items() if state == "running"]
        terminal = all(state in {"completed", "failed", "cancelled", "skipped"} for state in self.stage_states.values())
        if self.invalid:
            action = "blocked"
        elif self.cancelled:
            action = "cancelled"
        elif terminal:
            action = "completed" if all(state in {"completed", "skipped"} for state in self.stage_states.values()) else "failed"
        elif running:
            action = "running"
        else:
            action = "ready"
        return {"action": action, "cancelled": self.cancelled, "stage_states": dict(self.stage_states), "running_stages": running, "deadlines": dict(self.deadlines), "events": list(self.events), "event_count": len(self.events), "invalid": self.invalid}

    def plan(self) -> dict:
        if self.invalid:
            return self.invalid
        if self.cancelled:
            return {"action": "blocked", "reason": "workflow_cancelled"}
        checkpoints = []
        for stage, state in self.stage_states.items():
            if state in {"completed", "failed", "skipped"}:
                checkpoints.append({"stage": stage, "status": state})
            elif state == "pending":
                checkpoints.append({"stage": stage, "status": "retry"})
        plan = build_execution_plan(self.stages, self.dependencies, checkpoints, self.max_parallelism)
        if plan.get("action") == "blocked":
            return plan
        plan["ready_stages"] = [stage for stage in plan.get("ready_stages", []) if self.stage_states.get(stage) == "pending"]
        plan["execution_waves"] = [wave for wave in plan.get("execution_waves", []) if wave and all(self.stage_states.get(stage) == "pending" for stage in wave)]
        plan["running_stages"] = [stage for stage, state in self.stage_states.items() if state == "running"]
        plan["available_slots"] = max(0, self.max_parallelism - len(plan["running_stages"]))
        plan["ready_stages"] = plan["ready_stages"][:plan["available_slots"]]
        return plan

    def start_stage(self, stage: str, at: str, timeout_seconds: int | None = None) -> dict:
        current = _parse_time(at)
        if current is None:
            return {"action": "blocked", "reason": "timestamp_invalid"}
        if self.invalid:
            return {"action": "blocked", "reason": "workflow_invalid"}
        if self.cancelled:
            return {"action": "blocked", "reason": "workflow_cancelled"}
        if stage not in self.stage_states:
            return {"action": "blocked", "reason": "stage_unknown"}
        if self.stage_states[stage] != "pending":
            return {"action": "blocked", "reason": "stage_not_pending"}
        if timeout_seconds is not None and (not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds < 1):
            return {"action": "blocked", "reason": "timeout_invalid"}
        plan = self.plan()
        if stage not in plan.get("ready_stages", []):
            return {"action": "blocked", "reason": "stage_not_ready"}
        self.stage_states[stage] = "running"
        if timeout_seconds is not None:
            self.deadlines[stage] = (current + timedelta(seconds=timeout_seconds)).isoformat()
        self._event("stage_started", stage, current.isoformat(), {"timeout_seconds": timeout_seconds})
        return {"action": "started", "stage": stage, "snapshot": self.snapshot()}

    def finish_stage(self, stage: str, outcome: str, at: str, error: str | None = None) -> dict:
        current = _parse_time(at)
        if current is None:
            return {"action": "blocked", "reason": "timestamp_invalid"}
        if outcome not in {"completed", "failed", "skipped"}:
            return {"action": "blocked", "reason": "outcome_invalid"}
        if stage not in self.stage_states:
            return {"action": "blocked", "reason": "stage_unknown"}
        if self.stage_states[stage] != "running":
            return {"action": "blocked", "reason": "stage_not_running"}
        self.stage_states[stage] = outcome
        self.deadlines.pop(stage, None)
        self._event("stage_" + outcome, stage, current.isoformat(), {"error": error} if error else {})
        return {"action": outcome, "stage": stage, "snapshot": self.snapshot()}

    def expire(self, at: str) -> dict:
        current = _parse_time(at)
        if current is None:
            return {"action": "blocked", "reason": "timestamp_invalid"}
        expired = []
        for stage, deadline in list(self.deadlines.items()):
            parsed = _parse_time(deadline)
            if parsed and parsed <= current and self.stage_states.get(stage) == "running":
                self.stage_states[stage] = "failed"
                self.deadlines.pop(stage, None)
                self._event("stage_timeout", stage, current.isoformat(), {"deadline": deadline})
                expired.append(stage)
        return {"action": "expired" if expired else "no_expirations", "stages": expired, "snapshot": self.snapshot()}

    def cancel(self, at: str, reason: str | None = None) -> dict:
        current = _parse_time(at)
        if current is None:
            return {"action": "blocked", "reason": "timestamp_invalid"}
        if self.cancelled:
            return {"action": "already_cancelled"}
        self.cancelled = True
        for stage, state in list(self.stage_states.items()):
            if state in {"pending", "running"}:
                self.stage_states[stage] = "cancelled"
                self.deadlines.pop(stage, None)
                self._event("stage_cancelled", stage, current.isoformat(), {"reason": reason} if reason else {})
        self._event("workflow_cancelled", None, current.isoformat(), {"reason": reason} if reason else {})
        return {"action": "cancelled", "snapshot": self.snapshot()}
