import unittest
from unittest.mock import Mock

from sentinel_core.retry_recovery import RetryPolicyEngine, RetryRecoveryCoordinator


class RetryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.policy = RetryPolicyEngine(max_attempts=4, base_delay_seconds=10,
                                       max_delay_seconds=25, jitter_ratio=0.2)
        self.job = {"schema": 1, "job_id": "job-1", "workflow_id": "wf-1",
                    "stage": "stage-a", "execution_id": "exec-1", "task_id": "task-1"}

    def test_exponential_backoff_and_cap(self):
        first = self.policy.decide(1, "transient", "2026-01-01T00:00:00Z", jitter_sample=0.5)
        third = self.policy.decide(3, "transient", "2026-01-01T00:00:00Z", jitter_sample=0.5)
        self.assertEqual(first["delay_seconds"], 10)
        self.assertEqual(third["delay_seconds"], 25)

    def test_jitter_is_bounded_and_deterministic(self):
        low = self.policy.decide(1, "transient", "2026-01-01T00:00:00Z", jitter_sample=0)
        high = self.policy.decide(1, "transient", "2026-01-01T00:00:00Z", jitter_sample=1)
        self.assertEqual(low["delay_seconds"], 8)
        self.assertEqual(high["delay_seconds"], 12)

    def test_retry_after_is_minimum_delay(self):
        result = self.policy.decide(1, "transient", "2026-01-01T00:00:00Z", retry_after_seconds=40)
        self.assertEqual(result["delay_seconds"], 40)

    def test_permanent_failure_stops(self):
        self.assertEqual(self.policy.decide(1, "permanent", "2026-01-01T00:00:00Z")["action"], "stop")

    def test_attempt_limit_stops(self):
        result = self.policy.decide(4, "transient", "2026-01-01T00:00:00Z")
        self.assertEqual(result["reason"], "attempt_limit_reached")

    def test_job_preserves_execution_identity_and_parent(self):
        decision = self.policy.decide(1, "transient", "2026-01-01T00:00:00Z")
        planned = self.policy.build_retry_job(self.job, decision, "retry-1")
        self.assertEqual(planned["job"]["execution_id"], "exec-1")
        self.assertEqual(planned["job"]["parent_job_id"], "job-1")
        self.assertEqual(planned["job"]["attempt_number"], 2)

    def test_coordinator_persists_retry(self):
        store = Mock()
        store.enqueue.return_value = {"action": "stored", "job_id": "retry-1"}
        coordinator = RetryRecoveryCoordinator(self.policy, store)
        result = coordinator.recover(self.job, 1, "transient", "2026-01-01T00:00:00Z", "retry-1")
        self.assertEqual(result["action"], "scheduled")
        store.enqueue.assert_called_once()

    def test_store_failure_is_fail_closed(self):
        store = Mock()
        store.enqueue.return_value = {"action": "blocked", "reason": "job_id_duplicate"}
        coordinator = RetryRecoveryCoordinator(self.policy, store)
        result = coordinator.recover(self.job, 1, "transient", "2026-01-01T00:00:00Z", "retry-1")
        self.assertEqual(result["reason"], "retry_persist_failed")

    def test_invalid_inputs_block(self):
        self.assertEqual(self.policy.decide(0, "transient", "bad")["action"], "blocked")
        self.assertEqual(self.policy.decide(1, "transient", "2026-01-01T00:00:00Z", jitter_sample=2)["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
