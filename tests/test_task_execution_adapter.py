import unittest

from sentinel_core.task_handler_registry import TaskHandlerRegistry
from sentinel_core.task_execution_adapter import TaskExecutionAdapter


class TaskExecutionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = TaskHandlerRegistry()
        self.adapter = TaskExecutionAdapter(self.registry)

    def test_invokes_registered_handler_and_normalizes_result(self):
        self.registry.register("echo", lambda payload, context=None: {"payload": payload, "context": context}, "1")
        result = self.adapter.execute({"task_id": "t1", "handler": "echo", "handler_version": "1", "input": {"x": 1}}, {"run": "r"})
        self.assertEqual(result["action"], "completed")
        self.assertEqual(result["result"], {"payload": {"x": 1}, "context": {"run": "r"}})

    def test_unknown_handler_is_blocked(self):
        result = self.adapter.execute({"task_id": "t1", "handler": "missing", "input": {}})
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["reason"], "not_found")

    def test_invalid_input_is_blocked_before_invocation(self):
        calls = []
        self.registry.register("safe", lambda payload, context=None: calls.append(payload), input_validator=lambda payload: False)
        result = self.adapter.execute({"task_id": "t1", "handler": "safe", "input": "unsafe"})
        self.assertEqual(result["reason"], "input_invalid")
        self.assertEqual(calls, [])

    def test_handler_exception_is_normalized(self):
        def handler(_payload, context=None):
            raise ValueError("bad input")
        self.registry.register("broken", handler)
        result = self.adapter.execute({"task_id": "t1", "handler": "broken"})
        self.assertEqual(result["action"], "failed")
        self.assertEqual(result["error_type"], "ValueError")

    def test_invalid_task_and_context_rejected(self):
        self.assertEqual(self.adapter.execute(None)["reason"], "task_invalid")
        self.registry.register("noop", lambda payload, context=None: None)
        self.assertEqual(self.adapter.execute({"task_id": "t1", "handler": "noop"}, "bad")["reason], "context_invalid")

    def test_version_mismatch_blocks(self):
        self.registry.register("v", lambda payload, context=None: payload, "1")
        result = self.adapter.execute({"task_id": "t1", "handler": "v", "handler_version": "2"})
        self.assertEqual(result["action"], "blocked")
        self.assertEqual(result["reason"], "version_mismatch")


if __name__ == "__main__":
    unittest.main()
