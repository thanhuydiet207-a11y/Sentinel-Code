import unittest
from sentinel_core.audit_trail import build_audit_trail, verify_audit_trail, lifecycle_status

class AuditTrailTests(unittest.TestCase):
    def sample(self):
        return [{"type":"created","timestamp":"2026-01-01T00:00:00Z","payload":{"commit":"abc"}},
                {"type":"patch_proposed","timestamp":"2026-01-01T00:01:00Z","payload":{"patch_sha256":"a"*64}}]
    def test_chain_valid(self):
        trail=build_audit_trail("session-1",self.sample())
        self.assertTrue(verify_audit_trail(trail)["valid"])
    def test_payload_tamper_detected(self):
        trail=build_audit_trail("session-1",self.sample())
        trail["events"][0]["payload"]["commit"]="changed"
        self.assertFalse(verify_audit_trail(trail)["valid"])
    def test_reorder_detected(self):
        trail=build_audit_trail("session-1",self.sample())
        trail["events"].reverse()
        self.assertFalse(verify_audit_trail(trail)["valid"])
    def test_requires_created_event_for_complete_lifecycle(self):
        self.assertEqual(lifecycle_status(self.sample())["status"],"complete")
        self.assertEqual(lifecycle_status([])["status"],"incomplete")
    def test_approval_requires_verification_and_report(self):
        events=[{"type":"created"},{"type":"approved"}]
        result=lifecycle_status(events)
        self.assertEqual(result["status"],"incomplete")
        self.assertIn("approval_requested_before_approved",result["missing_requirements"])
    def test_invalid_event_type_rejected(self):
        with self.assertRaises(ValueError):
            build_audit_trail("s", [{"type":"unknown","timestamp":"x"}])

if __name__ == "__main__":
    unittest.main()
