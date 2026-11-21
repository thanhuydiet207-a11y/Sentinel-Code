import unittest

from sentinel_core.retry_health import assess_retry_health


class RetryHealthTests(unittest.TestCase):
    def snapshot(self, due=0, expired=0, active=0):
        return {"action": "snapshot", "queue": {"queued": due}, "due_queued": due, "leases": {"active": active, "expired": expired}}

    def test_healthy(self):
        self.assertEqual(assess_retry_health(self.snapshot())["status"], "healthy")

    def test_backlog_warning(self):
        result = assess_retry_health(self.snapshot(due=11), {"max_due_queued": 10})
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["findings"][0]["code"], "due_queue_backlog")

    def test_expired_lease_critical(self):
        result = assess_retry_health(self.snapshot(expired=1))
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["findings"][0]["severity"], "critical")

    def test_combined_findings(self):
        result = assess_retry_health(self.snapshot(due=5, expired=2, active=20), {"max_due_queued": 3, "max_active_leases": 10})
        self.assertEqual(result["status"], "critical")
        self.assertEqual(len(result["findings"]), 3)

    def test_invalid_snapshot_and_thresholds(self):
        self.assertEqual(assess_retry_health({})["action"], "blocked")
        self.assertEqual(assess_retry_health(self.snapshot(), {"max_due_queued": -1})["action"], "blocked")


if __name__ == "__main__":
    unittest.main()
