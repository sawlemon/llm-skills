"""Extraction request/parsing contract and OpenRouter client wiring."""

import unittest

from hindsight_bench.extraction import (
    EXTRACTION_SCHEMA,
    ExtractionParseError,
    build_chat_request,
    parse_extraction,
)
from hindsight_bench.openrouter import OpenRouterClient
from tests.fakes import FakeOpenRouter


class RequestBuilderTests(unittest.TestCase):
    def test_payload_shape(self):
        payload = build_chat_request("SYS", "content", "openai/gpt-oss-20b", {"effort": "low"}, "2026-08-30")
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("[Conversation timestamp: 2026-08-30]", payload["messages"][1]["content"])
        self.assertEqual(payload["response_format"]["type"], "json_schema")
        self.assertTrue(payload["response_format"]["json_schema"]["strict"])
        self.assertEqual(payload["provider"], {"require_parameters": True})
        self.assertEqual(payload["reasoning"], {"effort": "low"})

    def test_no_reasoning_key_when_none(self):
        payload = build_chat_request("SYS", "content", "m", None, "2026-08-30")
        self.assertNotIn("reasoning", payload)


class ParseTests(unittest.TestCase):
    def test_parse_json_content(self):
        body = {"choices": [{"message": {"content": '{"facts": [{"what": "x", "fact_type": "world"}]}'}}]}
        facts = parse_extraction(body)
        self.assertEqual(facts[0]["what"], "x")

    def test_rejects_malformed(self):
        with self.assertRaises(ExtractionParseError):
            parse_extraction({"choices": []})
        with self.assertRaises(ExtractionParseError):
            parse_extraction({"choices": [{"message": {"content": "not json"}}]})

    def test_schema_strict(self):
        self.assertTrue(EXTRACTION_SCHEMA["additionalProperties"] is False)
        fact_schema = EXTRACTION_SCHEMA["properties"]["facts"]["items"]
        self.assertEqual(fact_schema["additionalProperties"], False)


class ClientTests(unittest.TestCase):
    def test_chat_flow(self):
        fake = FakeOpenRouter(chat_responses={"m": [[{"what": "fact", "fact_type": "world"}]]})
        client = OpenRouterClient("https://example.invalid/api/v1", guard=None, api_key="test-key", transport=fake)
        result = client.chat({"model": "m", "messages": []})
        self.assertTrue(result["ok"])
        facts = parse_extraction(result["body"])
        self.assertEqual(facts[0]["what"], "fact")
        # Authorization header present exactly once, per call.
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer test-key")

    def test_reasoning_mandatory_error_passthrough(self):
        fake = FakeOpenRouter(chat_responses={"m": [{"error": "Reasoning is mandatory for this endpoint.", "status": 400}]})
        client = OpenRouterClient("https://example.invalid/api/v1", guard=None, api_key="k", transport=fake)
        result = client.chat({"model": "m"})
        self.assertFalse(result["ok"])
        self.assertIn("Reasoning is mandatory", result["error"])

    def test_rerank_flow(self):
        fake = FakeOpenRouter(rerank_order=[2, 0, 1])
        client = OpenRouterClient("https://example.invalid/api/v1", guard=None, api_key="k", transport=fake)
        result = client.rerank("cohere/rerank-4-pro", "query", ["a", "b", "c"], top_n=3)
        self.assertTrue(result["ok"])
        self.assertEqual([r["index"] for r in result["body"]["results"]], [2, 0, 1])


if __name__ == "__main__":
    unittest.main()
