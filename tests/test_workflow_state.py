import hashlib
import json
import tempfile
import unittest
import threading
from pathlib import Path

from sentinel_core.workflow_state import (
    create_workflow, checkpoint_stage, checkpoint_outputs, load_workflow, resume_plan, retry_stage, verify_workflow, validate_workflow_schema, migrate_workflow, stage_execution_decision,
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
            with self.assertRaisesRegex(ValueError, "workflow is not retryable"):
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

    def test_concurrent_checkpoint_writers_are_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "parallel-run", ["a", "b"], _DIGEST)
            barrier = threading.Barrier(2)
            def writer(stage):
                barrier.wait()
                checkpoint_stage(tmp, "parallel-run", stage, "completed")
            threads = [threading.Thread(target=writer, args=(stage,)) for stage in ("a", "b")]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=5)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
            state = load_workflow(tmp, "parallel-run")
            self.assertEqual(len(state["checkpoints"]), 2)
            self.assertEqual(state["status"], "completed")
            self.assertTrue(verify_workflow(state)["valid"])
            self.assertFalse((Path(tmp) / "parallel-run.json.lock").exists())

    def test_lock_timeout_does_not_modify_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "locked-run", ["a"], _DIGEST)
            lock = Path(tmp) / "locked-run.json.lock"
            lock.write_text("manual lock", encoding="utf-8")
            with self.assertRaises(TimeoutError):
                checkpoint_stage(tmp, "locked-run", "a", "completed")
            self.assertEqual(load_workflow(tmp, "locked-run")["checkpoints"], [])
            lock.unlink()
    def test_schema1_migration_creates_backup_and_preserves_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "legacy-run", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "legacy-run", "a", "completed", {"old": True})
            path = Path(tmp) / "legacy-run.json"
            legacy = json.loads(path.read_text())
            legacy["schema_version"] = 1
            legacy.pop("migration_history", None)
            path.write_text(json.dumps(legacy), encoding="utf-8")
            self.assertTrue(validate_workflow_schema(legacy)["valid"])
            result = migrate_workflow(tmp, "legacy-run")
            self.assertEqual(result["status"], "migrated")
            self.assertTrue(Path(result["backup"]).exists())
            migrated = load_workflow(tmp, "legacy-run")
            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(migrated["migration_history"][-1]["from"], 1)
            self.assertTrue(verify_workflow(migrated)["valid"])
            self.assertEqual(checkpoint_outputs(tmp, "legacy-run")["a"], {"old": True})

    def test_schema_validation_rejects_missing_required_fields(self):
        malformed = {"schema_version": 2, "workflow_id": "bad"}
        result = validate_workflow_schema(malformed)
        self.assertFalse(result["valid"])
        self.assertIn("missing_checkpoints", result["errors"])

    def test_migration_refuses_corrupt_checkpoint_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "legacy-corrupt", ["a"], _DIGEST)
            checkpoint_stage(tmp, "legacy-corrupt", "a", "completed")
            path = Path(tmp) / "legacy-corrupt.json"
            state = json.loads(path.read_text())
            state["schema_version"] = 1
            state.pop("migration_history", None)
            state["checkpoints"][0]["status"] = "failed"
            path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity validation failed"):
                migrate_workflow(tmp, "legacy-corrupt")
            self.assertFalse(Path(tmp, "legacy-corrupt.json.schema1.bak").exists())

    def test_workflow_status_must_match_checkpoint_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "status-audit", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "status-audit", "a", "completed")
            state = load_workflow(tmp, "status-audit")
            state["status"] = "completed"
            result = verify_workflow(state)
            self.assertFalse(result["valid"])
            self.assertIn("workflow_status_checkpoint_mismatch", result["errors"])
            path = Path(tmp) / "status-audit.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            plan = resume_plan(tmp, "status-audit")
            self.assertEqual(plan["status"], "blocked")
            self.assertEqual(plan["reason"], "checkpoint_integrity_invalid")

    def test_failed_stage_status_must_match_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "failed-consistency", ["a"], _DIGEST)
            checkpoint_stage(tmp, "failed-consistency", "a", "failed", error="failure")
            state = load_workflow(tmp, "failed-consistency")
            state["status"] = "running"
            result = verify_workflow(state)
            self.assertFalse(result["valid"])
            self.assertIn("workflow_status_checkpoint_mismatch", result["errors"])

    def test_checkpoint_event_semantics_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "event-semantics", ["a"], _DIGEST)
            checkpoint_stage(tmp, "event-semantics", "a", "completed")
            state = load_workflow(tmp, "event-semantics")
            event = state["checkpoints"][0]
            event["error"] = "invalid completed event"
            event["event_hash"] = hashlib.sha256(json.dumps({k:v for k,v in event.items() if k != "event_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            state["head_hash"] = event["event_hash"]
            result = verify_workflow(state)
            self.assertFalse(result["valid"])
            self.assertIn("checkpoint_0_completed_error_present", result["errors"])

    def test_resume_execution_gate_skips_completed_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "gate-completed", ["a", "b"], _DIGEST)
            checkpoint_stage(tmp, "gate-completed", "a", "completed")
            result = stage_execution_decision(tmp, "gate-completed", "a", _DIGEST)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["reason"], "stage_already_terminal")

    def test_resume_execution_gate_enforces_stage_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "gate-order", ["a", "b"], _DIGEST)
            result = stage_execution_decision(tmp, "gate-order", "b", _DIGEST)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["reason"], "prior_stage_incomplete")

    def test_resume_execution_gate_requires_idempotency_for_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "gate-side-effect", ["a"], _DIGEST)
            result = stage_execution_decision(tmp, "gate-side-effect", "a", _DIGEST, side_effecting=True)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["reason"], "idempotency_key_required")
            approved = stage_execution_decision(tmp, "gate-side-effect", "a", _DIGEST, side_effecting=True, idempotency_key="run-a-stage-a")
            self.assertTrue(approved["allowed"])

    def test_resume_execution_gate_blocks_input_mismatch_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            create_workflow(tmp, "gate-integrity", ["a"], _DIGEST)
            wrong = stage_execution_decision(tmp, "gate-integrity", "a", hashlib.sha256(b"changed").hexdigest())
            self.assertEqual(wrong["reason"], "input_digest_mismatch")
            state = load_workflow(tmp, "gate-integrity")
            state["status"] = "completed"
            path = Path(tmp) / "gate-integrity.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            blocked = stage_execution_decision(tmp, "gate-integrity", "a", _DIGEST)
            self.assertEqual(blocked["reason"], "checkpoint_integrity_invalid")

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
