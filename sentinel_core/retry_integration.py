"""Advisory integration pipeline for receipt recovery, retry policy, registry and scheduling."""
from __future__ import annotations

from typing import Any

from .execution_recovery import classify_execution_recovery
from .retry_orchestration import retry_policy_decision
from .retry_scheduler import schedule_retry
from .idempotency_registry import reserve_execution


def prepare_retry(
    receipt: Any,
    checkpoint_events: Any,
    registry: Any,
    idempotency_key: Any,
    execution_payload: Any,
    execution_id: Any,
    job_id: Any,
    scheduled_at: Any,
    attempt_number: int,
    max_attempts: int = 3,
    base_delay_seconds: int = 30,
    max_delay_seconds: int = 300,
    retry_marker_present: bool = False,
    jitter_seconds: int = 0,
) -> dict:
    """Compose recovery and retry gates; returns proposal only and mutates nothing."""
    recovery = classify_execution_recovery(receipt, checkpoint_events)
    if recovery["action"] != "safe_to_retry":
        return {"action": recovery["action"], "reason": "recovery_gate_not_retryable", "recovery": recovery}
    policy = retry_policy_decision(
        recovery, attempt_number, max_attempts, base_delay_seconds, max_delay_seconds,
        retry_marker_present=retry_marker_present,
        idempotency_key_present=isinstance(idempotency_key, str) and bool(idempotency_key.strip()),
    )
    if policy["action"] != "retry_scheduled":
        return {"action": policy["action"], "reason": "retry_policy_gate_rejected", "recovery": recovery, "policy": policy}
    reservation = reserve_execution(registry, idempotency_key, execution_payload, execution_id)
    if reservation["action"] == "blocked":
        return {"action": "blocked", "reason": "idempotency_reservation_rejected", "reservation": reservation}
    if reservation["action"] == "replay":
        return {"action": "replay", "reason": "idempotency_replay", "reservation": reservation, "recovery": recovery, "policy": policy}
    scheduling = schedule_retry(policy, receipt["workflow_id"], receipt["stage"], receipt["execution_id"], job_id, scheduled_at, jitter_seconds)
    if scheduling["action"] != "scheduled":
        return {"action": "blocked", "reason": "scheduling_rejected", "scheduling": scheduling}
    return {
        "action": "prepared",
        "reason": "retry_gates_passed",
        "recovery": recovery,
        "policy": policy,
        "reservation": reservation,
        "job": scheduling["job"],
    }
