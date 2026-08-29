"""Fake transports/clients for offline tests: deterministic, recording, no network."""

from __future__ import annotations

import json

from hindsight_bench.extraction import EXTRACTION_SCHEMA


class FakeHttpResult:
    def __init__(self, ok, status, body, error, elapsed_s):
        self.ok = ok
        self.status = status
        self.body = body
        self.error = error
        self.elapsed_s = elapsed_s


def _chat_body(facts):
    return {"choices": [{"message": {"content": json.dumps({"facts": facts})}}], "usage": {}, "provider": "Fake"}


class FakeOpenRouter:
    """Records every call; returns canned responses keyed by model."""

    def __init__(self, chat_responses: dict[str, list] | None = None, rerank_order: list[int] | None = None):
        self.calls = []
        self.chat_responses = chat_responses or {}
        self.rerank_order = rerank_order or []

    def post_json(self, url, payload, headers=None, timeout=120.0):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        if url.endswith("/chat/completions"):
            model = payload.get("model", "")
            queue = self.chat_responses.get(model)
            if queue is None:
                return FakeHttpResult(False, 500, None, "no canned response", 0.01)
            item = queue.pop(0) if len(queue) > 1 else queue[0]
            if isinstance(item, dict) and item.get("error"):
                return FakeHttpResult(False, item.get("status", 400), None, item["error"], 0.01)
            return FakeHttpResult(True, 200, _chat_body(item), None, 0.5)
        if url.endswith("/rerank"):
            results = [
                {"index": index, "relevance_score": 1.0 / (rank + 1)}
                for rank, index in enumerate(self.rerank_order)
            ]
            return FakeHttpResult(
                True, 200, {"results": results, "usage": {"search_units": 3, "cost": 0.002}, "provider": "Fake"}, None, 0.4
            )
        return FakeHttpResult(False, 404, None, "unknown url", 0.0)

    def get_json(self, url, headers=None, timeout=60.0):
        self.calls.append({"url": url, "headers": headers})
        return FakeHttpResult(True, 200, {"data": []}, None, 0.0)


class RecordingHindsightTransport:
    """Records method+path per call; mutable responses for health/recall/dry-run."""

    def __init__(self, recall_trace=None, dry_run_facts=None):
        self.calls = []
        self.recall_trace = recall_trace or {"summary": {"total_duration_seconds": 1.0, "phase_metrics": []}}
        self.dry_run_facts = dry_run_facts or []

    def _record(self, method, url):
        path = url.split("?", 1)[0].split("/v1/", 1)[-1] if "/v1/" in url else url
        self.calls.append((method.upper(), path))

    def post_json(self, url, payload, headers=None, timeout=120.0):
        self._record("POST", url)
        if url.endswith("/memories/recall"):
            return FakeHttpResult(True, 200, {"results": [], "trace": self.recall_trace}, None, 0.3)
        if url.endswith("/memories/dry-run-extract"):
            return FakeHttpResult(
                True,
                200,
                {"facts": [{"text": f, "fact_type": "world", "entities": []} for f in self.dry_run_facts], "usage": {}},
                None,
                0.4,
            )
        if url.rstrip("/").endswith("/memories"):
            return FakeHttpResult(True, 200, {"success": True}, None, 0.1)
        return FakeHttpResult(False, 404, None, "unknown", 0.0)

    def get_json(self, url, headers=None, timeout=60.0):
        self._record("GET", url)
        if url.endswith("/health"):
            return FakeHttpResult(True, 200, {"status": "healthy", "database": "connected"}, None, 0.01)
        return FakeHttpResult(True, 200, {}, None, 0.01)


def corrupted_fact():
    return {"what": "The user owns a blue Model 3", "when": "N/A", "who": "user", "fact_type": "world"}


__all__ = ["FakeOpenRouter", "RecordingHindsightTransport", "EXTRACTION_SCHEMA", "corrupted_fact"]
