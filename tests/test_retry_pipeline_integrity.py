import json
import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore
from sentinel_core.atomic_retry_store import AtomicRetryPreparationStore
from sentinel_core.retry_pipeline_integrity import audit_retry_pipeline


class RetryPipelineIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.atomic = AtomicRetryPreparationStore(self.db)
        self.job = {
            "schema": 1, "job_id": "job-1", "workflow_id": "wf", "stage": "stage",
            "execution_id": "exec", "attempt_number": 1, "status": "queued",
            "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:00:01+00:00",
            "delay_seconds": 1, "jitter_seconds": 0, "cancelled_at": None,
        }
        self.queue.enqueue(self.job)
        self.atomic.prepare("idempotency-key", {}, "exec-atomic", {**self.job, "job_id": "atomic-1"})

    def tearDown(self):
        self.db.close()

    def test_clean_pipeline_is_valid(self):
        result = audit_retry_pipeline(self.db)
        self.assertTrue(result["valid"])
        self.assertEqual(result["counts"]["retry_jobs"], 1)
        self.assertEqual(result["counts"]["atomic_jobs"], 1)

    def test_claimed_job_without_lease_is_reported(self):
        self.db.execute("UPDATE retry_jobs SET status='claimed' WHERE job_id='job-1'")
        self.db.commit()
        result = audit_retry_pipeline(self.db)
        self.assertIn("claimed_job_without_lease", {f["code"] for f in result["findings"]})

    def test_orphan_lease_is_reported(self):
        self.db.execute("INSERT INTO retry_worker_leases VALUES('missing','worker','2026-01-01T00:00:00+00:00','token')")
        self.db.commit()
        result = audit_retry_pipeline(self.db)
        self.assertIn("lease_without_job", {f["code"] for f in result["findings"]})

    def test_payload_status_mismatch_is_reported(self):
        payload = json.loads(self.db.execute("SELECT payload_json FROM retry_jobs WHERE job_id='job-1'").fetchone()[0])
        payload["status"] = "failed"
        self.db.execute("UPDATE retry_jobs SET payload_json=? WHERE job_id='job-1'", (json.dumps(payload),))
        self.db.commit()
        result = audit_retry_pipeline(self.db)
        self.assertIn("retry_status_mismatch", {f["code"] for f in result["findings"]})

    def test_atomic_job_without_reservation_is_reported(self):
        self.db.execute("DELETE FROM retry_reservations")
        self.db.commit()
        result = audit_retry_pipeline(self.db)
        self.assertIn("atomic_job_without_reservation", {f["code"] for f in result["findings"]})

    def test_missing_tables_fail_closed(self):
        other = sqlite3.connect(":memory:")
        self.assertEqual(audit_retry_pipeline(other)["reason"], "tables_missing")
        other.close()


if __name__ == "__main__":
    unittest.main()
