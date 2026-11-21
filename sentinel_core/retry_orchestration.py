"""Bounded, fail-closed retry policy decisions; no execution is performed."""
from __future__ import annotations

from typing import Any


def retry_policy_decision(
    recovery_decision: Any,
    attempt_number: int,
    max_attempts: int = 3,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 300,
    retry_marker_present: bool = False,
    idempotency_key_present: bool = False,
) -> dict:
    """Evaluate whether a retry may be scheduled and calculate bounded backoff."""
    if not isinstance(recovery_decision, dict) or not isinstance(recovery_decision.get("action"), str):
        return {"action": "blocked", "reason": "recovery_decision_invalid"}
    if not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
        return {"action": "blocked", "reason": "attempt_number_invalid"}
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        return {"action": "blocked", "reason": "max_attempts_invalid"}
    if not isinstance(base_delay_seconds, int) or isinstance(base_delay_seconds, bool) or base_delay_seconds < 0:
        return {"action": "blocked", "reason": "base_delay_invalid"}
    if not isinstance(max_delay_seconds, int) or isinstance(max_delay_seconds, bool) or max_delay_seconds < 0:
        return {"action": "blocked", "reason": "max_delay_invalid"}
    if max_delay_seconds < base_delay_seconds:
        return {"action": "blocked", "reason": "delay_bounds_invalid"}
    recovery_action = recovery_decision["action"]
    if recovery_action == "completed":
        return {"action": "completed", "reason": "execution_already_completed"}
    if recovery_action != "safe_to_retry":
        return {"action": "manual_review" if recovery_action == "manual_review" else "blocked", "reason": "recovery_not_retryable", "recovery_action": recovery_action}
    if attempt_number >= max_attempts:
        return {"action": "manual_review", "reason": "retry_limit_reached", "attempt_number": attempt_number, "max_attempts": max_attempts}
    if not retry_marker_present:
        return {"action": "blocked", "reason": "retry_marker_required"}
    if not idempotency_key_present:
        return {"action": "blocked", "reason": "idempotency_key_required"}
    delay = min(base_delay_seconds * (2 ** (attempt_number - 1)), max_delay_seconds)
    return {
        "action": "retry_scheduled",
        "reason": "bounded_retry_policy_approved",
        "attempt_number": attempt_number,
        next_attempt_number": attempt_number + 1,
        max_attempts": max_attempts,
        delay_seconds": delay,
    }
