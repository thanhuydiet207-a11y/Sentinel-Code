import unittest
from sentinel_core.false_positive import analyze_findings

def finding(**overrides):
    base = {"id":"F-1","rule_id":"rule/test","title":"User input reaches SQL query","severity":"high","confidence":.8,
            "location":{"path":"src/a.py","start_line":2,"end_line":2},
            "evidence":{"reason":"Source evidence","line_hash":"a"*64}}
    base.update(overrides)
    return base

class FalsePositiveTests(unittest.TestCase):
    def test_strong_evidence_still_requires_review(self):
        result=analyze_findings({"findings":[finding()]})["triage"][0]
        self.assertEqual(result["disposition"],"review")
        self.assertFalse(result["automatic_suppression"])

    def test_missing_evidence_is_flagged(self):
        result=analyze_findings({"findings":[finding(evidence={})]})["triage"][0]
        self.assertEqual(result["disposition"],"needs_review")
        self.assertIn("missing evidence explanation",result["reasons"])

    def test_low_confidence_and_invalid_location_are_flagged(self):
        item=finding(confidence=.1,location={"path":"x","start_line":0,"end_line":-1})
        result=analyze_findings({"findings":[item]})["triage"][0]
        self.assertGreater(result["heuristic_fp_risk"],0)
        self.assertIn("low scanner confidence",result["reasons"])


    def test_uncertainty_wording_in_title_requires_extra_triage(self):
        result=analyze_findings({"findings":[finding(title="Potential issue")]})["triage"][0]
        self.assertEqual(result["disposition"],"needs_review")
        self.assertIn("generic or uncertainty wording in title",result["reasons"])

    def test_never_auto_suppresses(self):
        result=analyze_findings({"findings":[finding(evidence={})]})
        self.assertFalse(result["triage"][0]["automatic_suppression"])
        self.assertFalse(result["metadata"]["automatic_suppression"])

if __name__ == "__main__":
    unittest.main()
