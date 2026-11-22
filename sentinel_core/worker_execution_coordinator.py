"""Coordinate retry-job leases with registered task execution."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sentinel_core.task_execution_adapter import TaskExecutionAdapter
from sentinel_core.worker_leases import RetryWorkerLeaseStore


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _lease_fields(lease: Any) -> tuple[str, str] | None:
    if not isinstance(lease, dict):
        return None
    worker_id = lease.get("worker_id")
    token = lease.get("lease_token")
    if not isinstance(worker_id, str) or not worker_id.strip():
        return None
    if not isinstance(token, str) or not token.strip():
        return None
    return worker_id, token


class WorkerExecutionCoordinator:
    """Compose the existing lease store with synchronous task dispatch.

    The lease token fences storage transitions. Long-running handlers need
    caller-managed heartbeats through renew(); this class starts no threads.
    """

    def __init__(
        self,
        lease_store: RetryWorkerLeaseStore,
        task_executor: TaskExecutionAdapter,
    ):
        self.lease_store = lease_store
        self.task_executor = task_executor

    def claim_due(
        self, now: str, worker_id: str, lease_seconds: int, limit: int = 1
    ) -> dict:
        """Requeue expired claims before atomically claiming due jobs."""
        reclaimed = self.lease_store.reclaim_expired(now, limit=limit)
        if reclaimed.get("action") != "reclaimed":
            return {
                "action": "blocked",
                "reason": "expired_lease_reclaim_failed",
                "details": reclaimed,
            }
        claimed = self.lease_store.claim_due(now, worker_id, lease_seconds, limit)
        if claimed.get("action") != "claimed":
            return claimed
        return {
            "action": "claimed",
            "worker_id": worker_id,
            "reclaimed": reclaimed.get("jobs", []),
            "jobs": claimed.get("jobs", []),
        }

    def renew(self, job_id: str, lease: Any, now: str, lease_seconds: int) -> dict:
        fields = _lease_fields(lease)
        if not isinstance(job_id, str) or not job_id.strip() or fields is None:
            return {"action": "blocked", "reason": "lease_identity_invalid"}
        worker_id, token = fields
        return self.lease_store.renew(job_id, worker_id, token, now, lease_seconds)

    def release(self, job_id: str, lease: Any, now: str) -> dict:
        fields = _lease_fields(lease)
        if not isinstance(job_id, str) or not job_id.strip() or fields is None:
            return {"action": "blocked", "reason": "lease_identity_invalid"}
        worker_id, token = fields
        return self.lease_store.release(job_id, worker_id, token, now)

    def complete(self, job_id: str, lease: Any, outcome: str, now: str) -> dict:
        fields = _lease_fields(lease)
        if not isinstance(job_id, str) or not job_id.strip() or fields is None:
            return {"action": "blocked", "reason": "lease_identity_invalid"}
        worker_id, token = fields
        return self.lease_store.complete(job_id, worker_id, token, outcome, now)

    def execute_claimed(
        self,
        job: Any,
        lease: Any,
        task: Any,
        started_at: str,
        finished_at: str,
        lease_seconds: int,
        context: Any = None,
    ) -> dict:
        """Execute one leased task and finalize it with the same lease token.

        A blocked task is released back to the queue. Handler success/failure is
        finalized as completed/failed. Explicit finish time prevents a stale
        start timestamp from being used to approve a late completion.
        """
        if not isinstance(job, dict) or job.get("schema") != 1:
            return {"action": "blocked", "reason": "job_invalid"}
        job_id = job.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip() or job.get("status") != "claimed":
            return {"action": "blocked", "reason": "job_not_claimed"}
        fields = _lease_fields(lease)
        if fields is None:
            return {"action": "blocked", "reason": "lease_identity_invalid"}
        if not isinstance(task, dict):
            return {"action": "blocked", "reason": "task_invalid"}
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            return {"action": "blocked", "reason": "task_id_invalid"}
        expected_task_id = job.get("task_id")
        if context is not None and not isinstance(context, dict):
            return {"action": "blocked", "reason": "context_invalid"}
        start = _parse_time(started_at)
        finish = _parse_time(finished_at)
        if start is None or finish is None or finish < start:
            return {"action": "blocked", "reason": "execution_times_invalid"}
        if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or lease_seconds < 1:
            return {"action": "blocked", "reason": "lease_seconds_invalid"}
        if expected_task_id is not None and expected_task_id != task_id:
            worker_id, token = fields
            released = self.lease_store.release(job_id, worker_id, token, finished_at)
            if released.get("action") == "released":
                return {"action": "blocked", "reason": "task_job_mismatch", "lease": released}
            return {"action": "blocked", "reason": "lease_release_rejected", "lease": released}

        worker_id, token = fields
        heartbeat = self.lease_store.renew(
            job_id, worker_id, token, started_at, lease_seconds
        )
        if heartbeat.get("action") != "renewed":
            return {"action": "blocked", "reason": "lease_not_active", "lease": heartbeat}

        execution_context = dict(context or {})
        execution_context["worker"] = {
            "worker_id": worker_id,
            "lease_token": token,
            "lease_expires_at": heartbeat["lease_expires_at"],
        }
        execution_context["retry"] = {
            "job_id": job_id,
            "workflow_id": job.get("workflow_id"),
            "stage": job.get("stage"),
            "execution_id": job.get("execution_id"),
            "attempt_number": job.get("attempt_number"),
        }
        try:
            execution = self.task_executor.execute(task, execution_context)
        except Exception as exc:
            execution = {
                "action": "failed",
                "task_id": task_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

        action = execution.get("action")
        if action in {"completed", "failed"}:
            outcome = action
            finalized = self.lease_store.complete(
                job_id, worker_id, token, outcome, finished_at
            )
            if finalized.get("action") == "completed":
                return {
                    "action": outcome,
                    "job_id": job_id,
                    "execution": execution,
                    "lease": finalized,
                }
            return {
                "action": "blocked",
                "reason": "lease_finalize_rejected",
                "execution": execution,
                "lease": finalized,
            }

        released = self.lease_store.release(job_id, worker_id, token, finished_at)
        if released.get("action") == "released":
            return {
                "action": "blocked",
                "reason": "task_execution_blocked",
                "execution": execution,
                "lease": released,
            }
        return {
            "action": "blocked",
            "reason": "lease_release_rejected",
            "execution": execution,
            "lease": released,
        }
