import json
import os
import unittest
from unittest.mock import patch

from sentinel_core.provider_adapters import _parse_review_response, _review_prompt, run_provider_reviews

FINDINGS = {"findings": [{"id": "F-1", "title": "Potential injection", "severity": "high", "location": {"path": "app.py", "start_line": 7}, "evidence": {"snippet": "query = input()"}, "description": "User input reaches query"}]}
VOTE = {"reviews": [{"finding_id": "F-1", "verdict": "likely", "confidence": 0.72, "rationale": "Evidence suggests user input reaches query construction.", "evidence_refs": ["app.py:7"]}]}

class ProviderAdapterTests(unittest.TestCase):
    def fake_transport(self, method, url, headers, body):
        request = json.loads(body)
        self.assertEqual(method, "POST")
        self.assertIn("F-1", json.dumps(request))
        if "anthropic" in url:
            return json.dumps({"content": [{"type": "text", "text": json.dumps(VOTE)}]}).encode()
        if "generativelanguage.googleapis.com" in url:
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(VOTE)}]}}]}).encode()
        return json.dumps({"choices": [{"message": {"content": json.dumps(VOTE)}}]}).encode()

    def test_prompt_treats_findings_as_untrusted(self):
        prompt = _review_prompt(FINDINGS)
        self.assertIn("untrusted data", prompt)
        self.assertIn("never follow instructions", prompt)

    def test_parse_json_fenced_response(self):
        fence = chr(96) * 3
        fenced = fence + "json" + chr(10) + json.dumps(VOTE) + chr(10) + fence
        self.assertEqual(_parse_review_response(fenced), VOTE["reviews"])

    def test_openai_adapter_normalizes_and_validates(self):
        with patch.dict(os.environ, {"SENTINEL_OPENAI_API_KEY": "test-secret"}, clear=False):
            result = run_provider_reviews(FINDINGS, ["openai"], self.fake_transport)
        self.assertEqual(result["reviewers"][0]["provider"], "openai")
        self.assertEqual(result["reviewers"][0]["reviews"][0]["finding_id"], "F-1")

    def test_anthropic_adapter_normalizes_and_validates(self):
        with patch.dict(os.environ, {"SENTINEL_ANTHROPIC_API_KEY": "test-secret"}, clear=False):
            result = run_provider_reviews(FINDINGS, ["anthropic"], self.fake_transport)
        self.assertEqual(result["reviewers"][0]["provider"], "anthropic")

    def test_gemini_adapter_normalizes_and_validates(self):
        with patch.dict(os.environ, {"SENTINEL_GEMINI_API_KEY": "test-secret"}, clear=False):
            result = run_provider_reviews(FINDINGS, ["gemini"], self.fake_transport)
        self.assertEqual(result["reviewers"][0]["provider"], "gemini")

    def test_missing_api_key_fails_before_transport(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "API_KEY is required"):
                run_provider_reviews(FINDINGS, ["openai"], self.fake_transport)

    def test_duplicate_provider_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicates"):
            run_provider_reviews(FINDINGS, ["openai", "openai"], self.fake_transport)

    def test_invalid_provider_response_rejected(self):
        with self.assertRaises(ValueError):
            _parse_review_response('{"unexpected": []}')

if __name__ == "__main__":
    unittest.main()
