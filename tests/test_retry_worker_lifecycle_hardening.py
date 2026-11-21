import json
import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore


class RetryWorkerLifecycleHardeningTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.now = "2026-01-01T00:00:01+00:00"
        self.jobs = []
        for job_id in ("a", "b"):
            job = {
                "schema": 1, "job_id": job_id, "workflow_id": "wf", "stage": "stage",
                "execution_id": "exec-" + job_id, "attempt_number": 1, "status": "queued",
                "scheduled_at": self.now, "due_at": self.now,
            }
            self.queue.enqueue(job)
            self.jobs.append(job)

    def tearDown(self):
        self.db.close()

    def claim(self, limit=1):
        return self.leases.claim_due(self.now, "worker", 30, limit)

    def test_claim_assigns_unique_fencing_tokens_per_job(self):
        result = self.claim(2)
        tokens = [item["lease"]["lease_token"] for item in result["jobs"]]
        self.assertEqual(len(tokens), 2)
        self.assertEqual(len(set(tokens)), 2)

    def test_renew_requires_claimed_job_and_owned_unexpired_lease(self):
        lease = self.claim()["jobs"][0]["lease"]
        self.db.execute("UPDATE retry_jobs SET status='queued' WHERE job_id='a'")
        self.db.commit()
        result = self.leases.renew("a", "worker", lease["lease_token"], self.now, 30)
        self.assertEqual(result["reason"], "job_not_claimed")

    def test_release_missing_job_preserves_lease(self):
        lease = self.claim()["jobs"][0]["lease"]
        self.db.execute("DELETE FROM retry_jobs WHERE job_id='a'")
        self.db.commit()
        result = self.leases.release("a", "worker", lease["lease_token"], self.now)
        self.assertEqual(result["reason"], "job_not_claimed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 1)

    def test_complete_missing_job_preserves_lease(self):
        lease = self.claim()["jobs"][0]["lease"]
        self.db.execute("DELETE FROM retry_jobs WHERE job_id='a'")
        self.db.commit()
        result = self.leases.complete("a", "worker", lease["lease_token"], "completed", self.now)
        self.assertEqual(result["reason"], "job_not_claimed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 1)

    def test_invalid_payload_blocks_claim_without_partial_state(self):
        self.db.execute("UPDATE retry_jobs SET payload_json='not-json' WHERE job_id='a'")
        self.db.commit()
        result = self.claim()
        self.assertEqual(result["reason"], "job_payload_invalid")
        self.assertEqual(self.db.execute("SELECT status FROM retry_jobs WHERE job_id='a'").fetchone()[0], "queued")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 0)

    def test_invalid_payload_blocks_release_without_partial_state(self):
        lease = self.claim()["jobs"][0]["lease"]
        self.db.execute("UPDATE retry_jobs SET payload_json='not-json' WHERE job_id='a'")
        self.db.commit()
        result = self.leases.release("a", "worker", lease["lease_token"], self.now)
        self.assertEqual(result["reason"], "job_payload_invalid")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 1)

    def test_expired_reclaim_requeues_job_and_removes_lease(self):
        lease = self.claim()["jobs"][0]["lease"]
        result = self.leases.reclaim_expired("2026-01-01T00:00:40+00:00")
        self.assertEqual(result["action"], "reclaimed")
        self.assertEqual(self.queue.get("a")["job"]["status"], "queued")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 0)

    def test_expired_orphan_lease_is_reported_and_removed(self):
        self.db.execute("INSERT INTO retry_worker_leases VALUES('missing','worker','2025-12-31T23:59:00+00:00','token')")
        self.db.commit()
        result = self.leases.reclaim_expired("2026-01-01T00:00:00+00:00")
        self.assertEqual(result["jobs"][0]["action"], "orphan_lease_removed")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 0)

    def test_reclaim_invalid_payload_keeps_expired_lease(self):
        lease = self.claim()["jobs"][0]["lease"]
        self.db.execute("UPDATE retry_jobs SET payload_json='bad' WHERE job_id='a'")
        self.db.commit()
        result = self.leases.reclaim_expired("2026-01-01T00:00:40+00:00")
        self.assertEqual(result["reason"], "job_payload_invalid")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retry_worker_leases").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
