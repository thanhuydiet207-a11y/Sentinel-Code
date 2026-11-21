"""Append-only logical audit events and remediation lifecycle validation."""
from __future__ import annotations
import hashlib
import json
from typing import Any

_ALLOWED = {"created", "finding_selected", "review_completed", "patch_proposed",
            "patch_validated", "risk_assessed", "sandbox_completed", "scan_completed",
            "report_generated", "evidence_sealed", "evidence_verified",
            "approval_requested", "approved", "rejected", "closed"}

def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def _event_hash(event: dict) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()

def build_audit_trail(session_id: str, events: Any) -> dict:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    normalized, previous = [], "0" * 64
    for index, raw in enumerate(events):
        if not isinstance(raw, dict):
            raise ValueError(f"event {index} must be an object")
        event_type = raw.get("type")
        if event_type not in _ALLOWED:
            raise ValueError(f"event {index} has unsupported type")
        timestamp = raw.get("timestamp")
        if not isinstance(timestamp, str) or not timestamp:
            raise ValueError(f"event {index} timestamp is required")
        payload = raw.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError(f"event {index} payload must be object")
        event = {"sequence": index, "session_id": session_id, "timestamp": timestamp,
                 "type": event_type, "payload": payload, "previous_hash": previous}
        event["event_hash"] = _event_hash(event)
        previous = event["event_hash"]
        normalized.append(event)
    return {"schema_version": 1, "session_id": session_id, "events": normalized,
            "head_hash": previous, "event_count": len(normalized),
            "integrity": "hash_chained",
            "limitations": ["Events are hash chained but not signed or stored in immutable storage.",
                            "Timestamps and payloads are caller-supplied; authenticity and chronology are not independently verified."]}

def verify_audit_trail(trail: Any) -> dict:
    if not isinstance(trail, dict) or trail.get("schema_version") != 1:
        raise ValueError("unsupported audit trail")
    events = trail.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    previous = "0" * 64
    errors = []
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"event_{i}_not_object")
            continue
        if event.get("sequence") != i:
            errors.append(f"event_{i}_sequence_mismatch")
        if event.get("session_id") != trail.get("session_id"):
            errors.append(f"event_{i}_session_mismatch")
        if event.get("previous_hash") != previous:
            errors.append(f"event_{i}_previous_hash_mismatch")
        claimed = event.get("event_hash")
        core = {k: v for k, v in event.items() if k != "event_hash"}
        actual = _event_hash(core)
        if claimed != actual:
            errors.append(f"event_{i}_hash_mismatch")
        previous = claimed if isinstance(claimed, str) else actual
    if trail.get("event_count") != len(events):
        errors.append("event_count_mismatch")
    if trail.get("head_hash") != previous:
        errors.append("head_hash_mismatch")
    return {"valid": not errors, "integrity": "verified" if not errors else "invalid",
            "event_count": len(events), "head_hash": previous, "errors": errors}

def lifecycle_status(events: Any) -> dict:
    if not isinstance(events, list):
        raise ValueError("events must be list")
    types = [e.get("type") for e in events if isinstance(e, dict)]
    required = ["created"]
    missing = [x for x in required if x not in types]
    if "approved" in types and "approval_requested" not in types:
        missing.append("approval_requested_before_approved")
    if "approved" in types and ("evidence_verified" not in types or "report_generated" not in types):
        missing.append("verified_evidence_and_report_before_approval")
    if "closed" in types and not any(t in types for t in ("approved", "rejected")):
        missing.append("approval_or_rejection_before_close")
    return {"status": "complete" if not missing else "incomplete",
            "missing_requirements": missing, "review_required": True}
