import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore


class WorkerLeaseTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.job = {"schema": 1, "job_id": "j1", "workflow_id": "w1", "stage": "s1", "execution_id": "e1", "attempt_number": 2, "status": "queued", "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:00:00+00:00", "delay_seconds": 0, "jitter_seconds": 0, "cancelled_at": None}
        self.queue.enqueue(self.job)

    def tearDown(self):
        self.db.close()

    def test_claim_due(self):
        result = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)
        self.assertEqual(result["action"], "claimed")
        self.assertEqual(result["jobs"][0]["job"]["status"], "claimed")

    def test_claim_only_once(self):
        self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)
        self.assertEqual(self.leases.claim_due("2026-01-01T00:00:01Z", "worker-b", 30)["jobs"], [])

    def test_renew_owned_lease(self):
        lease = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)["jobs"][0]["lease"]
        result = self.leases.renew("j1", "worker-a", lease["lease_token"], "2026-01-01T00:00:10Z", 60)
        self.assertEqual(result["action"], "renewed")

    def test_expired_lease_cannot_renew(self):
        lease = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 5)["jobs"][0]["lease"]
        result = self.leases.renew("j1", "worker-a", lease["lease_token"], "2026-01-01T00:00:06Z", 60)
        self.assertEqual(result["reason"], "lease_expired")

    def test_release_requeues(self):
        lease = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)["jobs"][0]["lease"]
        result = self.leases.release("j1", "worker-a", lease["lease_token"], "2026-01-01T00:00:02Z")
        self.assertEqual(result["action"], "released")
        self.assertEqual(self.queue.get("j1")["job"]["status"], "queued")

    def test_complete_finalizes_and_removes_lease(self):
        lease = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)["jobs"][0]["lease"]
        result = self.leases.complete("j1", "worker-a", lease["lease_token"], "completed", "2026-01-01T00:00:02Z")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.queue.get("j1")["job"]["status"], "claimed")

    def test_wrong_worker_blocked(self):
        lease = self.leases.claim_due("2026-01-01T00:00:01Z", "worker-a", 30)["jobs"][0]["lease"]
        self.assertEqual(self.leases.release("j1", "worker-b", lease["lease_token"], "2026-01-01T00:00:02Z")["action"], "blocked")

    def test_invalid_parameters_block(self):
        self.assertEqual(self.leases.claim_due("bad", "w", 0)["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
