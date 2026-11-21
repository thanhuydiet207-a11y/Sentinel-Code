import unittest

from sentinel_core.correlation import correlate_findings


def finding(fid, scanner, confidence, severity="high", path="src/app.py", digest="a" * 64):
    return {
        "id": fid, "scanner": scanner, "rule_id": f"{scanner}/rule",
        "severity": severity, "confidence": confidence, "title": "Issue",
        "location": {"path": path, "start_line": 5, "end_line": 5},
        "evidence": {"line_hash": digest},
    }


class CorrelationTests(unittest.TestCase):
    def test_correlates_independent_scanners_on_same_evidence(self):
        result = correlate_findings([
            {"findings": [finding("S1", "semgrep", .85)]},
            {"findings": [finding("G1", "gitleaks", .9)]},
        ])
        group = result["correlations"][0]
        self.assertTrue(group["corroborated"])
        self.assertEqual(group["scanner_count"], 2)
        self.assertAlmostEqual(group["combined_confidence"], .985)
        self.assertEqual(result["metadata"]["corroborated_groups"], 1)

    def test_different_evidence_does_not_merge(self):
        result = correlate_findings([
            {"findings": [finding("A", "semgrep", .8)]},
            {"findings": [finding("B", "trivy", .7, digest="b" * 64)]},
        ])
        self.assertEqual(len(result["correlations"]), 2)
        self.assertFalse(any(x["corroborated"] for x in result["correlations"]))

    def test_scanner_absence_not_negative_evidence(self):
        result = correlate_findings([{"findings": [finding("A", "semgrep", .8)]}])
        self.assertIn("absence is not evidence of safety", result["correlations"][0]["notes"])


if __name__ == "__main__":
    unittest.main()
