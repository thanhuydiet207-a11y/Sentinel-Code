import unittest
from sentinel_core.patch_risk import review_patch_risk

class PatchRiskTests(unittest.TestCase):
    def test_sensitive_path_and_exec_flag(self):
        result = review_patch_risk({"path":"src/auth.py","patch":"--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1 +1 @@\n-old\n+exec(user_input)\n"})
        self.assertIn("sensitive_path", result["flags"])
        self.assertIn("dangerous_constructs", result["flags"])
        self.assertEqual(result["risk_level"], "medium")
        self.assertFalse(result["automatic_apply_allowed"])
    def test_secret_flagged(self):
        result = review_patch_risk({"path":"config.py","patch":"--- a/config.py\n+++ b/config.py\n@@ -0,0 +1 @@\n+api_key = 'secret'\n"})
        self.assertIn("possible_secret", result["flags"])
    def test_dependency_and_multi_file_flags(self):
        result = review_patch_risk({"path":"requirements.txt","patch":"--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-old\n+new\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"})
        self.assertIn("dependency_or_build_file", result["flags"])
        self.assertIn("multi_file_patch", result["flags"])
    def test_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            review_patch_risk({"path":"../x.py","patch":"x"})
    def test_test_target_reduces_score_but_review_required(self):
        result = review_patch_risk({"path":"tests/test_app.py","patch":"--- a/tests/test_app.py\n+++ b/tests/test_app.py\n@@ -1 +1 @@\n-old\n+new\n"})
        self.assertEqual(result["risk_level"], "low")
        self.assertTrue(result["review_required"])

if __name__ == "__main__":
    unittest.main()
