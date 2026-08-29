"""Hindsight REST client (read-only by default; writes heavily gated).

Endpoints used:
    GET  /health
    POST /v1/default/banks/{bank}/memories/recall          (read)
    POST /v1/default/banks/{bank}/memories/dry-run-extract  (read-only preview)
    GET  /v1/default/banks/{bank}/llm-requests              (read)
    POST /v1/default/banks/{bank}/memories                  (WRITE — gated)

The workspace id is fixed to ``default`` to match a stock Hindsight install;
override via ``HINDSIGHT_BENCH_WORKSPACE`` if yours differs.
"""

from __future__ import annotations

import os

from .http import get_json, post_json


class HindsightClient:
    def __init__(self, base_url: str, guard, bank: str, timeout: float = 120.0, transport=None):
        self.base = base_url.rstrip("/")
        self.guard = guard
        self.bank = bank
        self.timeout = timeout
        self.transport = transport
        self.workspace = os.environ.get("HINDSIGHT_BENCH_WORKSPACE", "default")

    @property
    def bank_base(self) -> str:
        return f"{self.base}/v1/{self.workspace}/banks/{self.bank}"

    def _headers(self) -> dict[str, str]:
        import os

        headers = {"Content-Type": "application/json"}
        token = os.environ.get("HINDSIGHT_API_TOKEN", "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _call(self, method: str, path: str, payload: dict | None = None):
        url = f"{self.base}{path}"
        if method == "GET":
            result = get_json(url, headers=self._headers(), timeout=self.timeout,
                              guard=self.guard, transport=self.transport)
        else:
            # Guard even when a fake transport is injected, so tests exercise it.
            if self.transport is None:
                self.guard.check_hindsight_request(method, path)
            result = post_json(url, payload or {}, headers=self._headers(), timeout=self.timeout,
                               guard=self.guard, transport=self.transport)
        return {
            "ok": result.ok,
            "status": result.status,
            "body": result.body if result.ok else None,
            "error": None if result.ok else (result.error or ""),
            "elapsed_s": result.elapsed_s,
        }

    def health(self) -> dict:
        return self._call("GET", "/health")

    def recall(self, query: str, budget: str = "mid", max_tokens: int = 1500, trace: bool = True) -> dict:
        payload = {"query": query, "budget": budget, "max_tokens": max_tokens, "trace": trace}
        return self._call("POST", f"{self.bank_base}/memories/recall", payload)

    def dry_run_extract(self, content: str, context: str = "", timestamp: str | None = None) -> dict:
        payload: dict = {"content": content, "context": context}
        if timestamp:
            payload["timestamp"] = timestamp
        return self._call("POST", f"{self.bank_base}/memories/dry-run-extract", payload)

    def llm_requests(self, limit: int = 100) -> dict:
        return self._call("GET", f"{self.bank_base}/llm-requests?limit={limit}")

    def retain(self, content: str, context: str = "") -> dict:
        """Persist a memory. Requires persistence gates and a bench_ bank."""
        self.guard.check_hindsight_request("POST", f"{self.bank_base}/memories")
        return self._call("POST", f"{self.bank_base}/memories", {"items": [{"content": content, "context": context}]})
