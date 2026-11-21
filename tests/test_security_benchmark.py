import unittest

from sentinel_core.benchmark import evaluate_benchmark


def sample_dataset():
    return {
        "dataset_version": "test",
        "cases": [
            {"id": "vuln", "label": "vulnerable", "expected_findings": [
                {"rule_id": "CWE-89/SQLI", "category": "CWE-89", "path": "src/a.js",
                 "start_line": 4, "end_line": 5, "severity": "high"}]},
            {"id": "safe", "label": "safe", "expected_findings": []},
        ],
    }


class BenchmarkTests(unittest.TestCase):
    def test_perfect_result_has_perfect_metrics(self):
        results = {"agent": "test-agent", "cases": [
            {"case_id": "vuln", "findings": [
                {"rule_id": "cwe-89/sqli", "category": "CWE-89", "path": "src/a.js",
                 "start_line": 5, "end_line": 5, "severity": "high"}]},
            {"case_id": "safe", "findings": []},
        ]}
        summary = evaluate_benchmark(sample_dataset(), results)["summary"]
        self.assertEqual(summary["true_positive"], 1)
        self.assertEqual(summary["false_positive"], 0)
        self.assertEqual(summary["false_negative"], 0)
        self.assertEqual(summary["precision"], 1.0)
        self.assertEqual(summary["recall"], 1.0)
        self.assertEqual(summary["f1"], 1.0)
        self.assertEqual(summary["case_coverage"], 1.0)

    def test_false_positive_on_safe_case_is_counted(self):
        results = {"cases": [
            {"case_id": "vuln", "findings": []},
            {"case_id": "safe", "findings": [
                {"rule_id": "CWE-89/SQLI", "path": "src/safe.js", "start_line": 1, "end_line": 1}]},
        ]}
        summary = evaluate_benchmark(sample_dataset(), results)["summary"]
        self.assertEqual(summary["false_negative"], 1)
        self.assertEqual(summary["false_positive"], 1)
        self.assertEqual(summary["safe_case_false_positive_rate"], 1.0)
        self.assertEqual(summary["f1"], 0.0)

    def test_missing_case_reduces_coverage_and_counts_missed_findings(self):
        results = {"cases": [{"case_id": "safe", "findings": []}]}
        summary = evaluate_benchmark(sample_dataset(), results)["summary"]
        self.assertEqual(summary["case_coverage"], 0.5)
        self.assertEqual(summary["false_negative"], 1)

    def test_no_predictions_do_not_receive_perfect_precision(self):
        results = {"cases": [
            {"case_id": "vuln", "findings": []},
            {"case_id": "safe", "findings": []},
        ]}
        summary = evaluate_benchmark(sample_dataset(), results)["summary"]
        self.assertIsNone(summary["precision"])
        self.assertEqual(summary["recall"], 0.0)
        self.assertEqual(summary["f1"], 0.0)
        self.assertEqual(summary["safe_case_false_positive_rate"], 0.0)

    def test_unscored_cases_are_listed(self):
        summary = evaluate_benchmark(sample_dataset(), {"cases": []})["summary"]
        self.assertEqual(summary["unscored_case_ids"], ["safe", "vuln"])
        self.assertIsNone(summary["precision"])
        self.assertEqual(summary["recall"], 0.0)

    def test_duplicate_predictions_are_not_double_counted(self):
        prediction = {"rule_id": "CWE-89/SQLI", "path": "src/a.js", "start_line": 4, "end_line": 5}
        results = {"cases": [
            {"case_id": "vuln", "findings": [prediction, dict(prediction)]},
            {"case_id": "safe", "findings": []},
        ]}
        summary = evaluate_benchmark(sample_dataset(), results)["summary"]
        self.assertEqual(summary["true_positive"], 1)
        self.assertEqual(summary["false_positive"], 0)

    def test_rejects_unknown_and_duplicate_case_ids(self):
        with self.assertRaisesRegex(ValueError, "unknown result case"):
            evaluate_benchmark(sample_dataset(), {"cases": [{"case_id": "missing", "findings": []}]})
        with self.assertRaisesRegex(ValueError, "duplicate result case"):
            evaluate_benchmark(sample_dataset(), {"cases": [
                {"case_id": "safe", "findings": []}, {"case_id": "safe", "findings": []}
            ]})

    def test_rejects_safe_case_with_ground_truth_finding(self):
        bad = sample_dataset()
        bad["cases"][1]["expected_findings"] = [{"rule_id": "CWE-1/X", "path": "x", "start_line": 1, "end_line": 1}]
        with self.assertRaisesRegex(ValueError, "safe cases"):
            evaluate_benchmark(bad, {"cases": []})


if __name__ == "__main__":
    unittest.main()
