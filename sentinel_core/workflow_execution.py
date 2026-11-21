"""Dependency-aware workflow execution planning without executing tasks."""
from __future__ import annotations

from collections import deque
from typing import Any


def _validate_graph(stages: Any, dependencies: Any) -> dict:
    errors = []
    if not isinstance(stages, list) or not stages or any(not isinstance(s, str) or not s.strip() for s in stages):
        return {"valid": False, "errors": ["stages_invalid"]}
    if len(set(stages)) != len(stages):
        errors.append("stages_duplicate")
    declared = set(stages)
    if dependencies is None:
        dependencies = {}
    if not isinstance(dependencies, dict):
        return {"valid": False, "errors": ["dependencies_invalid"]}
    normalized = {}
    for stage, deps in dependencies.items():
        if stage not in declared:
            errors.append("dependency_stage_unknown:" + str(stage))
            continue
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            errors.append("dependency_list_invalid:" + stage)
            continue
        if len(set(deps)) != len(deps):
            errors.append("dependency_duplicate:" + stage)
        unknown = sorted(set(deps) - declared)
        errors.extend("dependency_unknown:" + stage + ":" + dep for dep in unknown)
        if stage in deps:
            errors.append("dependency_self:" + stage)
        normalized[stage] = [dep for dep in deps if dep in declared and dep != stage]
    if errors:
        return {"valid": False, "errors": errors, "dependencies": normalized}
    indegree = {stage: 0 for stage in stages}
    children = {stage: [] for stage in stages}
    for stage, deps in normalized.items():
        indegree[stage] = len(deps)
        for dep in deps:
            children[dep].append(stage)
    queue = deque(stage for stage in stages if indegree[stage] == 0)
    visited = []
    while queue:
        stage = queue.popleft()
        visited.append(stage)
        for child in children[stage]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(visited) != len(stages):
        errors.append("dependency_cycle")
    return {"valid": not errors, "errors": errors, "dependencies": normalized, "topological_order": visited}


def build_execution_plan(stages: Any, dependencies: Any = None, checkpoints: Any = None, max_parallelism: int = 4) -> dict:
    """Return safe ready stages and dependency waves; does not execute or mutate state."""
    graph = _validate_graph(stages, dependencies)
    if not graph["valid"]:
        return {"action": "blocked", "reason": "workflow_graph_invalid", "errors": graph["errors"]}
    if not isinstance(max_parallelism, int) or isinstance(max_parallelism, bool) or max_parallelism < 1:
        return {"action": "blocked", "reason": "parallelism_invalid"}
    if checkpoints is None:
        checkpoints = []
    if not isinstance(checkpoints, list) or any(not isinstance(event, dict) for event in checkpoints):
        return {"action": "blocked", "reason": "checkpoints_invalid"}

    latest = {}
    for event in checkpoints:
        stage = event.get("stage")
        status = event.get("status")
        if stage not in stages:
            return {"action": "blocked", "reason": "checkpoint_stage_unknown", "stage": stage}
        if status not in {"completed", "failed", "skipped", "retry"}:
            return {"action": "blocked", "reason": "checkpoint_status_invalid", "stage": stage}
        latest[stage] = status

    statuses = {stage: latest.get(stage, "pending") for stage in stages}
    ready, waiting, blocked, terminal = [], [], [], []
    for stage in stages:
        status = statuses[stage]
        deps = graph["dependencies"].get(stage, [])
        if status in {"completed", "skipped"}:
            terminal.append(stage)
            continue
        if status == "failed":
            blocked.append({"stage": stage, "reason": "stage_failed"})
            continue
        failed_deps = [dep for dep in deps if statuses[dep] == "failed"]
        if failed_deps:
            blocked.append({"stage": stage, "reason": "dependency_failed", "dependencies": failed_deps})
            continue
        unresolved = [dep for dep in deps if statuses[dep] not in {"completed", "skipped"}]
        if unresolved:
            waiting.append({"stage": stage, "dependencies": unresolved})
            continue
        ready.append(stage)

    waves = [ready[i:i + max_parallelism] for i in range(0, len(ready), max_parallelism)]
    remaining = [stage for stage in stages if stage not in terminal]
    action = "ready" if ready else ("completed" if not remaining else "waiting")
    return {
        "action": action,
        "topological_order": graph["topological_order"],
        "statuses": statuses,
        "ready_stages": ready,
        "execution_waves": waves,
        "waiting_stages": waiting,
        "blocked_stages": blocked,
        "terminal_stages": terminal,
        "remaining_stages": remaining,
        "max_parallelism": max_parallelism,
        "dependencies": graph["dependencies"],
    }
