"""Command-line interface: list, validate, run, score."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import SUITES, __version__
from .config import BenchConfig, from_args
from .runner import aggregate_cases, run_bench
from .safety import redact_obj


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hindsight_bench",
        description="Reproducible Hindsight retain/recall/reranker benchmarks (offline by default).",
    )
    parser.add_argument("--version", action="version", version=f"hindsight-bench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list available suites")
    sub.add_parser("validate", help="validate fixtures, goldens, and configs")

    run = sub.add_parser("run", help="run one or more suites")
    _add_run_options(run)

    score = sub.add_parser("score", help="recompute aggregates from a run.json")
    score.add_argument("--results", required=True, help="path to a run.json produced by `run`")
    score.add_argument("--json", action="store_true", help="emit JSON instead of text")
    return parser


def _add_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--mode", choices=("offline", "live"), help="default: offline (or HINDSIGHT_BENCH_MODE)")
    parser.add_argument("--suite", action="append", help="suite name; repeatable; default: all")
    parser.add_argument("--model", action="append", help="restrict to model slug/label; repeatable")
    parser.add_argument("--hindsight-url", help="Hindsight base URL, e.g. http://127.0.0.1:8888")
    parser.add_argument("--bank", help="Hindsight bank id (reads: any; writes: bench_ only)")
    parser.add_argument("--runs", type=int, help="repetitions per case (1-10, default 3)")
    parser.add_argument("--concurrency", type=int, help="max parallel extraction calls (1-16)")
    parser.add_argument("--timeout", type=float, help="per-request timeout seconds")
    parser.add_argument("--seed", type=int, default=20260830, help="recorded seed for the run")
    parser.add_argument("--candidate-caps", help="comma-separated caps, e.g. 50,100,200,300")
    parser.add_argument("--context-limit", type=int, help="override model context tokens for probing")
    parser.add_argument("--max-journal-chars", type=int, default=180_000, help="synthetic journal size")
    parser.add_argument("--out-dir", help="write run artifacts (run.json/manifest/trace/report) under this dir")
    parser.add_argument("--allow-network", action="store_true", help="permit outbound HTTP (required for live)")
    parser.add_argument("--allow-persistence", action="store_true", help="permit Hindsight writes (bench_ banks only)")
    parser.add_argument("--dry-run", action="store_true", help="block all mutating Hindsight requests")
    parser.add_argument("--hindsight-dry-run", action="store_true",
                        help="route retain extraction through the server's dry-run-extract (no persistence)")
    parser.add_argument("--include-text", action="store_true",
                        help="include raw text in output (offline synthetic data only)")
    parser.add_argument("--yes", action="store_true", help="confirm destructive/live operations")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON to stdout")


def cmd_list(_args) -> int:
    print("available suites:")
    for suite in SUITES:
        print(f"  {suite}")
    return 0


def cmd_validate(_args) -> int:
    from .validate import run_validation

    problems = run_validation()
    if problems:
        print("validation FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("validation OK: fixtures, goldens, configs, and prompt resolve cleanly")
    return 0


def cmd_run(args) -> int:
    config: BenchConfig = from_args(args)
    run = run_bench(config)
    payload = redact_obj(run) if not config.include_text else run
    if config.json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        _print_run_text(run)
    failed = run["aggregate"]["by_status"].get("fail", 0) + run["aggregate"]["by_status"].get("error", 0)
    return 0 if failed == 0 else 1


def _print_run_text(run: dict) -> None:
    from .report import render_summary_text

    print(render_summary_text(run))


def cmd_score(args) -> int:
    path = Path(args.results)
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return 2
    run = json.loads(path.read_text())
    aggregate = aggregate_cases(run.get("cases", []))
    if args.json:
        print(json.dumps(aggregate, indent=2))
    else:
        print(f"recomputed aggregate for {run.get('run_id', path.name)}: {json.dumps(aggregate)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"list": cmd_list, "validate": cmd_validate, "run": cmd_run, "score": cmd_score}
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
