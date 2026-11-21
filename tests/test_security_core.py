import hashlib
import tempfile
import unittest
from pathlib import Path

from sentinel_core.core import (
    deduplicate_findings, line_hash_from_text, priority_score,
    render_markdown_report, validate_payload,
)


def make_finding(root: Path, source: str, **overrides):
    path = root / "src" / "handler.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    finding = {
        "id": "TEST-001",
        "title": "Untrusted input reaches a command sink",
        "rule_id": "CWE-78/OS-COMMAND-INJECTION",
        "category": "CWE-78",
        "severity": "high",
        "confidence": 0.9,
        "location": {"path": "src/handler.py", "start_line": 2, "end_line": 2},
        "evidence": {
            "reason": "The request parameter is concatenated into a shell command.",
            "line_hash": line_hash_from_text(source, 2, 2),
            "data_flow": ["request.args.name", "shell command argument"],
        },
        "impact": "An attacker may execute unintended commands.",
        "remediation": "Pass a fixed executable and an argument array with shell=False.",
    }
    finding.update(overrides)
    return {"schema_version": "1.0", "findings": [finding]}, finding


class SecurityCoreTests(unittest.TestCase):
    def test_validates_matching_source_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = make_finding(root, "name = request.args['name']\nrun(name)\n")
            self.assertEqual(validate_payload(payload, root), [])

    def test_rejects_stale_line_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, _ = make_finding(root, "name = request.args['name']\nrun(name)\n")
            (root / "src/handler.py").write_text("name = request.args['name']\nrun_safe(name)\n", encoding="utf-8")
            errors = validate_payload(payload, root)
            self.assertTrue(any("line_hash does not match" in error for error in errors))

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, finding = make_finding(root, "name = 1\nrun(name)\n")
            finding["location"]["path"] = "../outside.py"
            self.assertTrue(any("traversal" in error for error in validate_payload(payload, root)))

    def test_rejects_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, finding = make_finding(root, "name = 1\nrun(name)\n")
            finding["location"]["path"] = str(root / "src/handler.py")
            self.assertTrue(any("absolute" in error for error in validate_payload(payload, root)))

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            outside = Path(tmp) / "outside.py"
            root.mkdir()
            outside.write_text("one\ntwo\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src/escape.py").symlink_to(outside)
            payload = {
                "schema_version": "1.0",
                "findings": [{
                    "id": "ESCAPE-1", "title": "Escape", "rule_id": "CWE-78/TEST",
                    "category": "CWE-78", "severity": "high", "confidence": 0.9,
                    "location": {"path": "src/escape.py", "start_line": 1, "end_line": 1},
                    "evidence": {"reason": "test", "line_hash": line_hash_from_text("one\ntwo\n", 1, 1)},
                    "impact": "test", "remediation": "test"
                }]
            }
            self.assertTrue(any("outside" in error for error in validate_payload(payload, root)))

    def test_rejects_invalid_confidence_and_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload, finding = make_finding(root, "name = 1\nrun(name)\n")
            finding["confidence"] = 2
            finding["category"] = "SQL injection"
            errors = validate_payload(payload, root)
            self.assertTrue(any("confidence" in error for error in errors))
            self.assertTrue(any("category" in error for error in errors))

    def test_line_hash_is_stable_and_checks_range(self):
        expected = hashlib.sha256(b"alpha\nbeta").hexdigest()
        self.assertEqual(line_hash_from_text("alpha\nbeta\n", 1, 2), expected)
        with self.assertRaises(ValueError):
            line_hash_from_text("alpha", 0, 1)

    def test_priority_score_is_transparent_and_bounded(self):
        self.assertEqual(priority_score({"severity": "high", "confidence": 0.8}), 64.0)
        self.assertEqual(priority_score({"severity": "critical", "confidence": 0.5}), 50.0)
        self.assertEqual(priority_score({"severity": "high", "confidence": 2}), 0.0)

    def test_deduplicates_same_rule_and_location_using_best_confidence(self):
        low = {"id": "A", "rule_id": "CWE-89/SQLI", "severity": "high", "confidence": 0.4,
               "location": {"path": "src/a.py", "start_line": 10, "end_line": 10}}
        high = dict(low, id="B", confidence=0.95)
        output = deduplicate_findings([low, high])
        self.assertEqual(len(output), 1)
        self.assertEqual(output[0]["id"], "B")
        self.assertEqual(output[0]["duplicate_count"], 2)
        self.assertEqual(output[0]["priority_score"], 76.0)

    def test_report_includes_triage_details_without_raw_source(self):
        item = {"id": "A", "title": "Unsafe operation", "rule_id": "CWE-78/EXEC",
                "category": "CWE-78", "severity": "high", "confidence": 0.75,
                "location": {"path": "src/a.py", "start_line": 3, "end_line": 3},
                "evidence": {"reason": "Input flows to shell", "data_flow": ["source", "sink"]},
                "impact": "Command execution", "remediation": "Use argv"}
        report = render_markdown_report([item], "PR #1")
        self.assertIn("Priority score", report)
        self.assertIn("60.00", report)
        self.assertIn("PR #1", report)
        self.assertNotIn("raw_secret_value", report)


if __name__ == "__main__":
    unittest.main()
