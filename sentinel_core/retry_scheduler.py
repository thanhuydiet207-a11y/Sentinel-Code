"""Pure retry scheduling and cancellation decisions; no background worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def schedule_retry(
    policy_decision: Any,
    workflow_id: str,
    stage: str,
    execution_id: str,
    job_id: str,
    scheduled_at: str,
    jitter_seconds: int = 0,
) -> dict:
    """Build a validated retry schedule record from an approved policy decision."""
    if not isinstance(policy_decision, dict) or policy_decision.get("action") != "retry_scheduled":
        return {"action": "blocked", "reason": "retry_policy_not_approved"}
    for field, value in (("workflow_id", workflow_id), ("stage", stage), ("execution_id", execution_id), ("job_id", job_id)):
        if not isinstance(value, str) or not value.strip():
            return {"action": "blocked", "reason": f"{field}_required"}
    if not isinstance(policy_decision.get("delay_seconds"), int) or isinstance(policy_decision.get("delay_seconds"), bool) or policy_decision["delay_seconds"] < 0:
        return {"action": "blocked", "reason": "policy_delay_invalid"}
    base = _parse_time(scheduled_at)
    if base is None:
        return {"action": "blocked", "reason": "scheduled_at_invalid"}
    if not isinstance(jitter_seconds, int) or isinstance(jitter_seconds, bool) or jitter_seconds < 0:
        return {"action": "blocked", "reason": "jitter_invalid"}
    due = base + timedelta(seconds=policy_decision["delay_seconds"] + jitter_seconds)
    return {
        "action": "scheduled",
        "job": {
            "schema": 1,
            "job_id": job_id,
            "workflow_id": workflow_id,
            "stage": stage,
            "execution_id": execution_id,
            "attempt_number": policy_decision.get("next_attempt_number"),
            "status": "queued",
            "scheduled_at": base.isoformat(),
            "due_at": due.isoformat(),
            "delay_seconds": policy_decision["delay_seconds"],
            "jitter_seconds": jitter_seconds,
            "cancelled_at": None,
        },
    }


def evaluate_retry_job(job: Any, now: str, cancel_requested: bool = False) -> dict:
    """Determine whether a retry job remains queued, is due, or is cancelled."""
    if not isinstance(job, dict) or job.get("schema") != 1:
        return {"action": "blocked", "reason": "job_invalid"}
    if job.get("status") not in {"queued", "cancelled"}:
        return {"action": "blocked", "reason": "job_status_invalid"}
    current = _parse_time(now)
    due = _parse_time(job.get("due_at"))
    if current is None or due is None:
        return {"action": "blocked", "reason": "time_invalid"}
    if cancel_requested or job.get("status") == "cancelled":
        return {"action": "cancelled", "reason": "cancellation_requested", "job_id": job.get("job_id")}
    if current < due:
        return {"action": "queued", "reason": "not_due", "due_at": job["due_at"]}
    return {"action": "due", "reason": "scheduled_time_reached", "job_id": job.get("job_id"), "attempt_number": job.get("attempt_number")}


def cancel_retry_job(job: Any, cancelled_at: str) -> dict:
    """Return a cancelled copy of a queued job; never mutate the input."""
    if not isinstance(job, dict) or job.get("schema") != 1 or job.get("status") != "queued":
        return {"action": "blocked", "reason": "job_not_cancellable"}
    if _parse_time(cancelled_at) is None:
        return {"action": "blocked", "reason": "cancelled_at_invalid"}
    updated = dict(job)
    updated["status"] = "cancelled"
    updated["cancelled_at"] = cancelled_at
    return {"action": "cancelled", "job": updated}
