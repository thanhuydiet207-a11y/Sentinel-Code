import unittest

from sentinel_core.workflow_runtime import WorkflowExecutionRuntime


class WorkflowExecutionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.runtime = WorkflowExecutionRuntime(["a", "b", "c"], {"b": ["a"], "c": ["a"]}, max_parallelism=2)
        self.now = "2026-01-01T00:00:00+00:00"

    def test_starts_only_ready_stages_and_respects_parallelism(self):
        self.assertEqual(self.runtime.start_stage("b", self.now)["reason"], "stage_not_ready")
        self.assertEqual(self.runtime.start_stage("a", self.now)["action"], "started")
        self.assertEqual(self.runtime.plan()["ready_stages"], [])
        self.assertEqual(self.runtime.plan()["available_slots"], 1)

    def test_completion_unlocks_dependent_stages(self):
        self.runtime.start_stage("a", self.now)
        result = self.runtime.finish_stage("a", "completed", "2026-01-01T00:00:01+00:00")
        self.assertEqual(result["action"], "completed")
        self.assertEqual(set(self.runtime.plan()["ready_stages"]), {"b", "c"})

    def test_failure_blocks_descendants(self):
        self.runtime.start_stage("a", self.now)
        self.runtime.finish_stage("a", "failed", "2026-01-01T00:00:01+00:00", "boom")
        plan = self.runtime.plan()
        self.assertEqual(plan["blocked_stages"][0]["stage"], "b")
        self.assertEqual(plan["blocked_stages"][1]["stage"], "c")

    def test_timeout_marks_running_stage_failed(self):
        self.runtime.start_stage("a", self.now, timeout_seconds=2)
        result = self.runtime.expire("2026-01-01T00:00:02+00:00")
        self.assertEqual(result["stages"], ["a"])
        self.assertEqual(self.runtime.stage_states["a"], "failed")

    def test_cancel_is_terminal_and_idempotent(self):
        self.runtime.start_stage("a", self.now)
        result = self.runtime.cancel("2026-01-01T00:00:01+00:00", "user request")
        self.assertEqual(result["action"], "cancelled")
        self.assertEqual(self.runtime.cancel("2026-01-01T00:00:02+00:00")["action"], "already_cancelled")
        self.assertEqual(self.runtime.start_stage("b", self.now)["reason"], "workflow_cancelled")

    def test_finish_requires_running_stage(self):
        self.assertEqual(self.runtime.finish_stage("a", "completed", self.now)["reason"], "stage_not_running")

    def test_invalid_time_is_rejected(self):
        self.assertEqual(self.runtime.start_stage("a", "not-a-time")["reason"], "timestamp_invalid")

    def test_invalid_graph_fails_closed(self):
        runtime = WorkflowExecutionRuntime(["a", "b"], {"a": ["b"], "b": ["a"]})
        self.assertEqual(runtime.snapshot()["action"], "blocked")
        self.assertEqual(runtime.start_stage("a", self.now)["reason"], "workflow_invalid")

    def test_event_sequence_is_monotonic(self):
        self.runtime.start_stage("a", self.now)
        self.runtime.finish_stage("a", "completed", "2026-01-01T00:00:01+00:00")
        self.assertEqual([event["sequence"] for event in self.runtime.events], [1, 2])


if __name__ == "__main__":
    unittest.main()
