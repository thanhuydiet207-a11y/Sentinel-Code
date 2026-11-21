import unittest
from sentinel_core.remediation_report import build_remediation_report

def bundle():
    return {
        "patch_validation": {"valid": True, "issues": []},
        "patch_risk": {"risk_level": "low", "risk_score": 10},
        "sandbox": {"status": "pass", "commands": [{"status": "pass"}]},
        "scan_comparison": {"status": "clean", "summary": {"fixed_count": 1, "new_count": 0, "persisting_count": 0}},
    }

class RemediationReportTests(unittest.TestCase):
    def test_ready_requires_manual_approval(self):
        result = build_remediation_report(bundle())
        self.assertEqual(result["decision"], "ready_for_manual_approval")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["automatic_apply_allowed"])
        self.assertFalse(result["automatic_merge_allowed"])
    def test_validation_failure_blocks(self):
        b = bundle(); b["patch_validation"]["valid"] = False
        result = build_remediation_report(b)
        self.assertEqual(result["decision"], "blocked_or_manual_review")
        self.assertIn("patch_validation_failed", result["blockers"])
    def test_test_failure_blocks(self):
        b = bundle(); b["sandbox"]["status"] = "fail"
        result = build_remediation_report(b)
        self.assertIn("sandbox_not_passed", result["blockers"])
    def test_regression_blocks(self):
        b = bundle(); b["scan_comparison"]["status"] = "regression"
        result = build_remediation_report(b)
        self.assertIn("security_regression_or_unverified_scan", result["blockers"])
    def test_high_risk_requires_review(self):
        b = bundle(); b["patch_risk"]["risk_level"] = "high"; b["patch_risk"]["risk_score"] = 80
        result = build_remediation_report(b)
        self.assertIn("high_patch_risk_requires_manual_review", result["blockers"])
    def test_invalid_bundle_shape_rejected(self):
        with self.assertRaises(ValueError):
            build_remediation_report([])
    def test_invalid_score_blocks(self):
        b = bundle(); b["patch_risk"]["risk_score"] = "low"
        result = build_remediation_report(b)
        self.assertIn("patch_risk_score_invalid", result["blockers"])

if __name__ == "__main__":
    unittest.main()
