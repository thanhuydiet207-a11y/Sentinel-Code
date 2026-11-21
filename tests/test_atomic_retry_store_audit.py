import sqlite3
import unittest

from sentinel_core.atomic_retry_store import AtomicRetryPreparationStore


class AtomicRetryStoreAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = AtomicRetryPreparationStore(self.db)
        self.job = {"schema": 1, "job_id": "job-audit", "workflow_id": "wf", "stage": "s", "execution_id": "exec", "attempt_number": 1, "status": "queued", "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:01:00+00:00"}

    def tearDown(self):
        self.db.close()

    def test_clean_store_audit(self):
        self.store.prepare("key", {}, "exec-1", self.job)
        result = self.store.audit()
        self.assertTrue(result["valid"])
        self.assertEqual(result["reservation_count"], 1)
        self.assertEqual(result["job_count"], 1)

    def test_reservation_without_job_detected(self):
        self.db.execute("INSERT INTO retry_reservations(key_digest,payload_digest,execution_id,status) VALUES('k','p','e','reserved')")
        result = self.store.audit()
        self.assertFalse(result["valid"])
        self.assertEqual(result["errors"][0]["kind"], "reservation_without_job")

    def test_job_payload_status_mismatch_detected(self):
        self.store.prepare("key", {}, "exec-1", self.job)
        self.db.execute("UPDATE atomic_retry_jobs SET status='completed' WHERE job_id='job-audit'")
        result = self.store.audit()
        self.assertFalse(result["valid"])
        self.assertIn("job_status_mismatch", [e["kind"] for e in result["errors"]])

    def test_job_without_reservation_detected(self):
        self.db.execute("INSERT INTO atomic_retry_jobs(job_id,key_digest,status,job_json) VALUES('job-orphan','missing','queued','{}')")
        result = self.store.audit()
        self.assertFalse(result["valid"])
        self.assertIn("job_without_reservation", [e["kind"] for e in result["errors"]])


if __name__ == "__main__":
    unittest.main()
