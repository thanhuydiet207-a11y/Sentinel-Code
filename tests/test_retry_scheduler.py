import copy
import unittest

from sentinel_core.retry_scheduler import schedule_retry, evaluate_retry_job, cancel_retry_job


class RetrySchedulerTests(unittest.TestCase):
    def policy(self):
        return {"action": "retry_scheduled", "delay_seconds": 60, "next_attempt_number": 2}

    def schedule(self, at="2026-01-01T00:00:00Z", jitter=0):
        return schedule_retry(self.policy(), "wf-1", "stage-a", "exec-1", "job-1", at, jitter)

    def test_schedule_uses_policy_delay(self):
        result = self.schedule()
        self.assertEqual(result["action"], "scheduled")
        self.assertEqual(result["job"]["due_at"], "2026-01-01T00:01:00+00:00")

    def test_jitter_is_added(self):
        result = self.schedule(jitter=5)
        self.assertEqual(result["job"]["due_at"], "2026-01-01T00:01:05+00:00")

    def test_unapproved_policy_blocked(self):
        result = schedule_retry({"action": "manual_review"}, "wf", "stage", "exec", "job", "2026-01-01T00:00:00Z")
        self.assertEqual(result["reason"], "retry_policy_not_approved")

    def test_invalid_time_and_jitter_block(self):
        self.assertEqual(self.schedule(at="not-time")["action"], "blocked")
        self.assertEqual(self.schedule(jitter=-1)["action"], "blocked")

    def test_not_due_remains_queued(self):
        job = self.schedule()["job"]
        result = evaluate_retry_job(job, "2026-01-01T00:00:30Z")
        self.assertEqual(result["action"], "queued")

    def test_due_job_returns_due(self):
        job = self.schedule()["job"]
        result = evaluate_retry_job(job, "2026-01-01T00:01:00Z")
        self.assertEqual(result["action"], "due")
        self.assertEqual(result["attempt_number"], 2)

    def test_cancel_requested(self):
        job = self.schedule()["job"]
        self.assertEqual(evaluate_retry_job(job, "2026-01-01T00:00:00Z", True)["action"], "cancelled")

    def test_cancel_returns_copy(self):
        job = self.schedule()["job"]
        result = cancel_retry_job(job, "2026-01-01T00:00:01Z")
        self.assertEqual(result["action"], "cancelled")
        self.assertEqual(job["status"], "queued")
        self.assertEqual(result["job"]["status"], "cancelled")

    def test_cancel_invalid_or_nonqueued_blocked(self):
        job = self.schedule()["job"]
        self.assertEqual(cancel_retry_job(job, "bad-time")["action"], "blocked")
        job["status"] = "running"
        self.assertEqual(cancel_retry_job(job, "2026-01-01T00:00:01Z")["action"], "blocked")

    def test_naive_time_rejected(self):
        self.assertEqual(self.schedule(at="2026-01-01T00:00:00")["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
