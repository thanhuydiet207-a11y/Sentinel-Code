import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentinel_core.core import line_hash_from_text
from sentinel_core.security_pipeline import run_security_pipeline


class SecurityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        source = "value = input()\nquery = value\n"
        (self.root / "app.py").write_text(source, encoding="utf-8")
        self.findings = {
            "schema_version": "1.0",
            "metadata": {"origin": "test"},
            "findings": [{
                "id": "F-1",
                "title": "Untrusted input reaches query construction",
                "rule_id": "CWE-89/SQL-INJECTION",
                "category": "CWE-89",
                "severity": "high",
                "confidence": 0.9,
                "location": {"path": "app.py", "start_line": 1, "end_line": 1},
                "evidence": {
                    "reason": "The user-controlled value is read from input.",
                    "line_hash": line_hash_from_text(source, 1, 1),
                },
                "impact": "An attacker may influence query construction.",
                "remediation": "Use parameterized queries.",
            }],
        }
        self.review_package = {"reviewers": [{
            "reviewer_id": "independent:openai",
            "provider": "openai",
            "reviews": [{
                "finding_id": "F-1",
                "verdict": "likely",
                "confidence": 0.8,
                "rationale": "Source line shows input is captured.",
                "evidence_refs": ["app.py:1"],
            }],
        }]}
        self.adversarial = {
            "metadata": {"total_provider_requests": 3},
            "stages": {
                "independent": self.review_package,
                "challenger": self.review_package,
                "adjudicator": self.review_package,
            },
            "cross_stage_analysis": [{
                "finding_id": "F-1",
                "cross_stage_disagreement": False,
            }],
        }

    def tearDown(self):
        self.tmp.cleanup()

    @patch("sentinel_core.security_pipeline.run_adversarial_reviews")
    def test_pipeline_runs_full_chain_and_returns_report(self, mocked):
        mocked.return_value = self.adversarial
        result = run_security_pipeline(self.findings, self.root, ["openai"])
        mocked.assert_called_once()
        self.assertEqual(result["summary"]["unique_findings"], 1)
        self.assertEqual(result["summary"]["adversarial_provider_requests"], 3)
        self.assertEqual(result["summary"]["verified_source_hash_references"], 3)
        self.assertIn("# Sentinel-Code Security Review", result["markdown_report"])
        self.assertFalse(result["summary"]["automatic_suppression"])

    @patch("sentinel_core.security_pipeline.run_adversarial_reviews")
    def test_invalid_source_evidence_stops_before_ai_calls(self, mocked):
        invalid = {
            **self.findings,
            "findings": [{**self.findings["findings"][0],
                          "evidence": {"reason": "wrong hash", "line_hash": "0" * 64}}],
        }
        with self.assertRaisesRegex(ValueError, "failed validation"):
            run_security_pipeline(invalid, self.root, ["openai"])
        mocked.assert_not_called()

    @patch("sentinel_core.security_pipeline.run_adversarial_reviews")
    @patch("sentinel_core.security_pipeline.import_scanner_results")
    def test_scanner_json_is_imported_and_combined(self, mocked_import, mocked_review):
        second = {
            "schema_version": "1.0",
            "metadata": {"scanner": "semgrep", "imported": 1, "skipped": []},
            "findings": [{
                "id": "S-2",
                "title": "Second issue",
                "rule_id": "semgrep/custom-rule",
                "category": "custom:scanner",
                "severity": "medium",
                "confidence": 0.85,
                "location": {"path": "app.py", "start_line": 2, "end_line": 2},
                "evidence": {"reason": "Scanner evidence", "line_hash": line_hash_from_text("value = input()\nquery = value\n", 2, 2)},
                "impact": "Potentially unsafe query.",
                "remediation": "Review the query construction.",
                "scanner": "semgrep",
            }],
        }
        mocked_import.return_value = second
        # Build one review response per finding for each stage.
        def review_result(payload, providers, **kwargs):
            return {
                "metadata": {"total_provider_requests": 3},
                "stages": {
                    name: {"reviewers": [{
                        "reviewer_id": name + ":openai",
                        "provider": "openai",
                        "reviews": [{
                            "finding_id": item["id"], "verdict": "uncertain",
                            "confidence": 0.5, "rationale": "Needs human validation",
                            "evidence_refs": [item["location"]["path"] + ":" + str(item["location"]["start_line"])],
                        } for item in payload["findings"]],
                    }]}
                    for name in ("independent", "challenger", "adjudicator")
                },
                "cross_stage_analysis": [{"finding_id": item["id"], "cross_stage_disagreement": False}
                                         for item in payload["findings"]],
            }
        mocked_review.side_effect = review_result
        result = run_security_pipeline(
            self.findings, self.root, ["openai"],
            scanner_inputs=[{"scanner": "semgrep", "data": {"results": []}}],
        )
        mocked_import.assert_called_once()
        self.assertEqual(result["summary"]["scanner_findings_imported"], 1)
        self.assertEqual(result["summary"]["unique_findings"], 2)

    def test_bad_scanner_name_rejected(self):
        with self.assertRaisesRegex(ValueError, "scanner must be one of"):
            run_security_pipeline(self.findings, self.root, ["openai"],
                                  scanner_inputs=[{"scanner": "unknown", "data": {}}])


if __name__ == "__main__":
    unittest.main()
