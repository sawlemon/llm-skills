"""Retain fact-extraction contract: schema, request builder, response parser.

The request shape and JSON schema mirror what Hindsight v0.9.2 sends to its
LLM provider (verified from live ``retain_extract_facts`` telemetry): a
system prompt carrying the extraction instructions plus the embedded
``FactExtractionResponse`` JSON schema, and a user message with the text.
"""

from __future__ import annotations

import json
from typing import Any

FACT_PROPERTIES: dict[str, Any] = {
    "what": {"type": "string"},
    "when": {"type": "string"},
    "where": {"type": "string"},
    "who": {"type": "string"},
    "why": {"type": "string"},
    "fact_kind": {"type": "string"},
    "occurred_start": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "occurred_end": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    "fact_type": {"type": "string", "enum": ["world", "assistant"]},
    "entities": {"type": "array", "items": {"type": "string"}},
    "causal_relations": {"anyOf": [{"type": "array", "items": {"type": "object"}}, {"type": "null"}]},
}

EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": FACT_PROPERTIES,
                "required": list(FACT_PROPERTIES),
                "additionalProperties": False,
            },
        }
    },
    "required": ["facts"],
    "additionalProperties": False,
}


class ExtractionParseError(ValueError):
    pass


def build_chat_request(
    system_prompt: str,
    content: str,
    model: str,
    reasoning: dict | None,
    timestamp: str,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> dict:
    """Build an OpenRouter chat-completions payload for fact extraction."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"[Conversation timestamp: {timestamp}]\n{content}"},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "FactExtractionResponse",
                "strict": True,
                "schema": EXTRACTION_SCHEMA,
            },
        },
        "provider": {"require_parameters": True},
    }
    if reasoning is not None:
        payload["reasoning"] = reasoning
    return payload


def parse_extraction(body: dict) -> list[dict]:
    """Extract the normalized fact list from a chat-completions response."""
    try:
        choice = body["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ExtractionParseError(f"malformed chat response: {error}") from error
    if isinstance(content, dict):
        data = content
    else:
        try:
            data = json.loads(content)
        except ValueError as error:
            raise ExtractionParseError(f"model returned non-JSON content: {error}") from error
    facts = data.get("facts")
    if not isinstance(facts, list):
        raise ExtractionParseError("extraction JSON lacks a 'facts' array")
    return [fact for fact in facts if isinstance(fact, dict) and fact.get("what")]


def fact_text(facts: list[dict]) -> str:
    """Joined, lowercased fact text — the corpus criteria are scored against."""
    return "\n".join(str(f.get("what", "")) for f in facts).lower()
