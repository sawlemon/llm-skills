"""Markdown rendering of benchmark runs."""

from __future__ import annotations

import json


def render_run_markdown(run: dict) -> str:
    lines = [f"# hindsight-bench run {run['run_id']}", ""]
    lines.append(f"- mode: `{run['mode']}` | seed: {run['seed']} | finished: {run['finished_at']}")
    lines.append(f"- suites: {', '.join(run['suites'])}")
    lines.append(f"- aggregate: `{json.dumps(run['aggregate'])}`")
    lines.append("")
    lines.append("| suite | case | status | metrics |")
    lines.append("|---|---|---|---|")
    for case in run["cases"]:
        metrics = json.dumps(case["metrics"], ensure_ascii=False)
        if len(metrics) > 160:
            metrics = metrics[:157] + "..."
        error = f" — {case['error']}" if case.get("error") else ""
        lines.append(f"| {case['suite']} | {case['case_id']} | {case['status']} | `{metrics}`{error} |")
    return "\n".join(lines) + "\n"


def render_summary_text(run: dict) -> str:
    lines = [f"run {run['run_id']} mode={run['mode']} suites={','.join(run['suites'])}"]
    for case in run["cases"]:
        marker = {"pass": "ok  ", "fail": "FAIL", "skip": "skip", "error": "ERR "}.get(case["status"], "??  ")
        detail = case.get("error") or ""
        lines.append(f"  [{marker}] {case['suite']}/{case['case_id']} {detail}")
    lines.append(f"aggregate: {json.dumps(run['aggregate'])}")
    if run.get("artifact_dir"):
        lines.append(f"artifacts: {run['artifact_dir']}")
    return "\n".join(lines)
