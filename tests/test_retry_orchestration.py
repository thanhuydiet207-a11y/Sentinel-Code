import unittest

from sentinel_core.retry_orchestration import retry_policy_decision


class RetryOrchestrationTests(unittest.TestCase):
    def test_first_retry_has_base_delay(self):
        result = retry_policy_decision({"action": "safe_to_retry"}, 1, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["action"], "retry_scheduled")
        self.assertEqual(result["delay_seconds"], 30)
        self.assertEqual(result["next_attempt_number"], 2)

    def test_backoff_is_exponential_and_capped(self):
        result = retry_policy_decision({"action": "safe_to_retry"}, 4, max_attempts=6, base_delay_seconds=20, max_delay_seconds=90, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["delay_seconds"], 90)

    def test_retry_marker_required(self):
        result = retry_policy_decision({"action": "safe_to_retry"}, 1, idempotency_key_present=True)
        self.assertEqual(result["reason"], "retry_marker_required")

    def test_idempotency_key_required(self):
        result = retry_policy_decision({"action": "safe_to_retry"}, 1, retry_marker_present=True)
        self.assertEqual(result["reason"], "idempotency_key_required")

    def test_attempt_limit_routes_to_review(self):
        result = retry_policy_decision({"action": "safe_to_retry"}, 3, max_attempts=3, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["action"], "manual_review")
        self.assertEqual(result["reason"], "retry_limit_reached")

    def test_manual_review_recovery_never_retries(self):
        result = retry_policy_decision({"action": "manual_review"}, 1, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["action"], "manual_review")

    def test_blocked_recovery_never_retries(self):
        result = retry_policy_decision({"action": "blocked"}, 1, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["action"], "blocked")

    def test_completed_is_not_retried(self):
        result = retry_policy_decision({"action": "completed"}, 1, retry_marker_present=True, idempotency_key_present=True)
        self.assertEqual(result["action"], "completed")

    def test_invalid_policy_parameters_fail_closed(self):
        self.assertEqual(retry_policy_decision({"action": "safe_to_retry"}, 0)["action"], "blocked")
        self.assertEqual(retry_policy_decision({"action": "safe_to_retry"}, 1, max_attempts=0)["action"], "blocked")
        self.assertEqual(retry_policy_decision({"action": "safe_to_retry"}, 1, base_delay_seconds=100, max_delay_seconds=10)["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
