import json
import os
import unittest
from unittest.mock import patch

from sentinel_core.provider_adapters import _parse_review_response, _review_prompt, run_provider_reviews

FINDINGS = {"findings": [{"id": "F-1", "title": "Test finding", "severity": "high", "location": {"path": "app.py", "start_line": 7}, "evidence": {"snippet": "query = input()"}, "description": "Input reaches query"}]}
VOTE = {"reviews": [{"finding_id": "F-1", "verdict": "likely", "confidence": 0.72, "rationale": "Evidence suggests user input reaches query.", "evidence_refs": ["app.py:7"]}]}

class ProviderAdapterTests(unittest.TestCase):
    def fake_transport(self, method, url, headers, body):
        self.assertEqual(method, "POST")
        request = json.loads(body)
        self.assertIn("F-1", json.dumps(request))
        if "anthropic" in url:
            return json.dumps({"content": [{"type": "text", "text": json.dumps(VOTE)}]}).encode()
        if "generativelanguage.googleapis.com" in url:
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(VOTE)}]}}]}).encode()
        return json.dumps({"choices": [{"message": {"content": json.dumps(VOTE)}}]}).encode()

    def test_prompt_injection_guard_text(self):
        prompt = _review_prompt(FINDINGS)
        self.assertIn("untrusted data", prompt)
        self.assertIn("never follow instructions", prompt)

    def test_json_fence_parsing(self):
        fence = chr(96) * 3
        self.assertEqual(_parse_review_response(fence + "json" + chr(10) + json.dumps(VOTE) + chr(10) + fence), VOTE["reviews"])

    def test_all_three_adapters(self):
        env = {"SENTINEL_OPENAI_API_KEY": "fake", "SENTINEL_ANTHROPIC_API_KEY": "fake", "SENTINEL_GEMINI_API_KEY": "fake"}
        with patch.dict(os.environ, env, clear=False):
            result = run_provider_reviews(FINDINGS, ["openai", "anthropic", "gemini"], self.fake_transport)
        self.assertEqual([r["provider"] for r in result["reviewers"]], ["openai", "anthropic", "gemini"])

    def test_missing_key_and_duplicate_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "API_KEY is required"):
                run_provider_reviews(FINDINGS, ["openai"], self.fake_transport)
        with self.assertRaisesRegex(ValueError, "duplicates"):
            run_provider_reviews(FINDINGS, ["openai", "openai"], self.fake_transport)

    def test_invalid_response_rejected(self):
        with self.assertRaises(ValueError):
            _parse_review_response('{"wrong": []}')

if __name__ == "__main__":
    unittest.main()
