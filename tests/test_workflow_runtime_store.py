import sqlite3
import unittest

from sentinel_core.workflow_runtime_store import DurableWorkflowRuntimeStore


class DurableWorkflowRuntimeStoreTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.store = DurableWorkflowRuntimeStore(self.connection)
        self.snapshot = {"stage_states": {"scan": "pending"}, "events": []}
        self.at = "2026-01-01T00:00:00+00:00"

    def test_create_and_load_snapshot(self):
        created = self.store.create("exec-1", "wf-1", self.snapshot, "ready", self.at)
        self.assertEqual(created["action"], "created")
        loaded = self.store.load("exec-1")
        self.assertEqual(loaded["snapshot"], self.snapshot)
        self.assertEqual(loaded["version"], 1)

    def test_duplicate_execution_rejected(self):
        self.store.create("exec-1", "wf-1", self.snapshot, "ready", self.at)
        self.assertEqual(self.store.create("exec-1", "wf-1", self.snapshot, "ready", self.at)["reason"], "execution_id_duplicate")

    def test_save_uses_optimistic_version(self):
        self.store.create("exec-1", "wf-1", self.snapshot, "ready", self.at)
        updated = {"stage_states": {"scan": "running"}, "events": [{"sequence": 1}]}
        self.assertEqual(self.store.save("exec-1", 1, updated, "running", self.at)["version"], 2)
        self.assertEqual(self.store.save("exec-1", 1, self.snapshot, "ready", self.at)["action"], "conflict")
        self.assertEqual(self.store.load("exec-1")["snapshot"], updated)

    def test_event_journal_is_append_only_and_ordered(self):
        events = [{"sequence": 1, "type": "started", "at": self.at}]
        self.store.create("exec-1", "wf-1", self.snapshot, "running", self.at, events)
        more = [{"sequence": 2, "type": "finished", "at": self.at}]
        self.store.save("exec-1", 1, self.snapshot, "completed", self.at, more)
        loaded = self.store.load("exec-1", include_events=True)
        self.assertEqual([event["sequence"] for event in loaded["events"]], [1, 2])

    def test_duplicate_event_sequence_rolls_back_snapshot(self):
        self.store.create("exec-1", "wf-1", self.snapshot, "running", self.at, [{"sequence": 1, "type": "start", "at": self.at}])
        result = self.store.save("exec-1", 1, {"changed": True}, "completed", self.at, [{"sequence": 1, "type": "duplicate", "at": self.at}])
        self.assertEqual(result["reason"], "event_sequence_duplicate")
        self.assertEqual(self.store.load("exec-1")["version"], 1)

    def test_recoverable_execution_listing(self):
        self.store.create("exec-1", "wf-1", self.snapshot, "ready", self.at)
        self.store.create("exec-2", "wf-2", self.snapshot, "completed", self.at)
        listed = self.store.list_recoverable()
        self.assertEqual([item["execution_id"] for item in listed["executions"]], ["exec-1"])

    def test_invalid_payloads_and_parameters_fail_closed(self):
        self.assertEqual(self.store.create("", "wf", self.snapshot, "ready", self.at)["reason"], "identifiers_invalid")
        self.assertEqual(self.store.create("exec", "wf", [], "ready", self.at)["reason"], "snapshot_invalid")
        self.assertEqual(self.store.save("exec", True, self.snapshot, "ready", self.at)["reason"], "version_invalid")
        self.assertEqual(self.store.list_recoverable(0)["reason"], "limit_invalid")
        self.assertEqual(self.store.create("exec", "wf", self.snapshot, "ready", "naive-time")["reason], "timestamp_invalid")

    def test_not_found_and_storage_failures_are_structured(self):
        self.assertEqual(self.store.load("missing")["action"], "not_found")
        self.assertEqual(self.store.save("missing", 1, self.snapshot, "ready", self.at)["action"], "not_found")


if __name__ == "__main__":
    unittest.main()
