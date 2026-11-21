import hashlib
import tempfile
import unittest
from pathlib import Path

from sentinel_core.evidence_verification import verify_ai_evidence


class EvidenceVerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        source = "first line\nunsafe = input()\nlast line\n"
        (self.root / "app.py").write_text(source, encoding="utf-8")
        digest = hashlib.sha256("unsafe = input()".encode()).hexdigest()
        self.findings = {"findings": [{
            "id": "F-1",
            "location": {"path": "app.py", "start_line": 2, "end_line": 2},
            "evidence": {"line_hash": digest},
        }]}

    def tearDown(self):
        self.tmp.cleanup()

    def _reviews(self, refs):
        return {"reviewers": [{"reviewer_id": "r1", "reviews": [{"finding_id": "F-1", "evidence_refs": refs}]}]}

    def test_exact_location_and_hash_verified(self):
        result = verify_ai_evidence(self.findings, self._reviews(["app.py:2"]), self.root)
        check = result["verification"][0]
        self.assertEqual(check["verification_status"], "verified_location_and_hash")
        self.assertEqual(check["hash_match_count"], 1)

    def test_existing_but_wrong_location_not_hash_verified(self):
        result = verify_ai_evidence(self.findings, self._reviews(["app.py:1"]), self.root)
        check = result["verification"][0]
        self.assertEqual(check["verification_status"], "valid_references")
        self.assertEqual(check["hash_match_count"], 0)

    def test_missing_reference_reported_unverified(self):
        result = verify_ai_evidence(self.findings, self._reviews([]), self.root)
        self.assertEqual(result["verification"][0]["verification_status"], "unverified")

    def test_traversal_reference_rejected(self):
        result = verify_ai_evidence(self.findings, self._reviews(["../secret.py:1"]), self.root)
        self.assertEqual(result["verification"][0]["verification_status"], "unverified")
        self.assertFalse(result["verification"][0]["checks"][0]["valid"])

    def test_line_out_of_bounds(self):
        result = verify_ai_evidence(self.findings, self._reviews(["app.py:99"]), self.root)
        self.assertFalse(result["verification"][0]["checks"][0]["valid"])


if __name__ == "__main__":
    unittest.main()
