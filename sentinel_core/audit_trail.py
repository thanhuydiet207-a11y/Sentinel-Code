"""Append-only logical audit events and remediation lifecycle validation."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from typing import Any

_ALLOWED = {"created", "finding_selected", "review_completed", "patch_proposed",
            "patch_validated", "risk_assessed", "sandbox_completed", "scan_completed",
            "report_generated", "evidence_sealed", "evidence_verified",
            "approval_requested", "approved", "rejected", "closed"}

def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def _event_hash(event: dict) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()

def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed

def build_audit_trail(session_id: str, events: Any) -> dict:
    if not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("session_id is required")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    normalized, previous, last_time = [], "0" * 64, None
    for index, raw in enumerate(events):
        if not isinstance(raw, dict):
            raise ValueError(f"event {index} must be an object")
        event_type = raw.get("type")
        if event_type not in _ALLOWED:
            raise ValueError(f"event {index} has unsupported type")
        timestamp = raw.get("timestamp")
        parsed_time = _timestamp(timestamp)
        if last_time is not None and parsed_time < last_time:
            raise ValueError(f"event {index} timestamp precedes previous event")
        last_time = parsed_time
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
                            "Timestamps and payloads are caller-supplied; authenticity is not independently verified."]}

def verify_audit_trail(trail: Any) -> dict:
    if not isinstance(trail, dict) or trail.get("schema_version") != 1:
        raise ValueError("unsupported audit trail")
    events = trail.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    previous, errors, last_time = "0" * 64, [], None
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
        if event.get("type") not in _ALLOWED:
            errors.append(f"event_{i}_unsupported_type")
        try:
            parsed = _timestamp(event.get("timestamp"))
            if last_time is not None and parsed < last_time:
                errors.append(f"event_{i}_timestamp_order_mismatch")
            last_time = parsed
        except ValueError:
            errors.append(f"event_{i}_timestamp_invalid")
        if not isinstance(event.get("payload"), dict):
            errors.append(f"event_{i}_payload_invalid")
        claimed = event.get("event_hash")
        core = {k: v for k, v in event.items() if k != "event_hash"}
        try:
            actual = _event_hash(core)
        except (TypeError, ValueError):
            actual = ""
            errors.append(f"event_{i}_hash_uncomputable")
        if claimed != actual:
            errors.append(f"event_{i}_hash_mismatch")
        previous = actual
    if trail.get("event_count") != len(events):
        errors.append("event_count_mismatch")
    if trail.get("head_hash") != previous:
        errors.append("head_hash_mismatch")
    lifecycle = lifecycle_status(events)
    errors.extend(f"lifecycle_{item}" for item in lifecycle["missing_requirements"])
    return {"valid": not errors, "integrity": "verified" if not errors else "invalid",
            "event_count": len(events), "head_hash": previous, "errors": errors}

def lifecycle_status(events: Any) -> dict:
    if not isinstance(events, list):
        raise ValueError("events must be list")
    types = [e.get("type") if isinstance(e, dict) else None for e in events]
    missing = []
    positions = {}
    for index, event_type in enumerate(types):
        if event_type is not None:
            positions.setdefault(event_type, []).append(index)

    def require_once(event_type: str, label: str):
        count = len(positions.get(event_type, []))
        if count != 1:
            missing.append(label)

    def require_before(first: str, second: str, label: str):
        first_positions = positions.get(first, [])
        second_positions = positions.get(second, [])
        if not first_positions or not second_positions or first_positions[0] >= second_positions[0]:
            missing.append(label)

    if not types or types[0] != "created":
        missing.append("created_must_be_first")
    require_once("created", "created_must_appear_once")

    for event_type in ("approval_requested", "approved", "rejected", "closed"):
        if len(positions.get(event_type, [])) > 1:
            missing.append(f"{event_type}_must_appear_at_most_once")

    if positions.get("approved") and positions.get("rejected"):
        missing.append("approval_and_rejection_are_mutually_exclusive")

    if positions.get("approved"):
        require_before("approval_requested", "approved", "approval_requested_before_approved")
        require_before("evidence_verified", "approved", "evidence_verified_before_approved")
        require_before("report_generated", "approved", "report_generated_before_approved")

    if positions.get("rejected"):
        require_before("approval_requested", "rejected", "approval_requested_before_rejected")

    if any(positions.get(event_type) for event_type in ("approved", "rejected", "closed")):
        if len(positions.get("approval_requested", [])) != 1:
            missing.append("approval_requested_must_appear_once_before_decision")

    if positions.get("closed"):
        if types[-1] != "closed" or len(positions["closed"]) != 1:
            missing.append("closed_must_be_final_and_unique")
        if not (positions.get("approved") or positions.get("rejected")):
            missing.append("approval_or_rejection_before_close")
        else:
            decision_positions = positions.get("approved", []) + positions.get("rejected", [])
            if positions["closed"][0] <= max(decision_positions):
                missing.append("decision_before_close")

    return {"status": "complete" if not missing else "incomplete",
            "missing_requirements": sorted(set(missing)), "review_required": True}
