import sqlite3
import unittest

from sentinel_core.workflow_runtime import WorkflowExecutionRuntime
from sentinel_core.workflow_runtime_store import DurableWorkflowRuntimeStore
from sentinel_core.durable_workflow_runtime import DurableWorkflowRuntime


class DurableWorkflowRuntimeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.store = DurableWorkflowRuntimeStore(sqlite3.connect(":memory:"))
        self.at = "2026-01-01T00:00:00+00:00"

    def test_create_persist_and_restore_lifecycle(self):
        runtime = WorkflowExecutionRuntime(["scan", "report"], {"report": ["scan"]})
        created = DurableWorkflowRuntime.create(self.store, "exec-1", "wf-1", runtime, self.at)
        adapter = created["durable_runtime"]
        runtime.start_stage("scan", self.at)
        self.assertEqual(adapter.persist(self.at)["version"], 2)
        restored = DurableWorkflowRuntime.restore(self.store, "exec-1")
        recovered = restored["durable_runtime"]
        self.assertEqual(recovered.runtime.stage_states["scan"], "running")
        self.assertEqual(recovered.runtime.events[0]["type"], "stage_started")
        recovered.runtime.finish_stage("scan", "completed", "2026-01-01T00:00:01+00:00")
        self.assertEqual(recovered.persist("2026-01-01T00:00:01+00:00")["version"], 3)
        again = DurableWorkflowRuntime.restore(self.store, "exec-1")["durable_runtime"]
        self.assertEqual(again.runtime.stage_states["scan"], "completed")
        self.assertEqual([event["sequence"] for event in again.runtime.events], [1, 2])

    def test_stale_adapter_write_is_rejected(self):
        runtime = WorkflowExecutionRuntime(["a"])
        DurableWorkflowRuntime.create(self.store, "exec-1", "wf-1", runtime, self.at)
        first = DurableWorkflowRuntime.restore(self.store, "exec-1")["durable_runtime"]
        second = DurableWorkflowRuntime.restore(self.store, "exec-1")["durable_runtime"]
        first.runtime.start_stage("a", self.at)
        self.assertEqual(first.persist(self.at)["action"], "saved")
        second.runtime.start_stage("a", self.at)
        self.assertEqual(second.persist(self.at)["action"], "conflict")

    def test_invalid_snapshot_rejected_on_restore(self):
        self.store.create("exec-1", "wf-1", {"unexpected": True}, "ready", self.at)
        self.assertEqual(DurableWorkflowRuntime.restore(self.store, "exec-1")["reason"], "snapshot_schema_invalid")

    def test_duplicate_create_returns_structured_failure(self):
        runtime = WorkflowExecutionRuntime(["a"])
        DurableWorkflowRuntime.create(self.store, "exec-1", "wf-1", runtime, self.at)
        self.assertEqual(DurableWorkflowRuntime.create(self.store, "exec-1", "wf-1", runtime, self.at)["reason"], "execution_id_duplicate")


if __name__ == "__main__":
    unittest.main()
