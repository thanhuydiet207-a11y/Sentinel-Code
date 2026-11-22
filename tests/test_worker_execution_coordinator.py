import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.task_execution_adapter import TaskExecutionAdapter
from sentinel_core.task_handler_registry import TaskHandlerRegistry
from sentinel_core.worker_execution_coordinator import WorkerExecutionCoordinator
from sentinel_core.worker_leases import RetryWorkerLeaseStore


class WorkerExecutionCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.registry = TaskHandlerRegistry()
        self.executor = TaskExecutionAdapter(self.registry)
        self.coordinator = WorkerExecutionCoordinator(self.leases, self.executor)
        self.now = "2026-01-01T00:00:01+00:00"
        self.job = {
            "schema": 1,
            "job_id": "job-1",
            "task_id": "task-1",
            "workflow_id": "workflow-1",
            "stage": "stage-1",
            "execution_id": "execution-1",
            "attempt_number": 1,
            "status": "queued",
            "scheduled_at": self.now,
            "due_at": self.now,
        }
        self.queue.enqueue(self.job)
        self.task = {
            "task_id": "task-1",
            "handler": "echo",
            "handler_version": "1",
            "input": {"value": "ok"},
        }

    def tearDown(self):
        self.db.close()

    def claim(self, worker_id="worker-a", lease_seconds=30):
        return self.coordinator.claim_due(self.now, worker_id, lease_seconds)

    def test_claim_reclaims_expired_before_claiming_due_jobs(self):
        first = self.claim()
        lease = first["jobs"][0]["lease"]
        self.leases.renew("job-1", "worker-a", lease["lease_token"], self.now, 1)
        reclaimed = self.coordinator.claim_due(
            "2026-01-01T00:00:03+00:00", "worker-b", 30
        )
        self.assertEqual(reclaimed["action"], "claimed")
        self.assertEqual(reclaimed["reclaimed"][0]["job_id"], "job-1")
        self.assertEqual(reclaimed["jobs"][0]["lease"]["worker_id"], "worker-b")
        self.assertNotEqual(
            reclaimed["jobs"][0]["lease"]["lease_token"], lease["lease_token"]
        )

    def test_successful_execution_finalizes_job(self):
        seen = []
        self.registry.register(
            "echo",
            lambda payload, context=None: seen.append(context) or payload,
            "1",
        )
        claimed = self.claim()["jobs"][0]
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            self.now, "2026-01-01T00:00:02+00:00", 30,
            {"trace_id": "trace-1"},
        )
        self.assertEqual(result["action"], "completed")
        self.assertEqual(self.queue.get("job-1")["job"]["status"], "completed")
        self.assertEqual(seen[0]["trace_id"], "trace-1")
        self.assertEqual(seen[0]["worker"]["worker_id"], "worker-a")
        self.assertEqual(seen[0]["retry"]["execution_id"], "execution-1")

    def test_handler_failure_finalizes_job_as_failed(self):
        def fail(_payload, context=None):
            raise RuntimeError("handler failed")
        self.registry.register("echo", fail)
        claimed = self.claim()["jobs"][0]
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            self.now, "2026-01-01T00:00:02+00:00", 30,
        )
        self.assertEqual(result["action"], "failed")
        self.assertEqual(self.queue.get("job-1")["job"]["status"], "failed")
        self.assertEqual(result["execution"]["error_type"], "RuntimeError")

    def test_blocked_task_is_released_for_recovery(self):
        claimed = self.claim()["jobs"][0]
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            self.now, "2026-01-01T00:00:02+00:00", 30,
        )
        self.assertEqual(result["reason"], "task_execution_blocked")
        self.assertEqual(self.queue.get("job-1")["job"]["status"], "queued")

    def test_expired_or_stale_worker_cannot_execute(self):
        claimed = self.coordinator.claim_due(self.now, "worker-a", 1)["jobs"][0]
        self.coordinator.claim_due(
            "2026-01-01T00:00:03+00:00", "worker-b", 30
        )
        calls = []
        self.registry.register("echo", lambda payload, context=None: calls.append(payload))
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            "2026-01-01T00:00:03+00:00", "2026-01-01T00:00:04+00:00", 30,
        )
        self.assertEqual(result["reason"], "lease_not_active")
        self.assertEqual(calls, [])

    def test_task_job_mismatch_is_rejected_before_handler(self):
        claimed = self.claim()["jobs"][0]
        calls = []
        self.registry.register("echo", lambda payload, context=None: calls.append(payload))
        mismatched = dict(self.task, task_id="another-task")
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], mismatched,
            self.now, "2026-01-01T00:00:02+00:00", 30,
        )
        self.assertEqual(result["reason"], "task_job_mismatch")
        self.assertEqual(calls, [])

    def test_completion_after_lease_expiry_is_rejected(self):
        self.registry.register("echo", lambda payload, context=None: payload)
        claimed = self.claim(lease_seconds=2)["jobs"][0]
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            self.now, "2026-01-01T00:00:05+00:00", 2,
        )
        self.assertEqual(result["reason"], "lease_finalize_rejected")
        self.assertEqual(self.queue.get("job-1")["job"]["status"], "claimed")

    def test_worker_context_cannot_be_spoofed_by_caller(self):
        seen = []
        self.registry.register("echo", lambda payload, context=None: seen.append(context) or payload)
        claimed = self.claim()["jobs"][0]
        result = self.coordinator.execute_claimed(
            claimed["job"], claimed["lease"], self.task,
            self.now, "2026-01-01T00:00:02+00:00", 30,
            {"worker": {"worker_id": "forged"}, "retry": {"job_id": "forged"}},
        )
        self.assertEqual(result["action"], "completed")
        self.assertEqual(seen[0]["worker"]["worker_id"], "worker-a")
        self.assertEqual(seen[0]["retry"]["job_id"], "job-1")


if __name__ == "__main__":
    unittest.main()
