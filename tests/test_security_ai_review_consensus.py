import unittest

from sentinel_core.ai_review import ReviewValidationError, aggregate_reviews


def package():
    findings = {"schema_version": "1.0", "findings": [
        {"id": "F-1", "title": "SQL injection", "severity": "high", "location": {"path": "app.py", "start_line": 4, "end_line": 4}},
        {"id": "F-2", "title": "Weak issue", "severity": "low", "location": {"path": "x.py", "start_line": 1, "end_line": 1}},
    ]}
    reviews = {"reviewers": [
        {"reviewer_id": "r1", "provider": "provider-a", "model": "model-x", "reviews": [
            {"finding_id": "F-1", "verdict": "confirmed", "confidence": .9, "rationale": "Source reaches sink"},
            {"finding_id": "F-2", "verdict": "dismissed", "confidence": .8},
        ]},
        {"reviewer_id": "r2", "provider": "provider-b", "reviews": [
            {"finding_id": "F-1", "verdict": "likely", "confidence": .7},
            {"finding_id": "F-2", "verdict": "uncertain", "confidence": .4},
        ]},
    ]}
    return findings, reviews


class AIReviewConsensusTests(unittest.TestCase):
    def test_positive_review_corroboration_and_disagreement(self):
        findings, reviews = package()
        result = aggregate_reviews(findings, reviews)
        first, second = result["consensus"]
        self.assertTrue(first["positive_corroborated"])
        self.assertTrue(first["disagreement"])
        self.assertEqual(first["agreement_ratio"], .5)
        self.assertTrue(second["disagreement"])
        self.assertEqual(second["recommendation"], "manual_review")

    def test_unanimous_dismissal_does_not_suppress(self):
        findings, reviews = package()
        reviews["reviewers"][1]["reviews"][1]["verdict"] = "dismissed"
        result = aggregate_reviews(findings, reviews)
        item = result["consensus"][1]
        self.assertEqual(item["dominant_verdict"], "dismissed")
        self.assertFalse(item["automatic_suppression"])
        self.assertEqual(item["recommendation"], "manual_review")

    def test_unknown_finding_reference_rejected(self):
        findings, reviews = package()
        reviews["reviewers"][0]["reviews"][0]["finding_id"] = "MISSING"
        with self.assertRaises(ReviewValidationError):
            aggregate_reviews(findings, reviews)

    def test_duplicate_reviewer_rejected(self):
        findings, reviews = package()
        reviews["reviewers"].append(dict(reviews["reviewers"][0]))
        with self.assertRaises(ReviewValidationError):
            aggregate_reviews(findings, reviews)

    def test_invalid_confidence_rejected(self):
        findings, reviews = package()
        reviews["reviewers"][0]["reviews"][0]["confidence"] = float("nan")
        with self.assertRaises(ReviewValidationError):
            aggregate_reviews(findings, reviews)

    def test_empty_reviewers_still_returns_manual_review(self):
        findings, _ = package()
        result = aggregate_reviews(findings, {"reviewers": []})
        self.assertEqual(result["metadata"]["reviewer_count"], 0)
        self.assertTrue(all(item["recommendation"] == "manual_review" for item in result["consensus"]))


if __name__ == "__main__":
    unittest.main()
