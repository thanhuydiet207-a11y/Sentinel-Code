import json
import tempfile
import unittest
from pathlib import Path

from sentinel_core.scanner_adapters import import_scanner_results


class ScannerAdapterTests(unittest.TestCase):
    def test_imports_semgrep_and_hashes_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "src" / "app.py"
            source.parent.mkdir()
            source.write_text("user = request.args['user']\nexec(user)\n", encoding="utf-8")
            data = {"results": [{
                "check_id": "python.lang.security.audit.exec-used",
                "path": "src/app.py",
                "start": {"line": 2},
                "end": {"line": 2},
                "extra": {"severity": "ERROR", "message": "Unsafe exec"},
            }]}
            payload = import_scanner_results("semgrep", data, root)
            self.assertEqual(len(payload["findings"]), 1)
            finding = payload["findings"][0]
            self.assertEqual(finding["location"]["path"], "src/app.py")
            self.assertEqual(finding["severity"], "high")
            self.assertEqual(len(finding["evidence"]["line_hash"]), 64)

    def test_skips_path_escape_and_reports_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = import_scanner_results("gitleaks", [{"File": "../outside", "RuleID": "secret"}], tmp)
            self.assertEqual(payload["findings"], [])
            self.assertEqual(len(payload["metadata"]["skipped"]), 1)

    def test_trivy_import_uses_target_manifest_and_skips_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
            payload = import_scanner_results("trivy", {"Results": [{
                "Target": "package-lock.json",
                "Vulnerabilities": [{"VulnerabilityID": "CVE-2024-1234", "Severity": "HIGH", "Title": "Example issue"}],
            }]}, root)
            self.assertEqual(len(payload["findings"]), 1)
            self.assertEqual(payload["findings"][0]["location"]["start_line"], 1)
            self.assertEqual(payload["findings"][0]["category"], "custom:dependency-vulnerability")

    def test_rejects_unknown_scanner(self):
        with self.assertRaises(ValueError):
            import_scanner_results("unknown", {}, ".")


if __name__ == "__main__":
    unittest.main()
