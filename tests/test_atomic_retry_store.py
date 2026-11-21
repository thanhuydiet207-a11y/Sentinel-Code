import sqlite3
import unittest

from sentinel_core.atomic_retry_store import AtomicRetryPreparationStore


class AtomicRetryPreparationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = AtomicRetryPreparationStore(self.db)
        self.job = {"schema": 1, "job_id": "job-1", "workflow_id": "wf", "stage": "s", "execution_id": "exec", "attempt_number": 2, "status": "queued", "scheduled_at": "2026-01-01T00:00:00+00:00", "due_at": "2026-01-01T00:01:00+00:00"}

    def tearDown(self):
        self.db.close()

    def test_atomic_prepare_creates_reservation_and_job(self):
        result = self.store.prepare("key", {"x": 1}, "exec-1", self.job)
        self.assertEqual(result["action"], "prepared")
        self.assertEqual(self.store.counts(), {"reservations": 1, "jobs": 1})

    def test_replay_does_not_duplicate_job(self):
        self.store.prepare("key", {"x": 1}, "exec-1", self.job)
        replay = self.store.prepare("key", {"x": 1}, "exec-2", {**self.job, "job_id": "job-2"})
        self.assertEqual(replay["action"], "replay")
        self.assertEqual(self.store.counts(), {"reservations": 1, "jobs": 1})

    def test_conflicting_payload_blocked(self):
        self.store.prepare("key", {"x": 1}, "exec-1", self.job)
        result = self.store.prepare("key", {"x": 2}, "exec-2", {**self.job, "job_id": "job-2"})
        self.assertEqual(result["reason"], "idempotency_key_payload_conflict")

    def test_job_unique_conflict_rolls_back_reservation(self):
        self.store.prepare("key-a", {"x": 1}, "exec-a", self.job)
        result = self.store.prepare("key-b", {"x": 2}, "exec-b", self.job)
        self.assertEqual(result["reason"], "unique_constraint_conflict")
        self.assertEqual(self.store.counts(), {"reservations": 1, "jobs": 1})
        self.assertEqual(self.store.prepare("key-b", {"x": 2}, "exec-b", {**self.job, "job_id": "job-2"})["action"], "prepared")

    def test_job_lookup(self):
        self.store.prepare("key", {"x": 1}, "exec-1", self.job)
        self.assertEqual(self.store.get_job("job-1")["job"]["status"], "queued")
        self.assertEqual(self.store.get_job("missing")["action"], "not_found")

    def test_invalid_inputs_fail_closed(self):
        self.assertEqual(self.store.prepare("", {}, "exec", self.job)["action"], "blocked")
        self.assertEqual(self.store.prepare("key", {}, "exec", {})["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
