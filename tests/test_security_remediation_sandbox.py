import tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from sentinel_core.remediation_sandbox import SandboxValidationError, run_remediation_sandbox

class RemediationSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("old\n", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=not-copied\n", encoding="utf-8")
        (self.root / "secret.json").write_text("should-not-copy\n", encoding="utf-8")
    def tearDown(self):
        self.tmp.cleanup()
    def test_candidate_temp_workspace_and_original_unchanged(self):
        def fake_run(command, **kwargs):
            workspace = Path(kwargs["cwd"])
            self.assertEqual((workspace / "src/app.py").read_text(), "candidate\n")
            self.assertFalse((workspace / ".env").exists())
            self.assertFalse((workspace / "secret.json").exists())
            return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
        with patch("sentinel_core.remediation_sandbox.subprocess.run", side_effect=fake_run):
            result = run_remediation_sandbox(self.root, "src/app.py", "candidate\n", [["python3", "-m", "unittest"]])
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["original_repository_modified"])
        self.assertEqual((self.root / "src/app.py").read_text(), "old\n")
    def test_stops_on_failed_command(self):
        def fake_run(command, **kwargs):
            return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "failed"})()
        with patch("sentinel_core.remediation_sandbox.subprocess.run", side_effect=fake_run):
            result = run_remediation_sandbox(self.root, "src/app.py", "candidate\n",
                [["python3", "-m", "unittest"], ["semgrep", "--version"]])
        self.assertEqual(result["status"], "fail")
        self.assertEqual(len(result["commands"]), 1)
    def test_rejects_shell_and_disallowed_executable(self):
        for command in (["python3", "-c", "x", "&&", "rm"], ["bash", "-c", "echo x"]):
            with self.assertRaises(SandboxValidationError):
                run_remediation_sandbox(self.root, "src/app.py", "candidate", [command])
    def test_rejects_traversal_and_secret_target(self):
        for path in ("../outside.py", ".env", "secrets.json"):
            with self.assertRaises(SandboxValidationError):
                run_remediation_sandbox(self.root, path, "candidate", [["python3", "--version"]])
    def test_timeout_is_reported(self):
        import subprocess
        with patch("sentinel_core.remediation_sandbox.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(["python3"], 1, output="out", stderr="err")):
            result = run_remediation_sandbox(self.root, "src/app.py", "candidate",
                [["python3", "--version"]], timeout_seconds=1)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["commands"][0]["status"], "timeout")

if __name__ == "__main__":
    unittest.main()
