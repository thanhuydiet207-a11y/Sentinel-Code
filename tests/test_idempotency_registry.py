import copy
import unittest

from sentinel_core.idempotency_registry import reserve_execution, transition_execution, verify_registry


class IdempotencyRegistryTests(unittest.TestCase):
    def test_reserve_new_key_without_mutation(self):
        state = {}
        result = reserve_execution(state, "secret-key", {"stage": "scan", "input": 1}, "exec-1")
        self.assertEqual(result["action"], "reserved")
        self.assertEqual(state, {})
        self.assertNotIn("secret-key", str(result))
        self.assertEqual(len(result["record"]["key_digest"]), 64)

    def test_same_key_same_payload_is_replay(self):
        first = reserve_execution({}, "key", {"x": 1}, "exec-1")
        state = {first["registry_key"]: first["record"]}
        replay = reserve_execution(state, "key", {"x": 1}, "exec-2")
        self.assertEqual(replay["action"], "replay")
        self.assertEqual(replay["record"]["execution_id"], "exec-1")

    def test_same_key_different_payload_conflicts(self):
        first = reserve_execution({}, "key", {"x": 1}, "exec-1")
        state = {first["registry_key"]: first["record"]}
        result = reserve_execution(state, "key", {"x": 2}, "exec-2")
        self.assertEqual(result["reason"], "idempotency_key_payload_conflict")

    def test_invalid_inputs_fail_closed(self):
        self.assertEqual(reserve_execution({}, "", {}, "exec")["action"], "blocked")
        self.assertEqual(reserve_execution([], "key", {}, "exec")["action"], "blocked")

    def test_valid_transitions(self):
        first = reserve_execution({}, "key", {}, "exec-1")
        state = {first["registry_key"]: first["record"]}
        running = transition_execution(state, first["registry_key"], "running")
        completed = transition_execution(running["registry"], first["registry_key"], "completed")
        self.assertEqual(completed["action"], "updated")
        self.assertEqual(completed["record"]["status"], "completed")

    def test_invalid_transition_blocked_and_input_unchanged(self):
        first = reserve_execution({}, "key", {}, "exec-1")
        state = {first["registry_key"]: first["record"]}
        snapshot = copy.deepcopy(state)
        result = transition_execution(state, first["registry_key"], "completed")
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(state, snapshot)

    def test_registry_verification_detects_duplicate_execution_ids(self):
        a = reserve_execution({}, "key-a", {}, "exec-1")
        b = reserve_execution({}, "key-b", {}, "exec-1")
        state = {a["registry_key"]: a["record"], b["registry_key"]: b["record"]}
        result = verify_registry(state)
        self.assertFalse(result["valid"])
        self.assertIn("duplicate_execution_id", result["errors"])

    def test_registry_verifies_clean_records(self):
        a = reserve_execution({}, "key-a", {"v": 1}, "exec-1")
        state = {a["registry_key"]: a["record"]}
        self.assertTrue(verify_registry(state)["valid"])


if __name__ == "__main__":
    unittest.main()
