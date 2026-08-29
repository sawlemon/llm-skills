"""Benchmark configuration: CLI overrides env, env overrides defaults.

Secrets never live here — they are read from the environment at call time
(see :mod:`hindsight_bench.safety.require_env_key`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent
BENCH_ROOT = PKG_ROOT.parent

RECALL_QUERY_TOKEN_LIMIT = 500  # Hindsight rejects recall queries above this


@dataclass
class BenchConfig:
    mode: str = "offline"  # offline | live
    suites: tuple[str, ...] = ("all",)
    runs: int = 3
    concurrency: int = 8
    timeout: float = 180.0
    seed: int = 20260830
    candidate_caps: tuple[int, ...] = (50, 100, 200, 300)
    context_limit: int | None = None  # None -> per-model value from goldens
    reserved_output_tokens: int = 3000
    hindsight_url: str = ""
    hindsight_bank: str = ""
    openrouter_base: str = "https://openrouter.ai/api/v1"
    models: tuple[str, ...] = ()  # empty -> suite defaults
    out_dir: Path | None = None
    include_text: bool = False
    allow_network: bool = False
    allow_persistence: bool = False
    dry_run: bool = False
    yes: bool = False
    json_output: bool = False
    hindsight_dry_run_extract: bool = False  # route retain calls via server dry-run
    max_journal_chars: int = 180_000

    @property
    def guard(self):
        from .safety import SafetyGuard

        return SafetyGuard(self.allow_network, self.allow_persistence, self.dry_run, self.hindsight_bank)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"HINDSIGHT_BENCH_{name}", os.environ.get(name, default)).strip()


def from_args(args) -> BenchConfig:
    mode = getattr(args, "mode", None) or _env("MODE", "offline")
    if mode not in ("offline", "live"):
        raise SystemExit(f"invalid mode {mode!r}; use offline or live")
    suites = tuple(getattr(args, "suite", None) or _env("SUITES", "all").split(","))
    caps = getattr(args, "candidate_caps", None)
    if caps:
        caps = tuple(int(x) for x in str(caps).split(",") if x.strip())
    else:
        env_caps = _env("CANDIDATE_CAPS")
        caps = tuple(int(x) for x in env_caps.split(",") if x.strip()) if env_caps else (50, 100, 200, 300)
    out_dir = getattr(args, "out_dir", None) or _env("OUT") or None
    hindsight_url = getattr(args, "hindsight_url", None) or _env("HINDSIGHT_API_URL", _env("HINDSIGHT_URL"))
    hindsight_bank = getattr(args, "bank", None) or _env("BANK", "")
    models = getattr(args, "models", None) or ()
    if getattr(args, "model", None):
        models = (args.model,)
    if not models:
        env_models = _env("MODEL")
        models = tuple(m for m in env_models.split(",") if m.strip()) if env_models else ()
    return BenchConfig(
        mode=mode,
        suites=suites,
        runs=int(getattr(args, "runs", 0) or _env("RUNS", "3")),
        concurrency=int(_env("CONCURRENCY", "8")),
        timeout=float(_env("TIMEOUT", "180")),
        seed=int(_env("SEED", str(getattr(args, "seed", 20260830)))),
        candidate_caps=caps,
        context_limit=getattr(args, "context_limit", None),
        hindsight_url=hindsight_url,
        hindsight_bank=hindsight_bank,
        openrouter_base=_env("OPENROUTER_BASE", "https://openrouter.ai/api/v1"),
        models=models,
        out_dir=Path(out_dir) if out_dir else None,
        include_text=bool(getattr(args, "include_text", False)),
        allow_network=bool(getattr(args, "allow_network", False)) or _env("ALLOW_NETWORK") == "1",
        allow_persistence=bool(getattr(args, "allow_persistence", False)) or _env("ALLOW_PERSISTENCE") == "1",
        dry_run=bool(getattr(args, "dry_run", False)),
        yes=bool(getattr(args, "yes", False)),
        json_output=bool(getattr(args, "json", False)),
        hindsight_dry_run_extract=bool(getattr(args, "hindsight_dry_run", False)),
        max_journal_chars=int(_env("MAX_JOURNAL_CHARS", str(getattr(args, "max_journal_chars", 180_000)))),
    )


def validate(config: BenchConfig) -> list[str]:
    problems: list[str] = []
    if config.mode == "live" and not config.allow_network:
        problems.append("live mode requires --allow-network")
    if config.dry_run and config.allow_persistence:
        problems.append("--dry-run and --allow-persistence are mutually exclusive")
    if config.mode == "offline" and (config.allow_network or config.allow_persistence):
        problems.append("offline mode must not enable network or persistence gates")
    if config.include_text and config.mode == "live":
        problems.append("--include-text is restricted to offline/synthetic data")
    if config.runs < 1 or config.runs > 10:
        problems.append("--runs must be between 1 and 10")
    if config.concurrency < 1 or config.concurrency > 16:
        problems.append("--concurrency must be between 1 and 16")
    for cap in config.candidate_caps:
        if cap < 1 or cap > 300:
            problems.append(f"candidate cap {cap} outside 1..300")
    if not config.suites:
        problems.append("no suites selected")
    return problems
