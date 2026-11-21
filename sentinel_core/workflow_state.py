"""Durable checkpoint and resume metadata for long-running remediation workflows."""
from __future__ import annotations
import hashlib, json, os, re, tempfile, time, functools
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import contextmanager

_SCHEMA = 2
_SUPPORTED_SCHEMAS = {1, 2}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_ALLOWED = {"completed", "failed", "skipped", "retry"}

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
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def _workflow_lock(path: Path, timeout: float = 3.0):
    """Serialize local writers; stale locks are never broken automatically."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(fd, json.dumps({"pid": os.getpid(), "created_at": _now()}).encode())
            os.fsync(fd)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"workflow lock busy: {lock_path.name}; inspect and remove stale lock manually")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass

def _serialized_writer(function):
    @functools.wraps(function)
    def wrapped(store, workflow_id, *args, **kwargs):
        path = _path(store, workflow_id)
        with _workflow_lock(path):
            return function(store, workflow_id, *args, **kwargs)
    return wrapped

@_serialized_writer
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
             "event_count": 0, "head_hash": "0"*64, "migration_history": [],
             "limitations": ["Local filesystem checkpoints are not signed or immutable.",
             "Local writers are serialized with lock files; stale locks require manual inspection and removal.",
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

@_serialized_writer
def checkpoint_stage(store: str | Path, workflow_id: str, stage: str, status: str, output: Any = None, error: str | None = None) -> dict:
    workflow_id = _safe_id(workflow_id)
    state = load_workflow(store, workflow_id)
    if state.get("status") != "running":
        raise ValueError("workflow is not running; failed workflows require retry_stage first")
    if stage not in state.get("stages", []):
        raise ValueError("stage is not declared")
    if status not in _ALLOWED:
        raise ValueError("status must be completed, failed, or skipped")
    prior = [c for c in state.get("checkpoints", []) if isinstance(c, dict) and c.get("stage") == stage]
    if prior and prior[-1].get("status") != "retry":
        raise ValueError("checkpoint is immutable; call retry_stage after a failed attempt")
    if status == "completed" and error is not None:
        raise ValueError("completed checkpoint cannot contain error")
    if status == "failed" and (not isinstance(error, str) or not error.strip()):
        raise ValueError("failed checkpoint requires error")
    if status in {"skipped", "retry"} and output is not None:
        raise ValueError(f"{status} stage cannot have output")
    if status == "retry":
        raise ValueError("retry markers must be created with retry_stage")
    event = {"sequence": state["event_count"], "workflow_id": workflow_id, "stage": stage,
             "status": status, "timestamp": _now(), "output": output,
             "output_digest": _hash(output) if output is not None else None,
             "error": error, "previous_hash": state["head_hash"]}
    event["event_hash"] = _hash({k:v for k,v in event.items() if k != "event_hash"})
    state["checkpoints"].append(event)
    state["event_count"] += 1
    state["head_hash"] = event["event_hash"]
    state["updated_at"] = event["timestamp"]
    latest = {s: next((c for c in reversed(state["checkpoints"]) if c.get("stage") == s), None) for s in state["stages"]}
    if status == "failed":
        state["status"] = "failed"
    elif all(item and item.get("status") in {"completed", "skipped"} for item in latest.values()):
        state["status"] = "completed"
    else:
        state["status"] = "running"
    _write(_path(store, workflow_id), state)
    return state

@_serialized_writer
def retry_stage(store: str | Path, workflow_id: str, stage: str) -> dict:
    """Append an audited retry marker after a failed stage; prior attempt remains immutable."""
    workflow_id = _safe_id(workflow_id)
    state = load_workflow(store, workflow_id)
    integrity = verify_workflow(state)
    if not integrity["valid"]:
        raise ValueError("checkpoint integrity invalid: " + ", ".join(integrity["errors"]))
    if state.get("status") not in {"running", "failed"}:
        raise ValueError("workflow is not retryable")
    if stage not in state.get("stages", []):
        raise ValueError("stage is not declared")
    prior = [c for c in state.get("checkpoints", []) if isinstance(c, dict) and c.get("stage") == stage]
    if not prior or prior[-1].get("status") != "failed":
        raise ValueError("only the latest failed stage attempt can be retried")
    event = {"sequence": state["event_count"], "workflow_id": workflow_id, "stage": stage,
             "status": "retry", "timestamp": _now(), "output": None, "output_digest": None,
             "error": None, "previous_hash": state["head_hash"]}
    event["event_hash"] = _hash({k:v for k,v in event.items() if k != "event_hash"})
    state["checkpoints"].append(event)
    state["event_count"] += 1
    state["head_hash"] = event["event_hash"]
    state["updated_at"] = event["timestamp"]
    state["status"] = "running"
    _write(_path(store, workflow_id), state)
    return state

def validate_workflow_schema(state: Any) -> dict:
    """Validate structural shape without verifying the checkpoint hash chain."""
    errors = []
    if not isinstance(state, dict):
        return {"valid": False, "errors": ["workflow_not_object"]}
    version = state.get("schema_version")
    if version not in _SUPPORTED_SCHEMAS:
        return {"valid": False, "errors": ["unsupported_workflow_schema"]}
    required = ("workflow_id", "status", "created_at", "updated_at", "input_digest", "stages", "checkpoints", "event_count", "head_hash")
    for key in required:
        if key not in state:
            errors.append(f"missing_{key}")
    if not isinstance(state.get("workflow_id"), str) or not _ID.fullmatch(state.get("workflow_id", "")):
        errors.append("workflow_id_invalid")
    if state.get("status") not in {"running", "failed", "completed"}:
        errors.append("workflow_status_invalid")
    stages = state.get("stages")
    if not isinstance(stages, list) or not stages or any(not isinstance(x, str) or not x.strip() for x in stages):
        errors.append("stages_invalid")
    if not isinstance(state.get("checkpoints"), list):
        errors.append("checkpoints_not_list")
    if not isinstance(state.get("event_count"), int) or isinstance(state.get("event_count"), bool):
        errors.append("event_count_invalid")
    if not isinstance(state.get("head_hash"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", state.get("head_hash", "")):
        errors.append("head_hash_invalid")
    if not isinstance(state.get("input_digest"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", state.get("input_digest", "")):
        errors.append("input_digest_invalid")
    if version == 2:
        if not isinstance(state.get("metadata"), dict): errors.append("metadata_invalid")
        if not isinstance(state.get("limitations"), list): errors.append("limitations_invalid")
        if not isinstance(state.get("migration_history"), list): errors.append("migration_history_invalid")
    return {"valid": not errors, "errors": errors, "schema_version": version}

def verify_workflow(state: Any) -> dict:
    errors = []
    schema = validate_workflow_schema(state)
    if not schema["valid"]:
        return {"valid": False, "errors": schema["errors"]}
    checkpoints = state.get("checkpoints")
    if not isinstance(checkpoints, list):
        return {"valid": False, "errors": ["checkpoints_not_list"]}
    previous, latest = "0"*64, {}
    for i, event in enumerate(checkpoints):
        if not isinstance(event, dict):
            errors.append(f"checkpoint_{i}_not_object")
            continue
        if event.get("sequence") != i: errors.append(f"checkpoint_{i}_sequence_mismatch")
        if event.get("workflow_id") != state.get("workflow_id"): errors.append(f"checkpoint_{i}_workflow_mismatch")
        if event.get("stage") not in state.get("stages", []): errors.append(f"checkpoint_{i}_unknown_stage")
        stage = event.get("stage")
        status = event.get("status")
        prior_status = latest.get(stage)
        if prior_status in {"completed", "skipped"}: errors.append(f"checkpoint_{i}_duplicate_terminal_stage")
        if prior_status == "failed" and status != "retry": errors.append(f"checkpoint_{i}_retry_marker_missing")
        if status == "retry" and prior_status != "failed": errors.append(f"checkpoint_{i}_retry_without_failure")
        if prior_status == "retry" and status not in {"completed", "failed", "skipped"}: errors.append(f"checkpoint_{i}_invalid_retry_result")
        if status not in _ALLOWED: errors.append(f"checkpoint_{i}_invalid_status")
        latest[stage] = status
        if event.get("previous_hash") != previous: errors.append(f"checkpoint_{i}_previous_hash_mismatch")
        actual = _hash({k:v for k,v in event.items() if k != "event_hash"})
        if event.get("event_hash") != actual: errors.append(f"checkpoint_{i}_hash_mismatch")
        if event.get("output") is not None and event.get("output_digest") != _hash(event.get("output")): errors.append(f"checkpoint_{i}_output_digest_mismatch")
        if event.get("output") is None and event.get("output_digest") is not None: errors.append(f"checkpoint_{i}_output_digest_without_output")
        previous = event.get("event_hash")
    if state.get("event_count") != len(checkpoints): errors.append("event_count_mismatch")
    if state.get("head_hash") != previous: errors.append("head_hash_mismatch")
    if not isinstance(state.get("input_digest"), str) or not re.fullmatch(r"[a-fA-F0-9]{64}", state.get("input_digest","")): errors.append("input_digest_invalid")
    return {"valid": not errors, "errors": errors, "event_count": len(checkpoints), "head_hash": previous}

@_serialized_writer
def migrate_workflow(store: str | Path, workflow_id: str) -> dict:
    """Migrate schema 1 to 2, preserving a non-overwriting backup."""
    workflow_id = _safe_id(workflow_id)
    path = _path(store, workflow_id)
    state = load_workflow(store, workflow_id)
    structural = validate_workflow_schema(state)
    if not structural["valid"]:
        raise ValueError("schema validation failed: " + ", ".join(structural["errors"]))
    if state.get("schema_version") == _SCHEMA:
        return {"status": "already_current", "workflow": state, "backup": None}
    integrity = verify_workflow(state)
    if not integrity["valid"]:
        raise ValueError("checkpoint integrity validation failed: " + ", ".join(integrity["errors"]))
    backup = path.with_suffix(path.suffix + ".schema1.bak")
    if backup.exists():
        raise FileExistsError("migration backup already exists; refusing to overwrite")
    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-backup-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, backup)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    migrated = dict(state)
    migrated["schema_version"] = _SCHEMA
    migrated.setdefault("metadata", {})
    migrated.setdefault("limitations", ["Local filesystem checkpoints are not signed or immutable.", "Before resuming, callers must revalidate external side effects and inputs."])
    migrated["migration_history"] = list(migrated.get("migration_history", [])) + [{"from": 1, "to": 2, "migrated_at": _now(), "backup": backup.name}]
    _write(path, migrated)
    checked = verify_workflow(migrated)
    if not checked["valid"]:
        _write(path, state)
        raise ValueError("migrated checkpoint failed validation: " + ", ".join(checked["errors"]))
    return {"status": "migrated", "workflow": migrated, "backup": str(backup)}

def resume_plan(store: str | Path, workflow_id: str, input_digest: str | None = None) -> dict:
    state = load_workflow(store, workflow_id)
    checked = verify_workflow(state)
    if not checked["valid"]:
        return {"workflow_id": workflow_id, "status": "blocked", "reason": "checkpoint_integrity_invalid", "errors": checked["errors"], "completed_stages": [], "remaining_stages": []}
    if input_digest is not None and input_digest.lower() != state.get("input_digest"):
        return {"workflow_id": workflow_id, "status": "blocked", "reason": "input_digest_mismatch", "completed_stages": [], "remaining_stages": state.get("stages", [])}
    latest = {s: next((c for c in reversed(state["checkpoints"]) if c.get("stage") == s), None) for s in state["stages"]}
    completed = [s for s, c in latest.items() if c and c["status"] == "completed"]
    failed = [s for s, c in latest.items() if c and c["status"] == "failed"]
    skipped = [s for s, c in latest.items() if c and c["status"] == "skipped"]
    remaining = [s for s in state["stages"] if s not in completed and s not in skipped]
    return {"workflow_id": workflow_id, "status": state["status"], "integrity": "verified",
            "completed_stages": completed, "failed_stages": failed, "skipped_stages": skipped,
            "remaining_stages": remaining, "next_stage": remaining[0] if remaining else None,
            "safe_to_resume": state["status"] == "running" and not failed,
            "limitations": state.get("limitations", [])}


def checkpoint_outputs(store: str | Path, workflow_id: str, input_digest: str | None = None) -> dict:
    """Return verified outputs for completed stages; refuse corrupted or mismatched state."""
    state = load_workflow(store, workflow_id)
    checked = verify_workflow(state)
    if not checked["valid"]:
        raise ValueError("checkpoint integrity invalid: " + ", ".join(checked["errors"]))
    if input_digest is not None and input_digest.lower() != state.get("input_digest"):
        raise ValueError("input digest mismatch")
    latest = {s: next((event for event in reversed(state["checkpoints"]) if event.get("stage") == s), None) for s in state.get("stages", [])}
    return {stage: event["output"] for stage, event in latest.items() if event and event.get("status") == "completed"}
