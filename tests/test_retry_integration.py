import unittest

from sentinel_core.execution_receipts import create_execution_receipt
from sentinel_core.retry_integration import prepare_retry


class RetryIntegrationTests(unittest.TestCase):
    def receipt(self, outcome="failed", side_effects="none"):
        return create_execution_receipt("wf-1", "scan", {"allowed": True}, "exec-old", outcome=outcome, details={"side_effects": side_effects})

    def args(self, receipt=None, registry=None, marker=True, key="id-key", now="2026-01-01T00:00:00Z"):
        return {
            "receipt": receipt or self.receipt(),
            "checkpoint_events": [{"stage": "scan", "status": "failed"}],
            "registry": registry or {},
            "idempotency_key": key,
            "execution_payload": {"workflow": "wf-1", "stage": "scan", "input_digest": "abc"},
            "execution_id": "exec-new",
            "job_id": "job-new",
            "scheduled_at": now,
            "attempt_number": 1,
            "retry_marker_present": marker,
        }

    def test_full_pipeline_prepares_retry(self):
        result = prepare_retry(**self.args())
        self.assertEqual(result["action"], "prepared")
        self.assertEqual(result["job"]["status"], "queued")
        self.assertEqual(result["job"]["attempt_number"], 2)

    def test_side_effect_unknown_stops_at_recovery(self):
        result = prepare_retry(**self.args(receipt=self.receipt(side_effects="unknown")))
        self.assertEqual(result["action"], "manual_review")

    def test_missing_retry_marker_blocks(self):
        result = prepare_retry(**self.args(marker=False))
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["policy"]["reason"], "retry_marker_required")

    def test_key_payload_conflict_blocked(self):
        existing = prepare_retry(**self.args())["reservation"]
        registry = {existing["registry_key"]: existing["record"]}
        args = self.args(registry=registry)
        args["execution_payload"] = {"different": True}
        result = prepare_retry(**args)
        self.assertEqual(result["action"], "blocked")

    def test_idempotent_replay_does_not_create_duplicate_job(self):
        first = prepare_retry(**self.args())
        registry = {first["reservation"]["registry_key"]: first["reservation"]["record"]}
        second = prepare_retry(**self.args(registry=registry))
        self.assertEqual(second["action"], "replay")
        self.assertNotIn("job", second)

    def test_invalid_schedule_blocked(self):
        result = prepare_retry(**self.args(now="invalid"))
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["reason"], "scheduling_rejected")


if __name__ == "__main__":
    unittest.main()
