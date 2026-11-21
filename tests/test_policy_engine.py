import unittest
from sentinel_core.policy_engine import evaluate_policy

class PolicyEngineTests(unittest.TestCase):
    def policy(self, **overrides):
        value = {"policy_id": "strict", "version": 1, "max_risk_score": 25,
                 "required_scanners": ["semgrep", "gitleaks"], "required_reviewers": ["openai"],
                 "min_reviewers": 1, "require_evidence_verified": True}
        value.update(overrides)
        return value

    def evidence(self, **overrides):
        value = {"patch_validation": {"valid": True}, "sandbox": {"status": "pass"},
                 "scan_comparison": {"status": "clean"}, "patch_risk": {"risk_score": 10},
                 "scanners": ["semgrep", "gitleaks"], "evidence_verified": True,
                 "reviewers": ["openai"]}
        value.update(overrides)
        return value

    def test_pass_when_all_gates_satisfied(self):
        result = evaluate_policy(self.policy(), self.evidence())
        self.assertEqual(result["decision"], "PASS")
        self.assertFalse(result["automatic_merge_allowed"])

    def test_block_high_risk(self):
        result = evaluate_policy(self.policy(), self.evidence(patch_risk={"risk_score": 80}))
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("patch_risk_exceeds_policy", result["blockers"])

    def test_review_missing_evidence(self):
        result = evaluate_policy(self.policy(), self.evidence(evidence_verified=False))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("evidence_not_verified", result["missing_evidence"])

    def test_block_failed_sandbox(self):
        result = evaluate_policy(self.policy(), self.evidence(sandbox={"status": "fail"}))
        self.assertEqual(result["decision"], "BLOCK")

    def test_review_missing_scanner(self):
        result = evaluate_policy(self.policy(), self.evidence(scanners=["semgrep"]))
        self.assertEqual(result["decision"], "REVIEW")

    def test_reject_unknown_policy_key(self):
        with self.assertRaises(ValueError):
            evaluate_policy(self.policy(unexpected=True), self.evidence())

    def test_invalid_risk_threshold(self):
        with self.assertRaises(ValueError):
            evaluate_policy(self.policy(max_risk_score=101), self.evidence())

    def test_review_missing_reviewer(self):
        result = evaluate_policy(self.policy(), self.evidence(reviewers=[]))
        self.assertEqual(result["decision"], "REVIEW")

if __name__ == "__main__":
    unittest.main()
