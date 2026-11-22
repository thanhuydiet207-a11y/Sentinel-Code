"""Retry policy decisions and crash-safe retry job planning."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


class RetryPolicyEngine:
    """Pure retry decision engine; callers persist the returned job atomically."""

    def __init__(self, max_attempts: int = 3, base_delay_seconds: int = 5,
                 max_delay_seconds: int = 300, jitter_ratio: float = 0.0):
        if (not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1
                or not isinstance(base_delay_seconds, int) or isinstance(base_delay_seconds, bool) or base_delay_seconds < 0
                or not isinstance(max_delay_seconds, int) or isinstance(max_delay_seconds, bool) or max_delay_seconds < 0
                or not isinstance(jitter_ratio, (int, float)) or isinstance(jitter_ratio, bool)
                or jitter_ratio < 0 or jitter_ratio > 1):
            raise ValueError("retry_policy_parameters_invalid")
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.jitter_ratio = float(jitter_ratio)

    def decide(self, attempt_number: int, failure_kind: str, now: str,
                retry_after_seconds: int | None = None, jitter_sample: float = 0.5) -> dict:
        current = _parse_time(now)
        if current is None or not isinstance(attempt_number, int) or isinstance(attempt_number, bool) or attempt_number < 1:
            return {"action": "blocked", "reason": "retry_decision_parameters_invalid"}
        if not isinstance(failure_kind, str) or not failure_kind.strip():
            return {"action": "blocked", "reason": "failure_kind_invalid"}
        if not isinstance(jitter_sample, (int, float)) or isinstance(jitter_sample, bool) or not 0 <= jitter_sample <= 1:
            return {"action": "blocked", "reason": "jitter_sample_invalid"}
        if retry_after_seconds is not None and (not isinstance(retry_after_seconds, int) or isinstance(retry_after_seconds, bool) or retry_after_seconds < 0):
            return {"action": "blocked", "reason": "retry_after_invalid"}
        if failure_kind.lower() in {"permanent", "validation", "cancelled", "auth"}:
            return {"action": "stop", "reason": "non_retryable_failure", "attempt_number": attempt_number}
        if attempt_number >= self.max_attempts:
            return {"action": "stop", "reason": "attempt_limit_reached", "attempt_number": attempt_number}
        exponential = min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (attempt_number - 1)))
        jitter_multiplier = 1 + ((jitter_sample * 2 - 1) * self.jitter_ratio)
        delay = max(0, int(round(exponential * jitter_multiplier)))
        if retry_after_seconds is not None:
            delay = max(delay, retry_after_seconds)
        due = current + timedelta(seconds=delay)
        return {"action": "retry", "attempt_number": attempt_number + 1,
                "delay_seconds": delay, "scheduled_at": current.isoformat(),
                "due_at": due.isoformat(), "failure_kind": failure_kind}

    def build_retry_job(self, failed_job: Any, decision: Any, retry_job_id: str) -> dict:
        if not isinstance(failed_job, dict) or failed_job.get("schema") != 1:
            return {"action": "blocked", "reason": "failed_job_invalid"}
        if not isinstance(decision, dict) or decision.get("action") != "retry":
            return {"action": "blocked", "reason": "retry_decision_invalid"}
        if not isinstance(retry_job_id, str) or not retry_job_id.strip():
            return {"action": "blocked", "reason": "retry_job_id_invalid"}
        for key in ("workflow_id", "stage", "execution_id"):
            if not isinstance(failed_job.get(key), str) or not failed_job[key].strip():
                return {"action": "blocked", "reason": "failed_job_fields_invalid"}
        return {"action": "planned", "job": {
            "schema": 1, "job_id": retry_job_id, "workflow_id": failed_job["workflow_id"],
            "stage": failed_job["stage"], "execution_id": failed_job["execution_id"],
            "attempt_number": decision["attempt_number"], "status": "queued",
            "scheduled_at": decision["scheduled_at"], "due_at": decision["due_at"],
            "task_id": failed_job.get("task_id"), "parent_job_id": failed_job.get("job_id"),
            "failure_kind": decision.get("failure_kind")}}


class RetryRecoveryCoordinator:
    """Plan and persist a retry; duplicate job IDs fail closed at the queue store."""

    def __init__(self, policy: RetryPolicyEngine, queue_store: Any):
        self.policy = policy
        self.queue_store = queue_store

    def recover(self, failed_job: Any, attempt_number: int, failure_kind: str,
                now: str, retry_job_id: str, retry_after_seconds: int | None = None,
                jitter_sample: float = 0.5) -> dict:
        decision = self.policy.decide(attempt_number, failure_kind, now,
                                    retry_after_seconds, jitter_sample)
        if decision.get("action") != "retry":
            return decision
        planned = self.policy.build_retry_job(failed_job, decision, retry_job_id)
        if planned.get("action") != "planned":
            return planned
        stored = self.queue_store.enqueue(planned["job"])
        if stored.get("action") != "stored":
            return {"action": "blocked", "reason": "retry_persist_failed", "details": stored}
        return {"action": "scheduled", "job": planned["job"], "decision": decision}
