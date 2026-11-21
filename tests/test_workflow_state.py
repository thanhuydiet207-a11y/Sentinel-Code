import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sentinel_core.workflow_state import (
    create_workflow, checkpoint_stage, checkpoint_outputs, load_workflow, resume_plan, retry_stage, verify_workflow,
)

_DIGEST = hashlib.sha256(b"input package").hexdigest()


class WorkflowStateTests(unittest.TestCase):
    def test_create_and_resume_skips_completed_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-1", ["validate", "review", "sandbox"], _DIGEST)
            checkpoint_stage(tmp, "run-1", "validate", "completed", {"ok": True})
            plan = resume_plan(tmp, "run-1", _DIGEST)
            self.assertEqual(plan["completed_stages"], ["validate"])
            self.assertEqual(plan["remaining_stages"], ["review", "sandbox"])
            self.assertEqual(plan["next_stage"], "review")
            self.assertTrue(plan["safe_to_resume"])

    def test_completed_outputs_are_persisted_and_retrievable(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-output", ["a", "b"], _DIGEST)
            payload = {"result": [1, 2], "nested": {"ok": True}}
            checkpoint_stage(tmp, "run-output", "a", "completed", payload)
            self.assertEqual(checkpoint_outputs(tmp, "run-output", _DIGEST), {"a": payload})
            state = load_workflow(tmp, "run-output")
            self.assertEqual(state["checkpoints"][0]["output"], payload)

    def test_output_digest_without_output_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-output-tamper", ["a"], _DIGEST)
            checkpoint_stage(tmp, "run-output-tamper", "a", "completed", {"ok": True})
            state = load_workflow(tmp, "run-output-tamper")
            state["checkpoints"][0]["output"] = None
            self.assertFalse(verify_workflow(state)["valid"])

    def test_completion_requires_all_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-2", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "run-2", "a", "completed")
            self.assertEqual(load_workflow(tmp, "run-2")["status"], "running")
            state = checkpoint_stage(tmp, "run-2", "b", "completed")
            self.assertEqual(state["status"], "completed")
            self.assertFalse(resume_plan(tmp, "run-2")["safe_to_resume"])

    def test_input_digest_mismatch_blocks_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-3", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "run-3", "a", "completed")
            plan = resume_plan(tmp, "run-3", hashlib.sha256(b"changed").hexdigest())
            self.assertEqual(plan["status"], "blocked")
            self.assertEqual(plan["reason"], "input_digest_mismatch")

    def test_duplicate_checkpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-4", ["a"], _DIGEST)
            checkpoint_stage(tmp, "run-4", "a", "completed")
            with self.assertRaises(ValueError):
                checkpoint_stage(tmp, "run-4", "a", "completed")

    def test_failed_stage_blocks_safe_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-5", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "run-5", "a", "failed", error="test command failed")
            plan = resume_plan(tmp, "run-5")
            self.assertFalse(plan["safe_to_resume"])
            self.assertEqual(plan["failed_stages"], ["a"])

    def test_checkpoint_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-6", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "run-6", "a", "completed", {"result": 1})
            state = load_workflow(tmp, "run-6")
            state["checkpoints"][0]["status"] = "failed"
            result = verify_workflow(state)
            self.assertFalse(result["valid"])
            self.assertIn("checkpoint_0_hash_mismatch", result["errors"])

    def test_failed_stage_can_be_retried_with_audited_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "retry-run", ["build", "verify"], _DIGEST)
            checkpoint_stage(tmp, "retry-run", "build", "completed", {"artifact": "ok"})
            checkpoint_stage(tmp, "retry-run", "verify", "failed", error="transient failure")
            plan = resume_plan(tmp, "retry-run", _DIGEST)
            self.assertEqual(plan["failed_stages"], ["verify"])
            self.assertEqual(plan["remaining_stages"], ["verify"])
            retry_stage(tmp, "retry-run", "verify")
            plan = resume_plan(tmp, "retry-run", _DIGEST)
            self.assertTrue(plan["safe_to_resume"])
            self.assertEqual(plan["remaining_stages"], ["verify"])
            checkpoint_stage(tmp, "retry-run", "verify", "completed", {"verified": True})
            state = load_workflow(tmp, "retry-run")
            self.assertEqual(state["status"], "completed")
            self.assertTrue(verify_workflow(state)["valid"])
            self.assertEqual(checkpoint_outputs(tmp, "retry-run", _DIGEST)["verify"], {"verified": True})

    def test_retry_marker_requires_latest_failed_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "retry-invalid", ["a"], _DIGEST)
            checkpoint_stage(tmp, "retry-invalid", "a", "completed")
            with self.assertRaisesRegex(ValueError, "latest failed"):
                retry_stage(tmp, "retry-invalid", "a")

    def test_failed_stage_retry_history_is_hash_chained(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "retry-chain", ["a"], _DIGEST)
            checkpoint_stage(tmp, "retry-chain", "a", "failed", error="first attempt")
            retry_stage(tmp, "retry-chain", "a")
            state = load_workflow(tmp, "retry-chain")
            self.assertTrue(verify_workflow(state)["valid"])
            state["checkpoints"][1]["status"] = "completed"
            self.assertFalse(verify_workflow(state)["valid"])
    def test_invalid_workflow_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_workflow(tmp, "../escape", ["a"], _DIGEST)

    def test_duplicate_stage_names_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                create_workflow(tmp, "run-8", ["a", "a"], _DIGEST)

    def test_stage_not_in_plan_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-9", ["a"], _DIGEST)
            with self.assertRaises(ValueError):
                checkpoint_stage(tmp, "run-9", "b", "completed")

    def test_completed_checkpoint_cannot_have_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-10", ["a"], _DIGEST)
            with self.assertRaises(ValueError):
                checkpoint_stage(tmp, "run-10", "a", "completed", error="bad")

    def test_workflow_create_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-11", ["a"], _DIGEST)
            with self.assertRaises(FileExistsError):
                create_workflow(tmp, "run-11", ["a"], _DIGEST)

    def test_store_uses_atomic_json_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "run-12", ["a"], _DIGEST)
            path = Path(tmp) / "run-12.json"
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text())["workflow_id"], "run-12")


if __name__ == "__main__":
    unittest.main()
