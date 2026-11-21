import hashlib
import tempfile
import unittest
from pathlib import Path

from sentinel_core.patch_validation import PatchValidationError, validate_patch_proposal


class PatchValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = "def query(value):\\n    return value\\n"
        (self.root / "app.py").write_text(self.source, encoding="utf-8")
        self.findings = {"findings": [{
            "id": "F-1", "location": {"path": "app.py", "start_line": 2, "end_line": 2}
        }]}
        self.patch = (
            "--- a/app.py\\n+++ b/app.py\\n"
            "@@ -1,2 +1,2 @@\\n"
            " def query(value):\\n"
            "-    return value\\n"
            "+    return safe(value)\\n"
        )
        self.proposal = {
            "finding_id": "F-1",
            "path": "app.py",
            "base_sha256": hashlib.sha256(self.source.encode()).hexdigest(),
            "patch": self.patch,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_patch_returns_candidate_without_modifying_source(self):
        result = validate_patch_proposal(self.proposal, self.findings, self.root)
        self.assertEqual(result["status"], "validated_candidate")
        self.assertEqual(result["candidate_content"], "def query(value):\\n    return safe(value)\\n")
        self.assertFalse(result["file_modified"])
        self.assertEqual((self.root / "app.py").read_text(), self.source)

    def test_rejects_stale_base_hash(self):
        stale = {**self.proposal, "base_sha256": "0" * 64}
        with self.assertRaisesRegex(PatchValidationError, "does not match"):
            validate_patch_proposal(stale, self.findings, self.root)

    def test_rejects_path_mismatch_and_traversal(self):
        wrong = {**self.proposal, "path": "other.py"}
        with self.assertRaisesRegex(PatchValidationError, "exactly match"):
            validate_patch_proposal(wrong, self.findings, self.root)
        traversal = {**self.proposal, "path": "../app.py"}
        with self.assertRaises(PatchValidationError):
            validate_patch_proposal(traversal, self.findings, self.root)

    def test_rejects_patch_context_that_does_not_match(self):
        bad = {**self.proposal, "patch": self.patch.replace("return value", "return unrelated")}
        with self.assertRaisesRegex(PatchValidationError, "does not match source"):
            validate_patch_proposal(bad, self.findings, self.root)

    def test_rejects_multiple_file_headers(self):
        bad = {**self.proposal, "patch": self.patch + "--- a/other.py\\n+++ b/other.py\\n"}
        with self.assertRaisesRegex(PatchValidationError, "unsupported unified diff"):
            validate_patch_proposal(bad, self.findings, self.root)


if __name__ == "__main__":
    unittest.main()
