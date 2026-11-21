import unittest
from sentinel_core.regression import compare_scan_snapshots

def f(rule, path="src/a.py", line=4, severity="high", scanner="semgrep", title="Issue"):
    return {"rule_id": rule, "scanner": scanner, "title": title, "severity": severity,
            "location": {"path": path, "start_line": line}}

class ScanRegressionTests(unittest.TestCase):
    def test_classifies_fixed_new_persisting(self):
        baseline = {"findings": [f("A"), f("B", line=8), f("C", path="src/b.py")]}
        candidate = {"findings": [f("A"), f("D", line=10)]}
        result = compare_scan_snapshots(baseline, candidate)
        self.assertEqual(result["summary"]["fixed_count"], 2)
        self.assertEqual(result["summary"]["new_count"], 1)
        self.assertEqual(result["summary"]["persisting_count"], 1)
        self.assertEqual(result["status"], "regression")
    def test_severity_increase_is_regression(self):
        result = compare_scan_snapshots([f("A", severity="low")], [f("A", severity="critical")])
        self.assertEqual(result["severity_changes"][0]["direction"], "worsened")
        self.assertEqual(result["status"], "regression")
    def test_severity_decrease_is_not_regression(self):
        result = compare_scan_snapshots([f("A", severity="high")], [f("A", severity="low")])
        self.assertEqual(result["severity_changes"][0]["direction"], "improved")
        self.assertEqual(result["status"], "clean")
    def test_hash_identity_ignores_line_shift(self):
        a = f("A", line=4); a["evidence"] = {"line_hash": "same"}
        b = f("A", line=50); b["evidence"] = {"line_hash": "same"}
        result = compare_scan_snapshots([a], [b])
        self.assertEqual(result["summary"]["persisting_count"], 1)
    def test_rejects_malformed_payload(self):
        with self.assertRaises(ValueError):
            compare_scan_snapshots({"findings": "bad"}, [])
    def test_duplicates_reported(self):
        result = compare_scan_snapshots([f("A"), f("A")], [f("A")])
        self.assertEqual(result["summary"]["duplicate_count"], 1)

if __name__ == "__main__":
    unittest.main()
