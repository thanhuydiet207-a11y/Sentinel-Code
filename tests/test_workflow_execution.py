import unittest

from sentinel_core.workflow_execution import build_execution_plan


class WorkflowExecutionPlannerTests(unittest.TestCase):
    def test_independent_stages_are_parallelized_with_limit(self):
        result = build_execution_plan(["a", "b", "c", "d"], max_parallelism=2)
        self.assertEqual(result["execution_waves"], [["a", "b"], ["c", "d"]])

    def test_dependencies_gate_stages(self):
        result = build_execution_plan(["scan", "review", "report"], {"review": ["scan"], "report": ["review"]})
        self.assertEqual(result["ready_stages"], ["scan"])
        self.assertEqual(result["waiting_stages"], [
            {"stage": "review", "dependencies": ["scan"]},
            {"stage": "report", "dependencies": ["review"]},
        ])

    def test_completed_dependency_unlocks_next_stage(self):
        result = build_execution_plan(["scan", "review"], {"review": ["scan"]}, [{"stage": "scan", "status": "completed"}])
        self.assertEqual(result["ready_stages"], ["review"])

    def test_failed_dependency_blocks_descendants(self):
        result = build_execution_plan(["a", "b", "c"], {"b": ["a"], "c": ["b"]}, [{"stage": "a", "status": "failed"}])
        self.assertEqual(result["blocked_stages"][0]["stage"], "a")
        self.assertEqual(result["blocked_stages"][1]["stage"], "b")
        self.assertEqual(result["waiting_stages"], [])
        self.assertEqual(result["blocked_stages"][2], {"stage": "c", "reason": "dependency_failed", "dependencies": ["b"]})

    def test_retry_marker_makes_stage_ready_when_dependencies_met(self):
        result = build_execution_plan(["a", "b"], {"b": ["a"]}, [{"stage": "a", "status": "completed"}, {"stage": "b", "status": "failed"}, {"stage": "b", "status": "retry"}])
        self.assertEqual(result["ready_stages"], ["b"])

    def test_cycle_rejected(self):
        result = build_execution_plan(["a", "b"], {"a": ["b"], "b": ["a"]})
        self.assertEqual(result["reason"], "workflow_graph_invalid")
        self.assertIn("dependency_cycle", result["errors"])

    def test_unknown_dependency_rejected(self):
        result = build_execution_plan(["a"], {"a": ["missing"]})
        self.assertEqual(result["action"], "blocked")

    def test_duplicate_dependency_rejected(self):
        result = build_execution_plan(["a", "b"], {"b": ["a", "a"]})
        self.assertEqual(result["action"], "blocked")

    def test_invalid_parallelism_rejected(self):
        for value in (0, -1, True, 1.5):
            self.assertEqual(build_execution_plan(["a"], max_parallelism=value)["reason"], "parallelism_invalid")

    def test_terminal_workflow_detected(self):
        result = build_execution_plan(["a", "b"], checkpoints=[{"stage": "a", "status": "completed"}, {"stage": "b", "status": "skipped"}])
        self.assertEqual(result["action"], "completed")
        self.assertEqual(result["remaining_stages"], [])


if __name__ == "__main__":
    unittest.main()
