"""Execution receipt and audit primitives for workflow stages."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_execution_receipt(
    workflow_id: str,
    stage: str,
    decision: dict,
    execution_id: str,
    idempotency_key: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    outcome: str | None = None,
    details: dict | None = None,
) -> dict:
    """Create a validated, privacy-preserving receipt; this function performs no execution."""
    if not isinstance(workflow_id, str) or not workflow_id.strip():
        raise ValueError("workflow_id_required")
    if not isinstance(stage, str) or not stage.strip():
        raise ValueError("stage_required")
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ValueError("execution_id_required")
    if not isinstance(decision, dict) or decision.get("allowed") not in {True, False}:
        raise ValueError("decision_invalid")
    if decision.get("allowed") is not True:
        raise ValueError("execution_not_approved")
    if outcome not in {None, "started", "completed", "failed", "abandoned"}:
        raise ValueError("outcome_invalid")
    if details is not None and not isinstance(details, dict):
        raise ValueError("details_must_be_object")
    receipt = {
        "receipt_schema": 1,
        "workflow_id": workflow_id,
        "stage": stage,
        "execution_id": execution_id,
        "decision": {"allowed": True, "reason": decision.get("reason", "stage_ready")},
        "idempotency_key_digest": hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest() if idempotency_key else None,
        "started_at": started_at or _utc_now(),
        "finished_at": finished_at,
        "outcome": outcome or "started",
        "details": details or {},
    }
    receipt["receipt_digest"] = _digest(receipt)
    return receipt


def verify_execution_receipt(receipt: Any) -> dict:
    """Verify receipt shape and digest; report unfinished executions as abandoned candidates."""
    if not isinstance(receipt, dict):
        return {"valid": False, "errors": ["receipt_not_object"], "abandoned": False}
    errors = []
    required = ("receipt_schema", "workflow_id", "stage", "execution_id", "decision", "started_at", "outcome", "details", "receipt_digest")
    for field in required:
        if field not in receipt:
            errors.append(f"missing_{field}")
    if receipt.get("receipt_schema") != 1:
        errors.append("unsupported_receipt_schema")
    if receipt.get("outcome") not in {"started", "completed", "failed", "abandoned"}:
        errors.append("outcome_invalid")
    if not isinstance(receipt.get("details"), dict):
        errors.append("details_invalid")
    digest = receipt.get("receipt_digest")
    if isinstance(digest, str):
        payload = {key: value for key, value in receipt.items() if key != "receipt_digest"}
        if _digest(payload) != digest:
            errors.append("receipt_digest_mismatch")
    else:
        errors.append("receipt_digest_invalid")
    return {"valid": not errors, "errors": errors, "abandoned": receipt.get("outcome") == "started" and receipt.get("finished_at") is None}


def reconcile_execution_receipts(receipts: Any, checkpoint_events: Any) -> dict:
    """Compare receipt outcomes with checkpoint history without mutating either input."""
    if not isinstance(receipts, list) or not isinstance(checkpoint_events, list):
        return {"valid": False, "errors": ["inputs_must_be_lists"], "matches": [], "unmatched_receipts": [], "unmatched_checkpoints": []}
    verified = [verify_execution_receipt(item) for item in receipts]
    invalid_indices = [index for index, result in enumerate(verified) if not result["valid"]]
    by_stage = {}
    for event in checkpoint_events:
        if isinstance(event, dict) and isinstance(event.get("stage"), str):
            by_stage.setdefault(event["stage"], []).append(event)
    matches = []
    unmatched_receipts = []
    used_events = set()
    for index, receipt in enumerate(receipts):
        if index in invalid_indices:
            unmatched_receipts.append({"index": index, "reason": "receipt_invalid"})
            continue
        candidates = by_stage.get(receipt["stage"], [])
        expected = {"completed": "completed", "failed": "failed", "abandoned": None, "started": None}.get(receipt["outcome"])
        match_index = next((i for i, event in enumerate(candidates) if i not in used_events and (expected is None or event.get("status") == expected)), None)
        if match_index is None:
            unmatched_receipts.append({"index": index, "reason": "checkpoint_missing_or_status_mismatch", "stage": receipt["stage"]})
        else:
            used_events.add(match_index)
            matches.append({"receipt_index": index, "stage": receipt["stage"], "outcome": receipt["outcome"], "checkpoint_status": candidates[match_index].get("status")})
    unmatched_checkpoints = []
    for stage, events in by_stage.items():
        for index, event in enumerate(events):
            if index not in used_events:
                unmatched_checkpoints.append({"stage": stage, "status": event.get("status")})
    return {"valid": not invalid_indices, "errors": [f"receipt_{i}_invalid" for i in invalid_indices], "matches": matches, "unmatched_receipts": unmatched_receipts, "unmatched_checkpoints": unmatched_checkpoints}
