"""Structural validation for fixtures, goldens, and run outputs.

Hand-rolled (no jsonschema dependency): raises SchemaError listing every
problem found so ``validate`` can report them in one pass.
"""

from __future__ import annotations

from typing import Any

REQUIRED_RUN_KEYS = ("schema_version", "run_id", "started_at", "mode", "seed", "suites", "cases", "aggregate")
REQUIRED_CASE_KEYS = ("case_id", "suite", "status", "metrics")
CASE_STATUSES = ("pass", "fail", "skip", "error")


class SchemaError(ValueError):
    pass


def validate_run(run: dict[str, Any]) -> list[str]:
    problems = []
    for key in REQUIRED_RUN_KEYS:
        if key not in run:
            problems.append(f"run.json missing key {key!r}")
    for index, case in enumerate(run.get("cases", [])):
        for key in REQUIRED_CASE_KEYS:
            if key not in case:
                problems.append(f"case[{index}] missing key {key!r}")
        status = case.get("status")
        if status not in CASE_STATUSES:
            problems.append(f"case[{index}] invalid status {status!r}")
    for suite in run.get("suites", []):
        if not isinstance(suite, str):
            problems.append(f"suite entry not a string: {suite!r}")
    return problems


def validate_golden_case(case: dict[str, Any], where: str) -> list[str]:
    problems = []
    for key in ("case_id", "required"):
        if key not in case:
            problems.append(f"{where}: golden case missing {key!r}")
    for group in case.get("required", []):
        if "id" not in group or not (group.get("any") or group.get("all")):
            problems.append(f"{where}: required group {group!r} needs 'id' and 'any'/'all' aliases")
    for entry in case.get("forbidden", []):
        if isinstance(entry, str):
            continue
        if not isinstance(entry, dict) or "text" not in entry:
            problems.append(f"{where}: forbidden entry must be a string or {{text, unless}}: {entry!r}")
    return problems
