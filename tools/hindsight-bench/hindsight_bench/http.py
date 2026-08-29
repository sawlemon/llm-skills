"""HTTP transport: urllib POST/GET with injectable fakes for tests."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from .safety import SafetyGuard, redact


class HttpResult:
    def __init__(self, ok: bool, status: int, body: Any, error: str | None, elapsed_s: float):
        self.ok = ok
        self.status = status
        self.body = body
        self.error = error
        self.elapsed_s = elapsed_s


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
    guard: SafetyGuard | None = None,
    transport=None,
) -> HttpResult:
    """POST a JSON document and return a normalized result.

    ``transport`` allows tests to inject a fake; production callers omit it.
    Error bodies are redacted before being stored or surfaced.
    """
    if transport is not None:
        return transport.post_json(url, payload, headers, timeout)
    if guard is not None:
        guard.check_network(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
        return HttpResult(True, response.status, body, None, time.monotonic() - started)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw[:2000]
        return HttpResult(False, error.code, body, redact(raw)[:2000], time.monotonic() - started)
    except Exception as error:  # transport-level failure (timeout, DNS, ...)
        return HttpResult(False, 0, None, redact(repr(error)), time.monotonic() - started)


def get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    guard: SafetyGuard | None = None,
    transport=None,
) -> HttpResult:
    if transport is not None:
        return transport.get_json(url, headers, timeout)
    if guard is not None:
        guard.check_network(url)
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
        return HttpResult(True, response.status, body, None, time.monotonic() - started)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        return HttpResult(False, error.code, None, redact(raw)[:2000], time.monotonic() - started)
    except Exception as error:
        return HttpResult(False, 0, None, redact(repr(error)), time.monotonic() - started)
