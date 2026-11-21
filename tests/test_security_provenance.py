import json
import tempfile
import unittest
from pathlib import Path
from sentinel_core.provenance import seal_evidence_bundle, verify_evidence_bundle

class EvidenceProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scan.json").write_text('{"findings":[]}', encoding="utf-8")
        (self.root / "tests.json").write_text('{"status":"pass"}', encoding="utf-8")
    def tearDown(self):
        self.tmp.cleanup()
    def bundle(self):
        return {"source_commit":"abc123", "candidate_sha256":"a"*64,
                "artifacts":[{"name":"scan","kind":"scanner","path":"scan.json"},
                             {"name":"tests","kind":"test","path":"tests.json"}]}
    def test_seal_and_verify(self):
        sealed=seal_evidence_bundle(self.bundle(), self.root)
        result=verify_evidence_bundle(sealed, self.root)
        self.assertTrue(result["valid"])
        self.assertTrue(result["bundle_hash_valid"])
    def test_tampering_detected(self):
        sealed=seal_evidence_bundle(self.bundle(), self.root)
        (self.root/"scan.json").write_text("tampered", encoding="utf-8")
        result=verify_evidence_bundle(sealed, self.root)
        self.assertFalse(result["valid"])
        self.assertFalse(result["artifact_checks"][0]["valid"])
    def test_bundle_metadata_tampering_detected(self):
        sealed=seal_evidence_bundle(self.bundle(), self.root)
        sealed["source_commit"]="changed"
        self.assertFalse(verify_evidence_bundle(sealed, self.root)["bundle_hash_valid"])
    def test_traversal_rejected(self):
        b=self.bundle(); b["artifacts"][0]["path"]="../scan.json"
        with self.assertRaises(ValueError): seal_evidence_bundle(b, self.root)
    def test_symlink_rejected(self):
        (self.root/"link").symlink_to(self.root/"scan.json")
        b=self.bundle(); b["artifacts"][0]["path"]="link"
        with self.assertRaises(ValueError): seal_evidence_bundle(b, self.root)
    def test_duplicate_names_rejected(self):
        b=self.bundle(); b["artifacts"][1]["name"]="scan"
        with self.assertRaises(ValueError): seal_evidence_bundle(b, self.root)

if __name__ == "__main__":
    unittest.main()
