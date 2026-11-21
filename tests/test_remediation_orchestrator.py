import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sentinel_core.policy_engine import evaluate_policy
from sentinel_core.remediation_orchestrator import run_remediation_orchestration


class PolicyEngineHardeningTests(unittest.TestCase):
    def policy(self, **overrides):
        value = {
            "policy_id": "strict", "version": 1, "max_risk_score": 25,
            "required_scanners": ["semgrep"], "required_reviewers": ["openai"],
            "min_reviewers": 1, "require_evidence_verified": True,
            "require_sandbox_pass": True, "require_regression_clean": True,
            "require_manual_approval": True,
        }
        value.update(overrides)
        return value

    def evidence(self, **overrides):
        value = {
            "patch_validation": {"valid": True}, "patch_risk": {"risk_score": 10},
            "sandbox": {"status": "pass"}, "scan_comparison": {"status": "clean"},
            "evidence_verified": True, "scanners": ["semgrep"], "reviewers": ["openai"],
        }
        value.update(overrides)
        return value

    def test_missing_sandbox_is_review_not_block(self):
        result = evaluate_policy(self.policy(), self.evidence(sandbox={"status": "not_run"}))
        self.assertEqual(result["decision"], "REVIEW")
        self.assertIn("sandbox_not_run", result["missing_evidence"])

    def test_failed_sandbox_is_block(self):
        result = evaluate_policy(self.policy(), self.evidence(sandbox={"status": "fail"}))
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("sandbox_failed", result["blockers"])

    def test_missing_regression_scan_is_review(self):
        result = evaluate_policy(self.policy(), self.evidence(scan_comparison={"status": "not_run"}))
        self.assertEqual(result["decision"], "REVIEW")

    def test_regression_is_block(self):
        result = evaluate_policy(self.policy(), self.evidence(scan_comparison={"status": "regression"}))
        self.assertEqual(result["decision"], "BLOCK")

    def test_invalid_provenance_is_block(self):
        result = evaluate_policy(self.policy(), self.evidence(
            evidence_verified=False, evidence_verification={"status": "invalid"}))
        self.assertEqual(result["decision"], "BLOCK")
        self.assertIn("evidence_integrity_failed", result["blockers"])

    def test_manual_approval_cannot_be_disabled(self):
        with self.assertRaises(ValueError):
            evaluate_policy(self.policy(require_manual_approval=False), self.evidence())

    def test_malformed_evidence_name_lists_do_not_crash(self):
        result = evaluate_policy(self.policy(), self.evidence(scanners=[{"bad": "value"}], reviewers=[[]]))
        self.assertEqual(result["decision"], "REVIEW")

    def test_pass_still_requires_human_approval(self):
        result = evaluate_policy(self.policy(), self.evidence())
        self.assertEqual(result["decision"], "PASS")
        self.assertTrue(result["human_approval_required"])
        self.assertFalse(result["automatic_apply_allowed"])
        self.assertFalse(result["automatic_merge_allowed"])


class RemediationOrchestratorTests(unittest.TestCase):
    def _fixture(self, root: Path):
        source = root / "sample.py"
        original = "value = 1\n"
        source.write_text(original, encoding="utf-8")
        proposal = {
            "finding_id": "F-1", "path": "sample.py",
            "base_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "patch": "--- a/sample.py\n+++ b/sample.py\n@@ -1 +1 @@\n-value = 1\n+value = 2\n",
        }
        findings = {"findings": [{"id": "F-1", "location": {"path": "sample.py"}}]}
        return source, original, findings, proposal

    @patch("sentinel_core.remediation_orchestrator.run_remediation_sandbox")
    def test_orchestrates_candidate_without_modifying_repository(self, sandbox_runner):
        sandbox_runner.return_value = {
            "status": "pass", "commands": [{"status": "pass"}],
            "original_repository_modified": False, "os_level_isolation": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, original, findings, proposal = self._fixture(root)
            policy = {
                "policy_id": "test", "max_risk_score": 100,
                "require_evidence_verified": False,
                "required_scanners": [], "required_reviewers": [],
            }
            result = run_remediation_orchestration(
                findings, proposal, root, baseline_scan={"findings": []},
                candidate_scan={"findings": []}, sandbox_commands=[["python", "--version"]],
                policy=policy,
            )
            self.assertEqual(result["status"], "ready_for_human_approval")
            self.assertEqual(result["policy"]["decision"], "PASS")
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertFalse(result["summary"]["repository_modified"])
            self.assertTrue(result["audit_verification"]["valid"])
            self.assertEqual(result["stages"]["audit_trail"]["status"], "verified")
            self.assertEqual(result["remediation_report"]["decision"], "ready_for_human_approval")
            sandbox_runner.assert_called_once()

    @patch("sentinel_core.remediation_orchestrator.run_remediation_sandbox")
    def test_invalid_patch_blocks_and_skips_sandbox(self, sandbox_runner):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, findings, proposal = self._fixture(root)
            proposal["base_sha256"] = "0" * 64
            result = run_remediation_orchestration(
                findings, proposal, root, policy={
                    "policy_id": "test", "require_evidence_verified": False,
                },
            )
            self.assertEqual(result["policy"]["decision"], "BLOCK")
            self.assertEqual(result["stages"]["patch_validation"]["status"], "fail")
            sandbox_runner.assert_not_called()

    @patch("sentinel_core.remediation_orchestrator.run_remediation_sandbox")
    def test_missing_scan_and_sandbox_yield_review(self, sandbox_runner):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, findings, proposal = self._fixture(root)
            result = run_remediation_orchestration(
                findings, proposal, root,
                policy={"policy_id": "test", "require_evidence_verified": False},
            )
            self.assertEqual(result["policy"]["decision"], "REVIEW")
            self.assertEqual(result["status"], "needs_review")
            sandbox_runner.assert_not_called()


    @patch("sentinel_core.remediation_orchestrator.run_security_pipeline")
    @patch("sentinel_core.remediation_orchestrator.run_remediation_sandbox")
    def test_opt_in_ai_pipeline_supplies_actual_scanner_and_reviewer_evidence(self, sandbox_runner, security_runner):
        sandbox_runner.return_value = {
            "status": "pass", "commands": [{"status": "pass"}],
            "original_repository_modified": False, "os_level_isolation": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, findings, proposal = self._fixture(root)
            security_runner.return_value = {
                "findings": findings,
                "scanner_imports": [{"scanner": "semgrep"}],
                "summary": {"adversarial_provider_requests": 3},
                "adversarial_review": {
                    "stages": {
                        "adjudicator": {
                            "reviewers": [{"provider": "openai", "reviews": [{
                                "finding_id": "F-1", "verdict": "likely",
                                "confidence": 0.95, "rationale": "Supported by source evidence.",
                                "evidence_refs": ["sample.py:1"],
                            }]}]
                        }
                    }
                },
                "stage_consensus": {
                    "adjudicator": {"consensus": [{"finding_id": "F-1"}]}
                },
                "cross_stage_analysis": [
                    {"finding_id": "F-1", "cross_stage_disagreement": False}
                ],
                "evidence_verification": {
                    "adjudicator": {"metadata": {"verified_hash_references": 1}}
                },
            }
            policy = {
                "policy_id": "ai-enabled", "max_risk_score": 100,
                "required_scanners": ["semgrep"], "required_reviewers": ["openai"],
                "min_reviewers": 1, "require_evidence_verified": False, "require_ai_adjudication": True,
                "min_adjudicator_reviewers": 1, "min_adjudicator_confidence": 0.8,
            }
            result = run_remediation_orchestration(
                findings, proposal, root, baseline_scan={"findings": []},
                candidate_scan={"findings": []}, sandbox_commands=[["python", "--version"]],
                policy=policy, scanner_inputs=[{"scanner": "semgrep", "data": {}}],
                ai_providers=["openai"],
            )
            self.assertEqual(result["policy"]["decision"], "PASS")
            self.assertEqual(result["stages"]["security_review"]["provider_requests"], 3)
            self.assertEqual(result["stages"]["ai_evidence_verification"]["verified_hash_references"], 1)
            self.assertEqual(result["stages"]["ai_adjudication"]["minimum_confidence"], 0.95)
            self.assertEqual(result["stages"]["ai_adjudication"]["status"], "complete")
            security_runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
