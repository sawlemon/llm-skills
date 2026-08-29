"""Trace recording and recall-trace parsing.

``TraceRecorder`` appends metadata-only JSONL events (hashes, counts,
durations — never prompt or memory text). ``parse_recall_trace`` turns a
Hindsight ``trace=true`` response into a flat phase table for scoring.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .safety import redact_obj


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class TraceRecorder:
    def __init__(self, path: Path | None, run_id: str):
        self.path = path
        self.run_id = run_id
        self._events: list[dict] = []

    def add(self, suite: str, case: str, phase: str, **fields) -> None:
        event = {"ts": utc_now(), "run_id": self.run_id, "suite": suite, "case": case, "phase": phase}
        event.update(redact_obj(fields))
        self._events.append(event)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @property
    def events(self) -> list[dict]:
        return list(self._events)


def parse_recall_trace(trace: dict) -> dict:
    """Flatten a Hindsight search trace into phase timings and counts."""
    summary = trace.get("summary", {})
    phases = {
        p["phase_name"]: round(p["duration_seconds"], 6)
        for p in summary.get("phase_metrics", [])
        if not p.get("details", {}).get("diagnostic")
    }
    diagnostics = {
        p["phase_name"]: round(p["duration_seconds"], 6)
        for p in summary.get("phase_metrics", [])
        if p.get("details", {}).get("diagnostic")
    }
    retrieval_details = next(
        (p.get("details", {}) for p in summary.get("phase_metrics", []) if p["phase_name"] == "parallel_retrieval"),
        {},
    )
    return {
        "phases": phases,
        "diagnostics": diagnostics,
        "total_duration_seconds": summary.get("total_duration_seconds"),
        "results_returned": summary.get("results_returned"),
        "budget_used": summary.get("budget_used"),
        "counts": {
            "semantic": retrieval_details.get("semantic_count"),
            "bm25": retrieval_details.get("bm25_count"),
            "graph": retrieval_details.get("graph_count"),
            "temporal": retrieval_details.get("temporal_count"),
        },
    }
