import sqlite3
import unittest

from sentinel_core.retry_queue_store import RetryQueueStore


class RetryQueueInputValidationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = RetryQueueStore(self.db)
        self.job = {
            "schema": 1, "job_id": "job", "workflow_id": "wf", "stage": "stage",
            "execution_id": "exec", "attempt_number": 1, "status": "queued",
            "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:00:01Z",
        }

    def tearDown(self):
        self.db.close()

    def test_blank_required_fields_rejected(self):
        job = {**self.job, "workflow_id": " "}
        self.assertEqual(self.store.enqueue(job)["reason"], "job_fields_invalid")

    def test_invalid_or_naive_timestamps_rejected(self):
        for value in ("bad-time", "2026-01-01T00:00:00"):
            job = {**self.job, "due_at": value}
            self.assertEqual(self.store.enqueue(job)["reason"], "job_timestamp_invalid")

    def test_attempt_number_must_be_positive_integer_not_bool(self):
        for value in (0, -1, True, "2"):
            job = {**self.job, "attempt_number": value}
            self.assertEqual(self.store.enqueue(job)["reason"], "attempt_number_invalid")

    def test_query_requires_timezone_aware_timestamp(self):
        self.assertEqual(self.store.list_due("invalid")["action"], "blocked")
        self.assertEqual(self.store.list_due("2026-01-01T00:00:00")["action"], "blocked")

    def test_valid_iso_timestamp_with_z_is_accepted(self):
        self.assertEqual(self.store.enqueue(self.job)["action"], "stored")


if __name__ == "__main__":
    unittest.main()
