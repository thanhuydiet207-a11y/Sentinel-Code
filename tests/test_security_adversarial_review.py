import unittest
from unittest.mock import call, patch

from sentinel_core.adversarial_review import run_adversarial_reviews

FINDINGS = {"findings": [
    {"id": "F-1", "title": "Possible injection", "severity": "high",
     "location": {"path": "app.py", "start_line": 7}}
]}


def package(role, verdict, provider="openai"):
    return {"reviewers": [{
        "reviewer_id": role + ":" + provider,
        "provider": provider,
        "model": "mock-model",
        "reviews": [{
            "finding_id": "F-1",
            "verdict": verdict,
            "confidence": 0.8,
            "rationale": role + " rationale",
            "evidence_refs": ["app.py:7"],
        }],
    }]}


class AdversarialReviewTests(unittest.TestCase):
    @patch("sentinel_core.adversarial_review.run_provider_reviews")
    def test_runs_three_roles_and_surfaces_disagreement(self, mocked):
        mocked.side_effect = [
            package("independent", "likely"),
            package("challenger", "dismissed"),
            package("adjudicator", "uncertain"),
        ]
        result = run_adversarial_reviews(FINDINGS, ["openai"])
        self.assertEqual([x.kwargs["review_role"] for x in mocked.call_args_list],
                         ["independent", "challenger", "adjudicator"])
        self.assertEqual(mocked.call_args_list[1].kwargs["prior_reviews"]["independent"]["reviewers"][0]["reviewer_id"],
                         "independent:openai")
        comparison = result["cross_stage_analysis"][0]
        self.assertTrue(comparison["cross_stage_disagreement"])
        self.assertEqual(comparison["adjudicator_verdicts"], ["uncertain"])
        self.assertFalse(comparison["automatic_suppression"])
        self.assertEqual(comparison["recommendation"], "manual_review")

    @patch("sentinel_core.adversarial_review.run_provider_reviews")
    def test_agreement_still_does_not_suppress(self, mocked):
        mocked.side_effect = [
            package("independent", "confirmed"),
            package("challenger", "confirmed"),
            package("adjudicator", "confirmed"),
        ]
        result = run_adversarial_reviews(FINDINGS, ["openai"])
        comparison = result["cross_stage_analysis"][0]
        self.assertFalse(comparison["cross_stage_disagreement"])
        self.assertFalse(comparison["automatic_suppression"])
        self.assertEqual(comparison["recommendation"], "human_security_decision_required")
        self.assertEqual(result["metadata"]["total_provider_requests"], 3)

    @patch("sentinel_core.adversarial_review.run_provider_reviews")
    def test_multiple_providers_and_three_stage_cost_are_reported(self, mocked):
        mocked.side_effect = [
            {"reviewers": [
                package(role, "likely", "openai")["reviewers"][0],
                package(role, "likely", "anthropic")["reviewers"][0],
            ]}
            for role in ("independent", "challenger", "adjudicator")
        ]
        result = run_adversarial_reviews(FINDINGS, ["openai", "anthropic"])
        self.assertEqual(result["metadata"]["total_provider_requests"], 6)
        self.assertEqual(result["metadata"]["providers"], ["openai", "anthropic"])

    def test_empty_and_duplicate_provider_lists_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least one provider"):
            run_adversarial_reviews(FINDINGS, [])
        with self.assertRaisesRegex(ValueError, "duplicates"):
            run_adversarial_reviews(FINDINGS, ["openai", "openai"])


if __name__ == "__main__":
    unittest.main()
