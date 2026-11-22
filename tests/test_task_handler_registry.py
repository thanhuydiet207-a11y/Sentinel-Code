import unittest

from sentinel_core.task_handler_registry import TaskHandlerRegistry


class TaskHandlerRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = TaskHandlerRegistry()
        self.handler = lambda payload: payload

    def test_register_and_resolve_handler(self):
        result = self.registry.register("scan.repo", self.handler, "2.1")
        self.assertEqual(result["action"], "registered")
        resolved = self.registry.resolve("scan.repo", "2.1")
        self.assertEqual(resolved["action"], "resolved")
        self.assertIs(resolved["handler"], self.handler)

    def test_duplicate_registration_fails_closed(self):
        self.registry.register("scan.repo", self.handler)
        self.assertEqual(self.registry.register("scan.repo", self.handler)["reason"], "handler_duplicate")

    def test_invalid_name_handler_and_version_rejected(self):
        self.assertEqual(self.registry.register("../scan", self.handler)["reason"], "handler_name_invalid")
        self.assertEqual(self.registry.register("scan", None)["reason"], "handler_not_callable")
        self.assertEqual(self.registry.register("scan", self.handler, "bad version")["reason"], "handler_version_invalid")

    def test_resolve_unknown_and_version_mismatch(self):
        self.assertEqual(self.registry.resolve("missing")["action"], "not_found")
        self.registry.register("scan", self.handler, "1")
        self.assertEqual(self.registry.resolve("scan", "2")["action"], "version_mismatch")

    def test_input_validator(self):
        self.registry.register("scan", self.handler, input_validator=lambda data: isinstance(data, dict) and "path" in data)
        self.assertEqual(self.registry.validate_input("scan", {"path": "."})["action"], "valid")
        self.assertEqual(self.registry.validate_input("scan", {})["reason"], "input_invalid")

    def test_validator_exception_is_fail_closed(self):
        def broken(_):
            raise RuntimeError("validator failure")
        self.registry.register("scan", self.handler, input_validator=broken)
        self.assertEqual(self.registry.validate_input("scan", {})["reason"], "input_validator_error")

    def test_list_and_unregister(self):
        self.registry.register("z.handler", self.handler, "1")
        self.registry.register("a.handler", self.handler, "2", lambda _: True)
        listing = self.registry.list_handlers()
        self.assertEqual([item["name"] for item in listing["handlers"]], ["a.handler", "z.handler"])
        self.assertTrue(listing["handlers"][0]["has_input_validator"])
        self.assertEqual(self.registry.unregister("a.handler", "2")["action"], "unregistered")
        self.assertEqual(self.registry.resolve("a.handler")["action"], "not_found")


if __name__ == "__main__":
    unittest.main()
