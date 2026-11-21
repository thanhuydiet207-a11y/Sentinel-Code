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


    def ai_evidence(self, **overrides):
        value = {
            "status": "complete", "reviewer_count": 2,
            "finding_count": 3, "adjudicated_finding_count": 3,
            "cross_stage_disagreements": 0, "minimum_confidence": 0.85,
        }
        value.update(overrides)
        return value

    def test_ai_adjudication_passes_when_complete_and_confident(self):
        policy = self.policy(require_ai_adjudication=True, min_adjudicator_reviewers=2,
                             max_cross_stage_disagreements=0, min_adjudicator_confidence=0.8)
        result = evaluate_policy(policy, self.evidence(ai_adjudication=self.ai_evidence()))
        self.assertEqual(result["decision"], "PASS")
        self.assertTrue(result["gates"]["ai_adjudication"])

    def test_required_ai_adjudication_missing_yields_review(self):
        result = evaluate_policy(self.policy(require_ai_adjudication=True), self.evidence())
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("ai_adjudication_not_completed", result["missing_evidence"])

    def test_incomplete_adjudicator_coverage_yields_review(self):
        result = evaluate_policy(
            self.policy(require_ai_adjudication=True),
            self.evidence(ai_adjudication=self.ai_evidence(adjudicated_finding_count=2)),
        )
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("adjudicator_finding_coverage_incomplete", result["missing_evidence"])

    def test_low_adjudicator_confidence_yields_review(self):
        result = evaluate_policy(
            self.policy(require_ai_adjudication=True, min_adjudicator_confidence=0.8),
            self.evidence(ai_adjudication=self.ai_evidence(minimum_confidence=0.4)),
        )
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("adjudicator_confidence_below_policy", result["review_reasons"])

    def test_cross_stage_disagreement_yields_review(self):
        result = evaluate_policy(
            self.policy(require_ai_adjudication=True, max_cross_stage_disagreements=0),
            self.evidence(ai_adjudication=self.ai_evidence(cross_stage_disagreements=1)),
        )
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("cross_stage_disagreement_limit_exceeded", result["review_reasons"])

    def test_too_few_adjudicators_yields_review(self):
        result = evaluate_policy(
            self.policy(require_ai_adjudication=True, min_adjudicator_reviewers=2),
            self.evidence(ai_adjudication=self.ai_evidence(reviewer_count=1)),
        )
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("minimum_adjudicator_reviewers_not_met", result["missing_evidence"])

    def test_invalid_ai_confidence_threshold_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_policy(self.policy(min_adjudicator_confidence=1.1), self.evidence())

    def test_invalid_ai_review_limits_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_policy(self.policy(max_cross_stage_disagreements=-1), self.evidence())

if __name__ == "__main__":
    unittest.main()
