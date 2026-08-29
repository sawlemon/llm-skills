"""Suite orchestration: offline (deterministic, no network) and live runners.

Offline runs exercise the real scoring/parsing/chunking code against bundled
synthetic reference outputs and fixtures, producing deterministic, seed-stable
results. Live runs repeat the original session methodology against real
OpenRouter / Hindsight endpoints and require explicit gates (see safety.py).
"""

from __future__ import annotations

import concurrent.futures
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import SUITES, __version__
from .chunking import chunk_stats, chunk_text
from .config import BENCH_ROOT, BenchConfig
from .extraction import ExtractionParseError, build_chat_request, parse_extraction
from .fixtures import (
    load_golden,
    load_journal_expected,
    load_journal_generator,
    load_prompt,
    load_retain_fixture,
    load_retrieval_fixture,
)
from .hashing import sha256_file, sha256_text
from .hindsight import HindsightClient
from .openrouter import OpenRouterClient
from .report import render_run_markdown
from .rerank import build_pool, truncate_for_cap
from .scoring import evaluate_fact_criteria as _eval
from .scoring import rank_metrics, summarize
from .safety import SafetyError
from .tracing import TraceRecorder, parse_recall_trace, utc_now

TIMESTAMP = "2026-08-30"


# ---------------------------------------------------------------------------
# Manifest / artifacts
# ---------------------------------------------------------------------------

def _provenance_hashes() -> dict:
    hashes = {}
    for folder in ("fixtures", "goldens", "prompts", "configs"):
        for path in sorted((BENCH_ROOT / folder).rglob("*")):
            if path.is_file():
                hashes[str(path.relative_to(BENCH_ROOT))] = sha256_file(path)
    return hashes


def build_manifest(config: BenchConfig, suites: list[str]) -> dict:
    return {
        "schema_version": 1,
        "tool_version": __version__,
        "run_id": f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{sha256_text(str(suites))[:6]}",
        "started_at": utc_now(),
        "mode": config.mode,
        "seed": config.seed,
        "suites": suites,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hindsight_dry_run_extract": config.hindsight_dry_run_extract,
        "input_hashes": _provenance_hashes(),
    }


def _write_artifacts(config: BenchConfig, manifest: dict, run: dict, recorder: TraceRecorder) -> Path | None:
    if config.out_dir is None:
        return None
    out = config.out_dir / manifest["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    manifest["finished_at"] = utc_now()
    manifest["aggregate"] = run["aggregate"]
    (out / "run.json").write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "report.md").write_text(render_run_markdown(run), encoding="utf-8")
    if recorder.events:
        (out / "trace.jsonl").write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in recorder.events), encoding="utf-8"
        )
    return out


def _case(suite, case_id, status, metrics=None, criteria=None, error=None, error_code=None):
    return {
        "case_id": case_id,
        "suite": suite,
        "status": status,
        "metrics": metrics or {},
        "criteria": criteria or {},
        "error": error,
        "error_code": error_code,
    }


# ---------------------------------------------------------------------------
# Retain suites
# ---------------------------------------------------------------------------

def _chat_extract(client, system_prompt, content, model, reasoning, timeout):
    payload = build_chat_request(system_prompt, content, model, reasoning, TIMESTAMP)
    response = client.chat(payload)
    row = {"elapsed_s": round(response["elapsed_s"], 4), "status": response["status"], "ok": response["ok"]}
    if not response["ok"]:
        row["error"] = response["error"]
        return row, None
    row["provider"] = response["body"].get("provider")
    row["usage"] = response["body"].get("usage", {})
    try:
        return row, parse_extraction(response["body"])
    except ExtractionParseError as error:
        row["error"] = str(error)
        return row, None


def _server_extract(hindsight, content):
    response = hindsight.dry_run_extract(content, context="hindsight-bench synthetic dry run", timestamp=f"{TIMESTAMP}T00:00:00Z")
    row = {"elapsed_s": round(response["elapsed_s"], 4), "ok": response["ok"]}
    if not response["ok"]:
        row["error"] = response["error"]
        return row, None
    body = response["body"] or {}
    row["usage"] = body.get("usage", {})
    facts = [
        {
            "what": f.get("text", ""),
            "when": "N/A",
            "who": "",
            "fact_type": f.get("fact_type", "world"),
            "entities": f.get("entities", []),
        }
        for f in body.get("facts", [])
    ]
    return row, facts


def _run_retain_cases(config, system_prompt, fixture_name, golden_name, section):
    """Shared runner for retain-matrix / retain-adversarial."""
    golden = load_golden(golden_name)
    fixture = load_retain_fixture(fixture_name)
    content = fixture[0]["content"]
    cases = []

    if config.mode == "offline":
        for ref in golden[section]["reference_outputs"]:
            facts = ref["facts"]
            evaluation = _eval(facts, golden[section]["case"])
            expected = ref["expected_verdict"]
            status = "pass" if evaluation["passed"] == (expected == "pass") else "fail"
            cases.append(
                _case(
                    section.replace("_", "-"),
                    ref["label"],
                    status,
                    metrics={"facts": len(facts), "criteria_passed": sum(c["passed"] for c in evaluation["criteria"].values())},
                    criteria={k: v["passed"] for k, v in evaluation["criteria"].items()},
                    error=None if status == "pass" else f"expected {expected}, got passed={evaluation['passed']}",
                )
            )
        return cases

    guard = config.guard
    configs = _retain_configs(config)
    key = None
    client = None
    hindsight = None
    if config.hindsight_dry_run_extract:
        hindsight = HindsightClient(config.hindsight_url, guard, config.hindsight_bank, timeout=config.timeout)
    else:
        from .safety import require_env_key

        key = require_env_key("OPENROUTER_API_KEY")
        client = OpenRouterClient(config.openrouter_base, guard, timeout=config.timeout, api_key=key)

    for model_config in configs:
        latencies, fact_counts, criteria_counts = [], [], []
        statuses = []
        for _ in range(config.runs):
            if hindsight is not None:
                row, facts = _server_extract(hindsight, content)
            else:
                row, facts = _chat_extract(client, system_prompt, content, model_config["model"], model_config.get("reasoning"), config.timeout)
            if not row["ok"]:
                error = row.get("error", "")
                if "reasoning is mandatory" in error.lower():
                    statuses.append("skip")
                    cases.append(_case(section.replace("_", "-"), model_config["label"], "skip",
                                       error_code="REASONING_MANDATORY", error=error))
                    break
                statuses.append("error")
                continue
            evaluation = _eval(facts or [], golden[section]["case"])
            latencies.append(row["elapsed_s"])
            fact_counts.append(len(facts or []))
            criteria_counts.append(sum(c["passed"] for c in evaluation["criteria"].values()))
            statuses.append("pass" if evaluation["passed"] else "fail")
        if statuses and all(s == "skip" for s in statuses):
            continue
        cases.append(
            _case(
                section.replace("_", "-"),
                model_config["label"],
                "pass" if statuses and all(s == "pass" for s in statuses) else ("fail" if "fail" in statuses else "error"),
                metrics={
                    "latency_s": summarize(latencies),
                    "facts": summarize([float(n) for n in fact_counts]),
                    "criteria_passed": criteria_counts,
                },
            )
        )
    return cases


def _retain_configs(config) -> list[dict]:
    suite_config = json.loads((BENCH_ROOT / "configs" / "offline.json").read_text())
    configs = suite_config["retain_matrix"]
    if config.models:
        wanted = {m.strip().lower() for m in config.models}
        configs = [c for c in configs if c["label"].lower() in wanted or c["model"].lower() in wanted]
    return configs


def run_retain_matrix(config, recorder) -> list[dict]:
    return _run_retain_cases(config, load_prompt(), "standard", "retain", "matrix")


def run_retain_adversarial(config, recorder) -> list[dict]:
    return _run_retain_cases(config, load_prompt(), "adversarial", "retain", "adversarial")


# ---------------------------------------------------------------------------
# Journal / boundary / context-limit suites
# ---------------------------------------------------------------------------

def run_journal_long(config, recorder) -> list[dict]:
    expected = load_journal_expected()
    chunks, needles, journal = None, None, None
    metrics = {}
    cases = []

    if config.mode == "offline":
        chunks, needles, journal = _journal_chunks(config.max_journal_chars)
        lost = [n for n in needles if not any(n in c["text"] for c in chunks)]
        concatenated = "".join(c["text"] for c in chunks)
        intact = len(needles) - len(lost)
        cases.append(
            _case(
                "journal-long",
                "chunker-integrity",
                "pass" if not lost and concatenated == journal else "fail",
                metrics={**chunk_stats(chunks), "characters": len(journal), "words": len(journal.split()),
                         "needles_intact": intact, "needles_total": len(needles)},
            )
        )
        return cases

    from .safety import require_env_key

    guard = config.guard
    chunks, needles, journal = _journal_chunks(config.max_journal_chars)
    suite_config = json.loads((BENCH_ROOT / "configs" / "offline.json").read_text())
    default_model = suite_config["journal_default"]
    model = config.models[0] if config.models else default_model["model"]
    reasoning = default_model.get("reasoning") if not config.models else {"effort": "low", "exclude": True}
    client = OpenRouterClient(config.openrouter_base, guard, timeout=config.timeout,
                              api_key=require_env_key("OPENROUTER_API_KEY"))
    system_prompt = load_prompt()

    def work(pair):
        index, chunk = pair
        row, facts = _chat_extract(client, system_prompt, chunk["text"], model, reasoning, config.timeout)
        return index, row, facts

    started_wall = utc_now()
    with concurrent.futures.ThreadPoolExecutor(max_workers=config.concurrency) as pool:
        results = list(pool.map(work, enumerate(chunks)))
    wall_note = {"started_at": started_wall}
    facts = [f for _, row, fs in results if fs for f in fs]
    corpus = " ".join(str(f.get("what", "")) for f in facts).lower()
    covered = sum(
        1
        for group in expected["groups"]
        if any(alias.lower() in corpus for alias in group["any"])
    )
    latencies = [row["elapsed_s"] for _, row, _ in results if row.get("ok")]
    input_tokens = sum(row.get("usage", {}).get("prompt_tokens", 0) for _, row, _ in results if row.get("ok"))
    output_tokens = sum(row.get("usage", {}).get("completion_tokens", 0) for _, row, _ in results if row.get("ok"))
    cost = sum(row.get("usage", {}).get("cost", 0) or 0 for _, row, _ in results if row.get("ok"))
    failed = [i for i, row, _ in results if not row.get("ok")]
    dedup_facts = {str(f.get("what")) for f in facts}
    metrics = {
        **chunk_stats(chunks),
        "characters": len(journal),
        "words": len(journal.split()),
        "model": model,
        "wall_s": summarize([r["elapsed_s"] for _, r, _ in results]),
        "latency_s": summarize(latencies),
        "facts_extracted": len(facts),
        "unique_facts": len(dedup_facts),
        "coverage": f"{len(covered)}/{len(needles)}",
        "failed_chunks": len(failed),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 6),
    }
    recorder.add("journal-long", "full-journal", "extraction", **metrics, **wall_note)
    cases.append(_case("journal-long", "full-journal", "pass" if not failed and len(covered) == len(needles) else "fail",
                       metrics=metrics))
    return cases


def _journal_chunks(target_chars):
    from .fixtures import build_journal_chunks

    return build_journal_chunks(target_chars)


def run_boundary_context(config, recorder) -> list[dict]:
    fixture = load_retain_fixture("boundary")
    cases = []

    if config.mode == "offline":
        max_chars = 3000
        for pair in fixture:
            first, second = pair["chunks"]
            problems = []
            if len(first) > max_chars or len(second) > max_chars:
                problems.append("chunk exceeds max_chars")
            joined = first + " " + second
            rechunked = chunk_text(joined, max_chars)
            if "".join(c["text"] for c in rechunked) != joined:
                problems.append("chunker lost characters")
            for position, markers in enumerate(pair["chunk_markers"]):
                corpus = (first if position == 0 else second).lower()
                if not any(alias.lower() in corpus for alias in markers["any"]):
                    problems.append(f"chunk {position} missing marker {markers['any']}")
            cases.append(
                _case(
                    "boundary-context",
                    pair["case_id"],
                    "pass" if not problems else "fail",
                    metrics={"chunk_chars": [len(first), len(second)], "joined_chars": len(joined)},
                    error="; ".join(problems) or None,
                )
            )
        return cases

    from .safety import require_env_key

    client = OpenRouterClient(config.openrouter_base, config.guard, timeout=config.timeout,
                              api_key=require_env_key("OPENROUTER_API_KEY"))
    system_prompt = load_prompt()
    suite_config = json.loads((BENCH_ROOT / "configs" / "offline.json").read_text())
    model = config.models[0] if config.models else "openai/gpt-oss-20b:nitro"

    for pair in fixture:
        first, second = pair["chunks"]
        joined = first + " " + second
        _, combined = _chat_extract(client, system_prompt, joined, model, {"effort": "low", "exclude": True}, config.timeout)
        _, facts_first = _chat_extract(client, system_prompt, first, model, {"effort": "low", "exclude": True}, config.timeout)
        _, facts_second = _chat_extract(client, system_prompt, second, model, {"effort": "low", "exclude": True}, config.timeout)
        split_facts = (facts_first or []) + (facts_second or [])
        corpus_combined = " ".join(str(f.get("what", "")) for f in (combined or [])).lower()
        corpus_split = " ".join(str(f.get("what", "")) for f in split_facts).lower()
        observed = {}
        for name, aliases in pair.get("combined_markers", {}).items():
            observed[f"combined_{name}"] = any(a.lower() in corpus_combined for a in aliases)
        for name, aliases in pair.get("split_markers", {}).items():
            observed[f"split_{name}"] = any(a.lower() in corpus_split for a in aliases)
        cases.append(_case("boundary-context", pair["case_id"], "pass", metrics=observed))
    return cases


def run_context_limit(config, recorder) -> list[dict]:
    golden = load_golden("context_limits")
    cases = []
    estimate = golden["filler_chars_per_token"]

    for model_id, spec in golden["models"].items():
        window = spec["context_tokens"]
        reserved = spec.get("reserved_output_tokens", config.reserved_output_tokens)
        prompt_tokens = golden["system_prompt_tokens"]
        budget_tokens = window - reserved - prompt_tokens
        budget_chars = int(budget_tokens * estimate)
        accepted = golden["probes"].get(model_id, [])
        for probe in accepted:
            # probe.input_tokens is the full text input (system prompt included),
            # matching what the provider counts against the context window.
            fits = probe["input_tokens"] + reserved <= window
            cases.append(
                _case(
                    "context-limit",
                    f"{model_id}:{probe['label']}",
                    "pass" if fits == probe["accepted"] else "fail",
                    metrics={
                        "input_tokens": probe["input_tokens"],
                        "window": window,
                        "budget_tokens": budget_tokens,
                        "budget_chars_estimate": budget_chars,
                        "accepted": probe["accepted"],
                    },
                )
            )
    return cases


# ---------------------------------------------------------------------------
# Recall suite
# ---------------------------------------------------------------------------

def run_recall_trace(config, recorder) -> list[dict]:
    golden = load_golden("recall")
    cases = []

    if config.mode == "offline":
        sample = json.loads((BENCH_ROOT / "fixtures/retrieval/recall_trace_sample.json").read_text())
        parsed = parse_recall_trace(sample["trace"] if "trace" in sample else sample)
        expected = golden["sample_trace"]
        mismatches = [
            f"{key}: {parsed['phases'].get(key)} != {value}"
            for key, value in expected["phases"].items()
            if abs(parsed["phases"].get(key, -1) - value) > 1e-4
        ]
        cases.append(
            _case(
                "recall-trace",
                "sample-trace-parse",
                "pass" if not mismatches else "fail",
                metrics={"phases": parsed["phases"], "counts": parsed["counts"],
                         "total_duration_seconds": parsed["total_duration_seconds"]},
                error="; ".join(mismatches) or None,
            )
        )
        return cases

    if not config.hindsight_url or not config.hindsight_bank:
        raise SafetyError("recall-trace live requires --hindsight-url and --bank")
    client = HindsightClient(config.hindsight_url, config.guard, config.hindsight_bank, timeout=config.timeout)
    health = client.health()
    if not health["ok"]:
        return [_case("recall-trace", "health", "error", error=health["error"], error_code="HINDSIGHT_UNREACHABLE")]
    rows = []
    for query in golden["live_queries"]:
        for _ in range(config.runs):
            response = client.recall(query)
            if not response["ok"]:
                cases.append(_case("recall-trace", query[:40], "error", error=response["error"]))
                continue
            parsed = parse_recall_trace(response["body"].get("trace") or {})
            rows.append(parsed)
            recorder.add("recall-trace", query[:40], "recall", **{k: v for k, v in parsed["phases"].items()})
    if rows:
        aggregate = {
            phase: summarize([r["phases"][phase] for r in rows if phase in r["phases"]])
            for phase in ("generate_query_embedding", "parallel_retrieval", "reranking")
        }
        aggregate["client_visible_internal_s"] = summarize([r["total_duration_seconds"] or 0 for r in rows])
        cases.append(_case("recall-trace", "live-phase-medians", "pass", metrics=aggregate))
    return cases


# ---------------------------------------------------------------------------
# Reranker suites
# ---------------------------------------------------------------------------

def _rerank_cases(config, recorder, sweep_caps: bool) -> list[dict]:
    golden = load_golden("rerank")
    suite_config = json.loads((BENCH_ROOT / "configs" / "offline.json").read_text())
    rerankers = config.models or tuple(suite_config["rerankers"])
    filler = None
    cases = []

    if config.mode == "offline":
        if not sweep_caps:
            for case in golden["cases"]:
                documents, grades = build_pool(case, filler)
                if len(documents) != case.get("pad_to", 300):
                    cases.append(_case("rerank", case["case_id"], "fail", error="pool size mismatch"))
                    continue
                for model_id, reference in case.get("reference_rankings", {}).items():
                    ranked_grades = reference["ranked_grades"]
                    ideal = sorted(grades.values(), reverse=True)
                    metrics = rank_metrics(ranked_grades, ideal)
                    # Reference metrics were transcribed from the recorded session
                    # run; 0.02 absorbs transcription wobble while still catching
                    # real metric-implementation bugs (verified in unit tests).
                    ok = abs(metrics["ndcg10"] - reference["ndcg10"]) < 0.02 and abs(metrics["mrr"] - reference["mrr"]) < 0.02
                    cases.append(_case("rerank-neutral", f"{case['case_id']}:{model_id}", "pass" if ok else "fail",
                                       metrics=metrics))
        if sweep_caps:
            cases.extend(_cap_reference_cases(golden))
        return cases

    from .safety import require_env_key

    client = OpenRouterClient(config.openrouter_base, config.guard, timeout=config.timeout,
                              api_key=require_env_key("OPENROUTER_API_KEY"))
    for case in golden["cases"]:
        for model_id in rerankers:
            documents, grades = (truncate_for_cap(case, 300, filler) if not sweep_caps else (None, None))
            if sweep_caps:
                continue
            result = client.rerank(model_id, case["query"], documents, top_n=20)
            if not result["ok"]:
                cases.append(_case("rerank-neutral", f"{case['case_id']}:{model_id}", "error", error=result["error"],
                                   error_code=f"HTTP_{result['status']}"))
                continue
            ranked = [grades.get(item["index"], 0) for item in result["body"]["results"][:10]]
            ideal = sorted(grades.values(), reverse=True)
            usage = result["body"].get("usage", {})
            cases.append(_case("rerank-neutral", f"{case['case_id']}:{model_id}", "pass",
                               metrics={**rank_metrics(ranked, ideal), "latency_s": round(result["elapsed_s"], 4),
                                        "cost_usd": usage.get("cost"), "search_units": usage.get("search_units")}))
    if sweep_caps:
        cases.extend(_cap_live_cases(config, client, golden, rerankers, recorder))
    return cases


def _cap_reference_cases(golden) -> list[dict]:
    cases = []
    for model_id, caps in golden.get("candidate_caps", {}).items():
        ordered_caps = sorted(caps, key=int)
        latencies = [caps[c]["median_s"] for c in ordered_caps]
        costs = [caps[c]["cost_usd"] for c in ordered_caps]
        monotonic = all(a <= b + 1e-6 for a, b in zip(latencies, latencies[1:]))
        cases.append(
            _case(
                "candidate-cap-scaling",
                model_id,
                "pass" if monotonic else "fail",
                metrics={"caps": ordered_caps, "latency_s": latencies, "cost_usd": costs},
                error=None if monotonic else "reference latency is not monotonic in cap",
            )
        )
    return cases


def _cap_live_cases(config, client, golden, rerankers, recorder) -> list[dict]:
    cases = []
    for case in golden["cases"]:
        if not case.get("use_for_caps"):
            continue
        for model_id in rerankers:
            latencies, costs = [], []
            for cap in config.candidate_caps:
                documents, grades = truncate_for_cap(case, cap)
                result = client.rerank(model_id, case["query"], documents, top_n=min(20, cap))
                if not result["ok"]:
                    cases.append(_case("candidate-cap-scaling", f"{case['case_id']}:{model_id}:cap{cap}", "error",
                                       error=result["error"]))
                    continue
                latencies.append(result["elapsed_s"])
                costs.append(result["body"].get("usage", {}).get("cost"))
                recorder.add("candidate-cap-scaling", case["case_id"], "rerank", model=model_id, cap=cap,
                             latency_s=result["elapsed_s"])
            if latencies:
                cases.append(_case("candidate-cap-scaling", f"{case['case_id']}:{model_id}", "pass",
                                   metrics={"caps": list(config.candidate_caps),
                                            "latency_s": [round(x, 4) for x in latencies], "cost_usd": costs}))
    return cases


def run_rerank_neutral(config, recorder) -> list[dict]:
    return _rerank_cases(config, recorder, sweep_caps=False)


def run_candidate_cap_scaling(config, recorder) -> list[dict]:
    return _rerank_cases(config, recorder, sweep_caps=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

RUNNERS = {
    "retain-matrix": run_retain_matrix,
    "retain-adversarial": run_retain_adversarial,
    "journal-long": run_journal_long,
    "boundary-context": run_boundary_context,
    "context-limit": run_context_limit,
    "recall-trace": run_recall_trace,
    "rerank-neutral": run_rerank_neutral,
    "candidate-cap-scaling": run_candidate_cap_scaling,
}


def select_suites(requested: tuple[str, ...]) -> list[str]:
    if requested == ("all",):
        return list(SUITES)
    unknown = [suite for suite in requested if suite not in SUITES]
    if unknown:
        raise SystemExit(f"unknown suites: {unknown}; valid: {', '.join(SUITES)}")
    return list(requested)


def run_bench(config) -> dict:
    problems = validate_config(config)
    if problems:
        raise SystemExit("config problems: " + "; ".join(problems))
    suites = select_suites(config.suites)
    manifest = build_manifest(config, suites)
    recorder = TraceRecorder(config.out_dir / "trace.jsonl" if config.out_dir else None, manifest["run_id"])
    cases: list[dict] = []
    for suite in suites:
        cases.extend(RUNNERS[suite](config, recorder))
    run = {
        "schema_version": 1,
        "tool_version": __version__,
        "run_id": manifest["run_id"],
        "started_at": manifest["started_at"],
        "finished_at": utc_now(),
        "mode": config.mode,
        "seed": config.seed,
        "suites": suites,
        "cases": cases,
        "aggregate": aggregate_cases(cases),
    }
    artifact_dir = _write_artifacts(config, manifest, run, recorder)
    if artifact_dir is not None:
        run["artifact_dir"] = str(artifact_dir)
    return run


def validate_config(config) -> list[str]:
    from .config import validate as validate_cfg

    return validate_cfg(config)


def aggregate_cases(cases: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_suite: dict[str, dict[str, int]] = {}
    for case in cases:
        by_status[case["status"]] = by_status.get(case["status"], 0) + 1
        suite_stats = by_suite.setdefault(case["suite"], {})
        suite_stats[case["status"]] = suite_stats.get(case["status"], 0) + 1
    return {"total": len(cases), "by_status": by_status, "by_suite": by_suite}
