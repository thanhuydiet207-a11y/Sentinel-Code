import sqlite3
import unittest

from sentinel_core.execution_receipts import create_execution_receipt, verify_execution_receipt, reconcile_execution_receipts
from sentinel_core.retry_integration import prepare_retry
from sentinel_core.retry_queue_store import RetryQueueStore
from sentinel_core.worker_leases import RetryWorkerLeaseStore


class RetryPipelineEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.queue = RetryQueueStore(self.db)
        self.leases = RetryWorkerLeaseStore(self.db)
        self.receipt = create_execution_receipt(
            "wf-e2e", "review", {"allowed": True}, "exec-original",
            outcome="failed", details={"side_effects": "none"},
        )
        self.checkpoints = [{"stage": "review", "status": "failed"}]

    def tearDown(self):
        self.db.close()

    def prepare(self):
        return prepare_retry(
            receipt=self.receipt,
            checkpoint_events=self.checkpoints,
            registry={},
            idempotency_key="e2e-idempotency",
            execution_payload={"workflow": "wf-e2e", "stage": "review", "input_digest": "abc123"},
            execution_id="exec-retry",
            job_id="job-e2e",
            scheduled_at="2026-01-01T00:00:00Z",
            attempt_number=1,
            max_attempts=3,
            retry_marker_present=True,
        )

    def test_end_to_end_prepare_persist_claim_complete(self):
        proposal = self.prepare()
        self.assertEqual(proposal["action"], "prepared")
        self.assertTrue(verify_execution_receipt(self.receipt)["valid"])
        self.assertEqual(self.queue.enqueue(proposal["job"])["action"], "stored")
        claimed = self.leases.claim_due("2026-01-01T00:00:31Z", "worker-a", 60)
        lease = claimed["jobs"][0]["lease"]
        completed = self.leases.complete("job-e2e", "worker-a", lease["lease_token"], "completed", "2026-01-01T00:00:32Z")
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.queue.get("job-e2e")["job"]["status"], "completed")

    def test_end_to_end_crash_reclaim_and_reclaim_by_second_worker(self):
        proposal = self.prepare()
        self.queue.enqueue(proposal["job"])
        first = self.leases.claim_due("2026-01-01T00:00:31Z", "worker-a", 2)["jobs"][0]["lease"]
        recovered = self.leases.reclaim_expired("2026-01-01T00:00:34Z")
        self.assertEqual(len(recovered["jobs"]), 1)
        second = self.leases.claim_due("2026-01-01T00:00:35Z", "worker-b", 60)["jobs"][0]["lease"]
        self.assertNotEqual(first["lease_token"], second["lease_token"])
        stale = self.leases.complete("job-e2e", "worker-a", first["lease_token"], "completed", "2026-01-01T00:00:36Z")
        self.assertEqual(stale["action"], "blocked")
        final = self.leases.complete("job-e2e", "worker-b", second["lease_token"], "completed", "2026-01-01T00:00:36Z")
        self.assertEqual(final["status"], "completed")

    def test_receipt_checkpoint_reconciliation(self):
        result = reconcile_execution_receipts([self.receipt], self.checkpoints)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["matches"]), 1)


if __name__ == "__main__":
    unittest.main()
