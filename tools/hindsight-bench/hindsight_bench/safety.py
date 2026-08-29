"""Safety gates, secret redaction, and bank write restrictions.

Three independent gates protect live runs:

1. ``allow_network``  — any outbound HTTP request.
2. ``allow_persistence`` — Hindsight *write* requests (retain/config changes).
3. ``dry_run`` — blocks every mutating Hindsight request even when
   ``allow_persistence`` is set.

Read-only Hindsight calls (health, recall, ``dry-run-extract``) need only
``allow_network``. Writes additionally require a generated ``bench_<id>`` bank;
personal banks (``default``, ``library``, ``agents``, ...) are always rejected
for writes. Secrets are only ever read from the process environment and are
redacted from any serialized output.
"""

from __future__ import annotations

import re

PERSONAL_BANKS = frozenset({"default", "library", "agents", "career", "crowdstrike"})
BANK_PREFIX_ALLOWED = "bench_"

_REDACTIONS = (
    (re.compile(r"sk-[A-Za-z0-9_-]{6,}"), "sk-<REDACTED>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{6,}"), "Bearer <REDACTED>"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)\S+"), r"\1<REDACTED>"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)['\"]?[A-Za-z0-9._-]{8,}"), r"\1<REDACTED>"),
)

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Hindsight performs these reads via POST; they are never writes.
READ_BY_POST_SUFFIXES = (
    "/memories/recall",
    "/memories/dry-run-extract",
    "/memories/list",
)


class SafetyError(RuntimeError):
    """A requested operation violates a safety gate."""


def redact(text: str) -> str:
    """Remove credential-looking material from free text."""
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


def redact_obj(obj):
    """Recursively redact every string inside JSON-like data."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {key: redact_obj(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    return obj


class SafetyGuard:
    """Gatekeeper for network and Hindsight mutations."""

    def __init__(self, allow_network: bool, allow_persistence: bool, dry_run: bool, bank: str = ""):
        self.allow_network = allow_network
        self.allow_persistence = allow_persistence
        self.dry_run = dry_run
        self.bank = bank

    # -- network -----------------------------------------------------------
    def check_network(self, url: str) -> None:
        if not self.allow_network:
            raise SafetyError(
                f"network access disabled (mode offline); pass --allow-network to reach {url.split('/')[2] if '://' in url else url}"
            )

    # -- Hindsight ---------------------------------------------------------
    def check_hindsight_request(self, method: str, path: str) -> None:
        if method.upper() not in MUTATING_METHODS:
            return
        if any(path.rstrip("/").endswith(suffix) for suffix in READ_BY_POST_SUFFIXES):
            return  # read-by-POST endpoint, never a write
        if self.dry_run:
            raise SafetyError(f"dry-run blocks mutating request {method} {path}")
        if not self.allow_persistence:
            raise SafetyError(f"persistence disabled; refusing {method} {path} (pass --allow-persistence)")
        if path.rstrip("/").endswith("/memories") and method.upper() == "POST":
            self.check_write_bank()

    def check_write_bank(self) -> None:
        bank = self.bank
        if bank in PERSONAL_BANKS:
            raise SafetyError(f"refusing to write personal bank {bank!r}")
        if not bank.startswith(BANK_PREFIX_ALLOWED):
            raise SafetyError(
                f"writes require a generated benchmark bank ({BANK_PREFIX_ALLOWED}<run_id>), got {bank!r}"
            )

    def check_live_ready(self) -> None:
        if self.dry_run and self.allow_persistence:
            raise SafetyError("--dry-run and --allow-persistence are mutually exclusive")


def require_env_key(name: str) -> str:
    """Read a secret from the environment only; never log or persist it."""
    import os

    value = os.environ.get(name, "").strip()
    if not value:
        raise SafetyError(
            f"environment variable {name} is not set; configure credentials outside the repo (export {name}=...)"
        )
    return value
