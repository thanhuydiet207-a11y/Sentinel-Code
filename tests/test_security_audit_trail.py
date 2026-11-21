import unittest
from sentinel_core.audit_trail import build_audit_trail, verify_audit_trail, lifecycle_status


class AuditTrailTests(unittest.TestCase):
    def sample(self):
        return [
            {"type": "created", "timestamp": "2026-01-01T00:00:00Z", "payload": {"commit": "abc"}},
            {"type": "patch_proposed", "timestamp": "2026-01-01T00:01:00Z", "payload": {"patch_sha256": "a" * 64}},
        ]

    def test_chain_valid(self):
        trail = build_audit_trail("session-1", self.sample())
        self.assertTrue(verify_audit_trail(trail)["valid"])

    def test_payload_tamper_detected(self):
        trail = build_audit_trail("session-1", self.sample())
        trail["events"][0]["payload"]["commit"] = "changed"
        self.assertFalse(verify_audit_trail(trail)["valid"])

    def test_reorder_detected(self):
        trail = build_audit_trail("session-1", self.sample())
        trail["events"].reverse()
        self.assertFalse(verify_audit_trail(trail)["valid"])

    def test_requires_created_event_for_complete_lifecycle(self):
        self.assertEqual(lifecycle_status(self.sample())["status"], "complete")
        self.assertEqual(lifecycle_status([])["status"], "incomplete")

    def test_approval_requires_verification_and_report(self):
        result = lifecycle_status([{"type": "created"}, {"type": "approved"}])
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("approval_requested_before_approved", result["missing_requirements"])

    def test_invalid_event_type_rejected(self):
        with self.assertRaises(ValueError):
            build_audit_trail("s", [{"type": "unknown", "timestamp": "x"}])

    def test_requires_timezone_aware_timestamp(self):
        with self.assertRaises(ValueError):
            build_audit_trail("s", [{"type": "created", "timestamp": "2026-01-01T00:00:00"}])

    def test_rejects_out_of_order_timestamps(self):
        with self.assertRaises(ValueError):
            build_audit_trail("s", [
                {"type": "created", "timestamp": "2026-01-01T00:01:00Z"},
                {"type": "patch_proposed", "timestamp": "2026-01-01T00:00:00Z"},
            ])

    def test_approval_requires_ordered_prerequisites(self):
        events = [
            {"type": "created"}, {"type": "approved"}, {"type": "approval_requested"},
            {"type": "evidence_verified"}, {"type": "report_generated"},
        ]
        result = lifecycle_status(events)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("approval_requested_before_approved", result["missing_requirements"])

    def test_closed_event_must_be_final_and_unique(self):
        events = [
            {"type": "created"}, {"type": "approval_requested"}, {"type": "rejected"},
            {"type": "closed"}, {"type": "review_completed"},
        ]
        result = lifecycle_status(events)
        self.assertIn("closed_must_be_final_and_unique", result["missing_requirements"])

    def test_verifier_reports_lifecycle_failure(self):
        trail = build_audit_trail("s", [
            {"type": "created", "timestamp": "2026-01-01T00:00:00Z"},
            {"type": "approved", "timestamp": "2026-01-01T00:01:00Z"},
        ])
        result = verify_audit_trail(trail)
        self.assertFalse(result["valid"])
        self.assertIn("lifecycle_approval_requested_before_approved", result["errors"])

    def test_duplicate_approval_request_invalid(self):
        events = [
            {"type": "created"}, {"type": "approval_requested"},
            {"type": "approval_requested"}, {"type": "rejected"},
        ]
        result = lifecycle_status(events)
        self.assertIn("approval_requested_must_be_appear_at_most_once", result["missing_requirements"])

    def test_duplicate_decisions_invalid(self):
        events = [
            {"type": "created"}, {"type": "approval_requested"},
            {"type": "rejected"}, {"type": "rejected"},
        ]
        result = lifecycle_status(events)
        self.assertIn("rejected_must_appear_at_most_once", result["missing_requirements"])

    def test_close_must_follow_decision(self):
        events = [
            {"type": "created"}, {"type": "approval_requested"},
            {"type": "closed"}, {"type": "rejected"},
        ]
        result = lifecycle_status(events)
        self.assertIn("closed_must_be_final_and_unique", result["missing_requirements"])
        self.assertIn("decision_before_close", result["missing_requirements"])

    def test_valid_rejection_lifecycle(self):
        events = [
            {"type": "created"}, {"type": "approval_requested"},
            {"type": "rejected"}, {"type": "closed"},
        ]
        self.assertEqual(lifecycle_status(events)["status"], "complete")

    def test_valid_approval_lifecycle(self):
        events = [
            {"type": "created"}, {"type": "report_generated"},
            {"type": "evidence_verified"}, {"type": "approval_requested"},
            {"type": "approved"}, {"type": "closed"},
        ]
        self.assertEqual(lifecycle_status(events)["status"], "complete")


if __name__ == "__main__":
    unittest.main()
