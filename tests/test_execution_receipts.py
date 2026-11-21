import copy
import unittest

from sentinel_core.execution_receipts import (
    create_execution_receipt, verify_execution_receipt, reconcile_execution_receipts,
)


class ExecutionReceiptTests(unittest.TestCase):
    def test_receipt_hash_and_key_privacy(self):
        receipt = create_execution_receipt("wf-1", "review", {"allowed": True, "reason": "ready"}, "exec-1", "secret-key")
        self.assertTrue(verify_execution_receipt(receipt)["valid"])
        self.assertNotIn("secret-key", str(receipt))
        self.assertEqual(len(receipt["idempotency_key_digest"]), 64)

    def test_denied_decision_cannot_create_receipt(self):
        with self.assertRaisesRegex(ValueError, "execution_not_approved"):
            create_execution_receipt("wf-1", "review", {"allowed": False}, "exec-1")

    def test_tampering_detected_and_started_is_abandoned_candidate(self):
        receipt = create_execution_receipt("wf-1", "review", {"allowed": True}, "exec-1")
        self.assertTrue(verify_execution_receipt(receipt)["abandoned"])
        changed = copy.deepcopy(receipt)
        changed["outcome"] = "completed"
        self.assertIn("receipt_digest_mismatch", verify_execution_receipt(changed)["errors"])

    def test_reconciliation_reports_match_and_missing(self):
        completed = create_execution_receipt("wf-1", "review", {"allowed": True}, "exec-1", outcome="completed")
        failed = create_execution_receipt("wf-1", "scan", {"allowed": True}, "exec-2", outcome="failed")
        result = reconcile_execution_receipts([completed, failed], [
            {"stage": "review", "status": "completed"},
            {"stage": "scan", "status": "failed"},
            {"stage": "build", "status": "completed"},
        ])
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["matches"]), 2)
        self.assertEqual(result["unmatched_checkpoints"], [{"stage": "build", "status": "completed"}])

    def test_invalid_receipt_is_not_reconciled(self):
        receipt = create_execution_receipt("wf-1", "review", {"allowed": True}, "exec-1")
        receipt["details"]["unsafe"] = True
        result = reconcile_execution_receipts([receipt], [{"stage": "review", "status": "completed"}])
        self.assertFalse(result["valid"])
        self.assertEqual(result["unmatched_receipts"][0]["reason"], "receipt_invalid")


if __name__ == "__main__":
    unittest.main()
