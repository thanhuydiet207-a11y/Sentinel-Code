"""Fail-closed execution recovery classification and reconciliation."""
from __future__ import annotations

from typing import Any

from .execution_receipts import verify_execution_receipt


def classify_execution_recovery(receipt: Any, checkpoint_events: Any) -> dict:
    """Classify recovery using verified receipts and stage-matched checkpoint history.

    This is advisory and never triggers retries or external side effects.
    """
    verification = verify_execution_receipt(receipt)
    if not verification["valid"]:
        return {"action": "blocked", "reason": "receipt_integrity_invalid", "errors": verification["errors"]}
    if not isinstance(checkpoint_events, list):
        return {"action": "blocked", "reason": "checkpoint_events_invalid"}
    stage = receipt["stage"]
    matching = [event for event in checkpoint_events if isinstance(event, dict) and event.get("stage") == stage]
    if not matching:
        return {"action": "manual_review", "reason": "checkpoint_missing", "stage": stage}
    latest = matching[-1]
    outcome = receipt["outcome"]
    checkpoint_status = latest.get("status")
    expected = {"completed": "completed", "failed": "failed", "abandoned": None, "started": None}
    if expected[outcome] is not None and checkpoint_status != expected[outcome]:
        return {"action": "blocked", "reason": "receipt_checkpoint_status_mismatch", "stage": stage, "receipt_outcome": outcome, "checkpoint_status": checkpoint_status}
    if outcome == "completed":
        return {"action": "completed", "reason": "execution_confirmed", "stage": stage}
    if outcome in {"started", "abandoned"}:
        side_effects = receipt.get("details", {}).get("side_effects")
        if side_effects == "none" and checkpoint_status in {"failed", "retry"}:
            return {"action": "safe_to_retry", "reason": "no_side_effects_confirmed", "stage": stage}
        if side_effects == "confirmed":
            return {"action": "manual_review", "reason": "side_effects_may_have_occurred", "stage": stage}
        return {"action": "manual_review", "reason": "side_effect_status_unknown", "stage": stage}
    if outcome == "failed":
        side_effects = receipt.get("details", {}).get("side_effects")
        if side_effects == "none":
            return {"action": "safe_to_retry", "reason": "failure_without_side_effects", "stage": stage}
        if side_effects == "confirmed":
            return {"action": "manual_review", "reason": "side_effects_confirmed", "stage": stage}
        return {"action": "manual_review", "reason": "side_effect_status_unknown", "stage": stage}
    return {"action": "blocked", "reason": "unsupported_outcome", "stage": stage}


def reconcile_recovery_state(receipts: Any, checkpoint_events: Any) -> dict:
    """Produce recovery decisions for each receipt; fail closed on invalid inputs."""
    if not isinstance(receipts, list) or not isinstance(checkpoint_events, list):
        return {"valid": False, "errors": ["inputs_must_be_lists"], "decisions": []}
    decisions = [classify_execution_recovery(receipt, checkpoint_events) for receipt in receipts]
    return {"valid": all(item["action"] != "blocked" for item in decisions), "errors": [], "decisions": decisions}
