"""Idempotency registry primitives operating on caller-owned state."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def reserve_execution(registry: Any, idempotency_key: Any, execution_payload: Any, execution_id: Any) -> dict:
    """Reserve an idempotency key or report replay/conflict; does not mutate registry."""
    if not isinstance(registry, dict):
        return {"action": "blocked", "reason": "registry_invalid"}
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        return {"action": "blocked", "reason": "idempotency_key_required"}
    if not isinstance(execution_id, str) or not execution_id.strip():
        return {"action": "blocked", "reason": "execution_id_required"}
    key_digest = _digest(idempotency_key)
    payload_digest = _fingerprint(execution_payload)
    existing = registry.get(key_digest)
    if existing is not None:
        if not isinstance(existing, dict):
            return {"action": "blocked", "reason": "registry_entry_invalid"}
        if existing.get("payload_digest") != payload_digest:
            return {"action": "blocked", "reason": "idempotency_key_payload_conflict"}
        return {"action": "replay", "reason": "idempotency_key_already_reserved", "record": dict(existing)}
    record = {
        "key_digest": key_digest,
        "payload_digest": payload_digest,
        "execution_id": execution_id,
        "status": "reserved",
    }
    return {"action": "reserved", "record": record, "registry_key": key_digest}


def transition_execution(registry: Any, registry_key: Any, new_status: Any) -> dict:
    """Validate a state transition and return a copied registry; never mutates input."""
    if not isinstance(registry, dict) or not isinstance(registry_key, str):
        return {"action": "blocked", "reason": "registry_invalid"}
    entry = registry.get(registry_key)
    if not isinstance(entry, dict):
        return {"action": "blocked", "reason": "registry_entry_missing"}
    transitions = {
        "reserved": {"running", "failed"},
        "running": {"completed", "failed"},
        "failed": set(),
        "completed": set(),
    }
    current = entry.get("status")
    if current not in transitions or new_status not in transitions[current]:
        return {"action": "blocked", "reason": "transition_invalid", "current_status": current, "requested_status": new_status}
    updated_registry = dict(registry)
    updated_entry = dict(entry)
    updated_entry["status"] = new_status
    updated_registry[registry_key] = updated_entry
    return {"action": "updated", "registry": updated_registry, "record": updated_entry}


def verify_registry(registry: Any) -> dict:
    """Validate registry records and detect duplicate execution IDs."""
    if not isinstance(registry, dict):
        return {"valid": False, "errors": ["registry_invalid"]}
    errors = []
    seen_execution_ids = set()
    for key, record in registry.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            errors.append("entry_invalid")
            continue
        if record.get("key_digest") != key or not isinstance(record.get("payload_digest"), str) or len(record["payload_digest"]) != 64:
            errors.append("digest_fields_invalid")
        if record.get("status") not in {"reserved", "running", "completed", "failed"}:
            errors.append("status_invalid")
        execution_id = record.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            errors.append("execution_id_invalid")
        elif execution_id in seen_execution_ids:
            errors.append("duplicate_execution_id")
        seen_execution_ids.add(execution_id)
    return {"valid": not errors, "errors": errors, "entry_count": len(registry)}
