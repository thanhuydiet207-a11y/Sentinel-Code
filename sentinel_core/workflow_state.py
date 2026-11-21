"""Durable checkpoint and resume metadata for long-running remediation workflows."""
from __future__ import annotations
import hashlib, json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = 1
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ALLOWED = {"completed", "failed", "skipped"}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()

def _safe_id(value: Any) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("workflow_id must be 1-128 safe characters")
    return value

def _path(store: str | Path, workflow_id: str) -> Path:
    root = Path(store).resolve()
    root.mkdir(parents=True, exist_ok=True)
    result = (root / (_safe_id(workflow_id) + ".json")).resolve()
    if result.parent != root:
        raise ValueError("workflow path escapes store")
    return result

def _write(path: Path, state: dict) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def create_workflow(store: str | Path, workflow_id: str, stages: Any, input_digest: str, metadata: Any = None) -> dict:
    workflow_id = _safe_id(workflow_id)
    if not isinstance(stages, list) or not stages or any(not isinstance(s, str) or not s.strip() for s in stages):
        raise ValueError("stages must be a non-empty list of stage names")
    if len(set(stages)) != len(stages):
        raise ValueError("stages must be unique")
    if not isinstance(input_digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", input_digest):
        raise ValueError("input_digest must be a SHA-256 digest")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")
    p = _path(store, workflow_id)
    if p.exists():
        raise FileExistsError("workflow already exists; choose a new id")
    state = {"schema_version": _SCHEMA, "workflow_id": workflow_id, "status": "running",
             "created_at": _now(), "updated_at": _now(), "input_digest": input_digest.lower(),
             "stages": stages, "checkpoints": [], "metadata": metadata or {},
             "event_count": 0, "head_hash": "0"*64,
             "limitations": ["Local filesystem checkpoints are not signed or immutable.",
             "Concurrent writers are not coordinated; use one writer per workflow.",
             "Before resuming, callers must revalidate external side effects and inputs."]}
    _write(p, state)
    return state

def load_workflow(store: str | Path, workflow_id: str) -> dict:
    p = _path(store, workflow_id)
    if not p.is_file():
        raise FileNotFoundError("workflow not found")
    value = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("workflow state must be an object")
    return value

def checkpoint_stage(store: str | Path, workflow_id: str, stage: str, status: str, output: Any = None, error: str | None = None) -> dict:
    workflow_id = _safe_id(workflow_id)
    state = load_workflow(store, workflow_id)
    if state.get("status") != "running":
        raise ValueError("workflow is not running")
    if stage not in state.get("stages", []):
        raise ValueError("stage is not declared")
    if status not in _ALLOWED:
        raise ValueError("status must be completed, failed, or skipped")
    if any(c.get("stage") == stage for c in state.get("checkpoints", []) if isinstance(c, dict)):
        raise ValueError("checkpoint is immutable; stage already recorded")
    if status == "completed" and error is not None:
        raise ValueError("completed checkpoint cannot contain error")
    if status == "failed" and (not isinstance(error, str) or not error.strip()):
        raise ValueError("failed checkpoint requires error")
    if status == "skipped" and output is not None:
        raise ValueError("skipped stage cannot have output")
    event = {"sequence": state["event_count"], "workflow_id": workflow_id, "stage": stage,
             "status": status, "timestamp": _now(), "output_digest": _hash(output) if output is not None else None,
             "error": error, "previous_hash": state["head_hash"]}
    event["event_hash"] = _hash({k:v for k,v in event.items() if k != "event_hash"})
    state["checkpoints"].append(event)
    state["event_count"] += 1
    state["head_hash"] = event["event_hash"]
    state["updated_at"] = event["timestamp"]
    if status == "failed":
        state["status"] = "failed"
    elif all(any(c.get("stage") == s and c.get("status") == "completed" for c in state["checkpoints"]) for s in state["stages"]):
        state["status"] = "completed"
    _write(_path(store, workflow_id), state)
    return state

def verify_workflow(state: Any) -> dict:
    errors = []
    if not isinstance(state, dict) or state.get("schema_version") != _SCHEMA:
        return {"valid": False, "errors": ["unsupported_workflow_schema"]}
    checkpoints = state.get("checkpoints")
    if not isinstance(checkpoints, list):
        return {"valid": False, "errors": ["checkpoints_not_list"]}
    previous, seen = "0"*64, set()
    for i, event in enumerate(checkpoints):
        if not isinstance(event, dict):
            errors.append(f"checkpoint_{i}_not_object")
            continue
        if event.get("sequence") != i: errors.append(f"checkpoint_{i}_sequence_mismatch")
        if event.get("workflow_id") != state.get("workflow_id"): errors.append(f"checkpoint_{i}_workflow_mismatch")
        if event.get("stage") not in state.get("stages", []): errors.append(f"checkpoint_{i}_unknown_stage")
        if event.get("stage") in seen: errors.append(f"checkpoint_{i}_duplicate_stage")
        seen.add(event.get("stage"))
        if event.get("status") not in _ALLOWED: errors.append(f"checkpoint_{i}_invalid_status")
        if event.get("previous_hash") != previous: errors.append(f"checkpoint_{i}_previous_hash_mismatch")
        actual = _hash({k:v for k,v in event.items() if k != "event_hash"})
        if event.get("event_hash") != actual: errors.append(f"checkpoint_{i}_hash_mismatch")
        if event.get("output") is not None and event.get("output_digest") != _hash(event.get("output")): errors.append(f"checkpoint_{i}_output_digest_mismatch")
        previous = event.get("event_hash")
    if state.get("event_count") != len(checkpoints): errors.append("event_count_mismatch")
    if state.get("head_hash") != previous: errors.append("head_hash_mismatch")
    if not isinstance(state.get("input_digest"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", state.get("input_digest","")): errors.append("input_digest_invalid")
    return {"valid": not errors, "errors": errors, "event_count": len(checkpoints), "head_hash": previous}

def resume_plan(store: str | Path, workflow_id: str, input_digest: str | None = None) -> dict:
    state = load_workflow(store, workflow_id)
    checked = verify_workflow(state)
    if not checked["valid"]:
        return {"workflow_id": workflow_id, "status": "blocked", "reason": "checkpoint_integrity_invalid", "errors": checked["errors"], "completed_stages": [], "remaining_stages": []}
    if input_digest is not None and input_digest.lower() != state.get("input_digest"):
        return {"workflow_id": workflow_id, "status": "blocked", "reason": "input_digest_mismatch", "completed_stages": [], "remaining_stages": state.get("stages", [])}
    completed = [c["stage"] for c in state["checkpoints"] if c["status"] == "completed"]
    failed = [c["stage"] for c in state["checkpoints"] if c["status"] == "failed"]
    skipped = [c["stage"] for c in state["checkpoints"] if c["status"] == "skipped"]
    remaining = [s for s in state["stages"] if s not in completed and s not in skipped]
    return {"workflow_id": workflow_id, "status": state["status"], "integrity": "verified",
            "completed_stages": completed, "failed_stages": failed, "skipped_stages": skipped,
            "remaining_stages": remaining, "next_stage": remaining[0] if remaining else None,
            "safe_to_resume": state["status"] in {"running", "failed"} and not failed,
            "limitations": state.get("limitations", [])}
