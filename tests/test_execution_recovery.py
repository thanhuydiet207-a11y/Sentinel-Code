import copy
import unittest

from sentinel_core.execution_receipts import create_execution_receipt
from sentinel_core.execution_recovery import classify_execution_recovery, reconcile_recovery_state


class ExecutionRecoveryTests(unittest.TestCase):
    def receipt(self, outcome, side_effects, stage="stage-a"):
        return create_execution_receipt("wf-1", stage, {"allowed": True}, "exec-1", outcome=outcome, details={"side_effects": side_effects})

    def test_failed_without_side_effects_is_retry_candidate(self):
        result = classify_execution_recovery(self.receipt("failed", "none"), [{"stage": "stage-a", "status": "failed"}])
        self.assertEqual(result["action"], "safe_to_retry")

    def test_confirmed_side_effects_require_manual_review(self):
        result = classify_execution_recovery(self.receipt("failed", "confirmed"), [{"stage": "stage-a", "status": "failed"}])
        self.assertEqual(result["action"], "manual_review")

    def test_unknown_side_effect_state_fails_closed(self):
        result = classify_execution_recovery(self.receipt("started", "unknown"), [{"stage": "stage-a", "status": "failed"}])
        self.assertEqual(result["action"], "manual_review")
        self.assertEqual(result["reason"], "side_effect_status_unknown")

    def test_missing_checkpoint_requires_review(self):
        result = classify_execution_recovery(self.receipt("abandoned", "none"), [])
        self.assertEqual(result["action"], "manual_review")
        self.assertEqual(result["reason"], "checkpoint_missing")

    def test_completed_receipt_requires_matching_checkpoint(self):
        result = classify_execution_recovery(self.receipt("completed", "none"), [{"stage": "stage-a", "status": "completed"}])
        self.assertEqual(result["action"], "completed")

    def test_checkpoint_mismatch_blocks(self):
        result = classify_execution_recovery(self.receipt("completed", "none"), [{"stage": "stage-a", "status": "failed"}])
        self.assertEqual(result["action"], "blocked")

    def test_tampered_receipt_blocks(self):
        receipt = self.receipt("failed", "none")
        receipt["details"]["side_effects"] = "none"
        result = classify_execution_recovery(receipt, [{"stage": "stage-a", "status": "failed"}])
        self.assertEqual(result["action"], "blocked")

    def test_reconcile_returns_decision_per_receipt(self):
        receipts = [self.receipt("failed", "none"), self.receipt("completed", "none", "stage-b")]
        events = [{"stage": "stage-a", "status": "failed"}, {"stage": "stage-b", "status": "completed"}]
        result = reconcile_recovery_state(receipts, events)
        self.assertTrue(result["valid"])
        self.assertEqual([d["action"] for d in result["decisions"]], ["safe_to_retry", "completed"])


if __name__ == "__main__":
    unittest.main()
