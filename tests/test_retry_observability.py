import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore
from sentinel_core.atomic_retry_store import AtomicRetryPreparationStore
from sentinel_core.retry_observability import retry_queue_snapshot


class RetryObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.atomic = AtomicRetryPreparationStore(self.db)
        self.job = {"schema": 1, "job_id": "job-observe", "workflow_id": "wf", "stage": "s", "execution_id": "exec", "attempt_number": 1, "status": "queued", "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:00:01+00:00", "delay_seconds": 0, "jitter_seconds": 0, "cancelled_at": None}
        self.queue.enqueue(self.job)
        self.atomic.prepare("key", {}, "exec-atomic", {**self.job, "job_id": "atomic-job"})

    def tearDown(self):
        self.db.close()

    def test_snapshot_reports_due_and_status_counts(self):
        result = retry_queue_snapshot(self.db, "2026-01-01T00:00:02+00:00")
        self.assertEqual(result["action"], "snapshot")
        self.assertEqual(result["queue"]["queued"], 1)
        self.assertEqual(result["due_queued"], 1)
        self.assertEqual(result["atomic_jobs"]["queued"], 1)
        self.assertEqual(result["reservations"]["reserved"], 1)

    def test_snapshot_reports_expired_lease(self):
        self.leases.claim_due("2026-01-01T00:00:02Z", "worker", 2)
        result = retry_queue_snapshot(self.db, "2026-01-01T00:00:05+00:00")
        self.assertEqual(result["leases"]["active"], 1)
        self.assertEqual(result["leases"]["expired"], 1)

    def test_invalid_timestamp_and_missing_tables_fail_closed(self):
        self.assertEqual(retry_queue_snapshot(self.db, "")["action"], "blocked")
        other = sqlite3.connect(":memory:")
        self.assertEqual(retry_queue_snapshot(other, "now")["reason"], "tables_missing")
        other.close()


if __name__ == "__main__":
    unittest.main()
