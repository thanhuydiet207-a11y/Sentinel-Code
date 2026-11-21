import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentinel_core.idempotency_store import IdempotencyStore


class DurableIdempotencyStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = IdempotencyStore(self.db)

    def tearDown(self):
        self.db.close()

    def test_reserve_and_replay(self):
        first = self.store.reserve("secret", {"a": 1}, "exec-1")
        replay = self.store.reserve("secret", {"a": 1}, "exec-2")
        self.assertEqual(first["action"], "reserved")
        self.assertEqual(replay["action"], "replay")
        self.assertEqual(replay["record"]["execution_id"], "exec-1")
        self.assertNotIn("secret", str(first))

    def test_payload_conflict(self):
        self.store.reserve("key", {"a": 1}, "exec-1")
        self.assertEqual(self.store.reserve("key", {"a": 2}, "exec-2")["reason"], "idempotency_key_payload_conflict")

    def test_execution_id_unique(self):
        self.store.reserve("key-a", {}, "exec-1")
        self.assertEqual(self.store.reserve("key-b", {}, "exec-1")["reason"], "execution_id_duplicate")

    def test_state_transitions(self):
        self.store.reserve("key", {}, "exec-1")
        self.assertEqual(self.store.transition("key", "running")["action"], "updated")
        self.assertEqual(self.store.transition("key", "completed")["record"]["status"], "completed")
        self.assertEqual(self.store.transition("key", "failed")["reason"], "transition_invalid")

    def test_missing_key_and_invalid_inputs(self):
        self.assertEqual(self.store.get("missing")["action"], "not_found")
        self.assertEqual(self.store.reserve("", {}, "exec")["action"], "blocked")

    def test_persistence_across_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "registry.sqlite")
            conn1 = sqlite3.connect(path)
            store1 = IdempotencyStore(conn1)
            self.assertEqual(store1.reserve("persist-key", {"v": 1}, "persist-exec")["action"], "reserved")
            conn1.close()
            conn2 = sqlite3.connect(path)
            store2 = IdempotencyStore(conn2)
            self.assertEqual(store2.get("persist-key")["record"]["execution_id"], "persist-exec")
            conn2.close()

    def test_two_connections_do_not_create_duplicate_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "registry.sqlite")
            c1, c2 = sqlite3.connect(path), sqlite3.connect(path)
            s1, s2 = IdempotencyStore(c1), IdempotencyStore(c2)
            self.assertEqual(s1.reserve("same", {"x": 1}, "exec-a")["action"], "reserved")
            self.assertEqual(s2.reserve("same", {"x": 1}, "exec-b")["action"], "replay")
            self.assertEqual(s1.count(), 1)
            c1.close()
            c2.close()


if __name__ == "__main__":
    unittest.main()
