import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore


class RetryFaultInjectionTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.job = {"schema": 1, "job_id": "job-crash", "workflow_id": "wf", "stage": "stage", "execution_id": "exec", "attempt_number": 1, "status": "queued", "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:00:00+00:00", "delay_seconds": 0, "jitter_seconds": 0, "cancelled_at": None}
        self.queue.enqueue(self.job)

    def tearDown(self):
        self.db.close()

    def test_crash_after_claim_recovered_after_lease_expiry(self):
        first = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 5)["jobs"][0]
        self.assertEqual(first["job"]["status"], "claimed")
        self.assertEqual(self.leases.claim_due("2026-01-01T00:00:02Z", "worker-b", 5)["jobs"], [])
        reclaimed = self.leases.reclaim_expired("2026-01-01T00:00:06Z")
        self.assertEqual(len(reclaimed["jobs"]), 1)
        self.assertEqual(self.queue.get("job-crash")["job"]["status"], "queued")
        second = self.leases.claim_due("2026-01-01T00:00:07Z", "worker-b", 10)["jobs"][0]
        self.assertEqual(second["lease"]["worker_id"], "worker-b")

    def test_stale_worker_cannot_finalize_after_reclaim(self):
        first = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 5)["jobs"][0]["lease"]
        self.leases.reclaim_expired("2026-01-01T00:00:06Z")
        second = self.leases.claim_due("2026-01-01T00:00:07Z", "worker-b", 10)["jobs"][0]["lease"]
        stale = self.leases.complete("job-crash", "worker-a", first["lease_token"], "completed", "2026-01-01T00:00:08Z")
        self.assertEqual(stale["action"], "blocked")
        fresh = self.leases.complete("job-crash", "worker-b", second["lease_token"], "completed", "2026-01-01T00:00:08Z")
        self.assertEqual(fresh["status"], "completed")

    def test_reclaim_limit_and_invalid_time(self):
        self.assertEqual(self.leases.reclaim_expired("bad")["action"], "blocked")
        self.assertEqual(self.leases.reclaim_expired("2026-01-01T00:00:01Z", 0)["action"], "blocked")

    def test_reclaim_only_expired(self):
        self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 60)
        result = self.leases.reclaim_expired("2026-01-01T00:00:02Z")
        self.assertEqual(result["jobs"], [])


if __name__ == "__main__":
    unittest.main()
