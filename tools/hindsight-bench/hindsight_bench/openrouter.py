"""OpenRouter client for chat completions and reranking.

Credentials come only from the environment (``OPENROUTER_API_KEY``) and are
attached per request; they are never written to config, logs, or results.
"""

from __future__ import annotations

from .http import get_json, post_json
from .safety import require_env_key

CHAT_PATH = "/chat/completions"
RERANK_PATH = "/rerank"
MODELS_PATH = "/models"


class OpenRouterClient:
    def __init__(self, base_url: str, guard, timeout: float = 120.0, transport=None, api_key: str | None = None):
        self.base = base_url.rstrip("/")
        self.guard = guard
        self.timeout = timeout
        self.transport = transport
        self._api_key = api_key  # tests may inject; production resolves lazily

    def _headers(self) -> dict[str, str]:
        key = self._api_key if self._api_key is not None else require_env_key("OPENROUTER_API_KEY")
        return {
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://github.com/sawlemon/llm-skills",
            "X-Title": "llm-skills hindsight-bench",
        }

    def chat(self, payload: dict) -> dict:
        result = post_json(
            f"{self.base}{CHAT_PATH}",
            payload,
            headers=self._headers(),
            timeout=self.timeout,
            guard=self.guard,
            transport=self.transport,
        )
        return _unwrap(result)

    def rerank(self, model: str, query: str, documents: list[str], top_n: int | None = None) -> dict:
        payload = {"model": model, "query": query, "documents": documents, "top_n": top_n or len(documents)}
        result = post_json(
            f"{self.base}{RERANK_PATH}",
            payload,
            headers=self._headers(),
            timeout=self.timeout,
            guard=self.guard,
            transport=self.transport,
        )
        return _unwrap(result)

    def catalog(self) -> dict:
        result = get_json(f"{self.base}{MODELS_PATH}", headers=self._headers(), timeout=self.timeout,
                          guard=self.guard, transport=self.transport)
        return _unwrap(result)


def _unwrap(result):
    """Normalize an HttpResult into {ok, status, body, error, elapsed_s}."""
    body = result.body if result.ok else None
    error = None if result.ok else (result.error or json_dumps(result.body))
    return {
        "ok": result.ok,
        "status": result.status,
        "body": body,
        "error": error,
        "elapsed_s": result.elapsed_s,
    }


def json_dumps(value) -> str:
    import json

    try:
        return json.dumps(value)[:2000]
    except (TypeError, ValueError):
        return str(value)[:2000]
