import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore


class RetryQueueStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.store = RetryQueueStore(self.connection)
        self.job = {
            "schema": 1, "job_id": "job-1", "workflow_id": "wf-1", "stage": "scan",
            "execution_id": "exec-1", "attempt_number": 2, "status": "queued",
            "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:01:00+00:00",
            "delay_seconds": 60, "jitter_seconds": 0, "cancelled_at": None,
        }

    def tearDown(self):
        self.connection.close()

    def test_enqueue_and_read(self):
        self.assertEqual(self.store.enqueue(self.job)["action"], "stored")
        self.assertEqual(self.store.get("job-1")["job"]["status"], "queued")

    def test_duplicate_job_id_rejected(self):
        self.store.enqueue(self.job)
        self.assertEqual(self.store.enqueue(self.job)["reason"], "job_id_duplicate")

    def test_due_listing(self):
        self.store.enqueue(self.job)
        self.assertEqual(len(self.store.list_due("2026-01-01T00:01:00+00:00")["jobs"]), 1)
        self.assertEqual(len(self.store.list_due("2026-01-01T00:00:30+00:00")["jobs"]), 0)

    def test_cancel_job_transactionally(self):
        self.store.enqueue(self.job)
        result = self.store.cancel("job-1", "2026-01-01T00:00:20+00:00")
        self.assertEqual(result["action"], "cancelled")
        self.assertEqual(self.store.get("job-1")["job"]["status"], "cancelled")
        self.assertEqual(self.store.list_due("2026-01-02T00:00:00+00:00")["jobs"], [])

    def test_cannot_cancel_twice_or_nonqueued(self):
        self.store.enqueue(self.job)
        self.store.cancel("job-1", "2026-01-01T00:00:20+00:00")
        self.assertEqual(self.store.cancel("job-1", "2026-01-01T00:00:30+00:00")["action"], "blocked")

    def test_missing_job(self):
        self.assertEqual(self.store.get("missing")["action"], "not_found")
        self.assertEqual(self.store.cancel("missing", "2026-01-01T00:00:30+00:00")["action"], "not_found")

    def test_invalid_enqueue_and_list(self):
        self.assertEqual(self.store.enqueue({})["action"], "blocked")
        self.assertEqual(self.store.list_due("", 0)["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
