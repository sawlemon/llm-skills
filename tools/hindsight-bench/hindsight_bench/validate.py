"""Offline validation of fixtures, goldens, configs, and the pinned prompt.

Runs entirely without network. ``validate`` (CLI) and the test suite share
this entry point. Includes the regeneration check: the committed neutral
pool must be byte-identical to ``build_neutral_pool(300)`` output.
"""

from __future__ import annotations

import json

from .config import BENCH_ROOT
from .fixtures import build_neutral_pool, load_jsonl
from .schemas import validate_golden_case


def run_validation() -> list[str]:
    problems: list[str] = []

    # Fixtures parse and carry required fields.
    for name in ("standard", "adversarial", "boundary"):
        path = BENCH_ROOT / "fixtures" / "retain" / f"{name}.jsonl"
        try:
            records = load_jsonl(path)
        except Exception as error:  # noqa: BLE001 - validation must survive bad files
            problems.append(f"{path.name}: unparseable ({error})")
            continue
        if not records:
            problems.append(f"{path.name}: empty fixture")
        for index, record in enumerate(records):
            if "case_id" not in record:
                problems.append(f"{path.name}[{index}]: missing case_id")
            if record.get("synthetic") is not True:
                problems.append(f"{path.name}[{index}]: fixture must declare synthetic=true")
            if name == "boundary":
                if len(record.get("chunks", [])) != 2:
                    problems.append(f"{path.name}[{index}]: boundary case needs exactly 2 chunks")
                if len(record.get("chunk_markers", [])) != 2:
                    problems.append(f"{path.name}[{index}]: boundary case needs chunk_markers per chunk")

    # Retrieval fixtures.
    queries_path = BENCH_ROOT / "fixtures" / "retrieval" / "queries.jsonl"
    try:
        queries = load_jsonl(queries_path)
        if not queries:
            problems.append("queries.jsonl: empty")
        for index, record in enumerate(queries):
            if "query" not in record:
                problems.append(f"queries.jsonl[{index}]: missing query")
    except Exception as error:  # noqa: BLE001
        problems.append(f"queries.jsonl: unparseable ({error})")

    pool_path = BENCH_ROOT / "fixtures" / "retrieval" / "neutral_pool.jsonl"
    try:
        committed = [json.loads(line)["text"] for line in pool_path.read_text().splitlines() if line.strip()]
        regenerated = build_neutral_pool(len(committed))
        if committed != regenerated:
            problems.append("neutral_pool.jsonl does not match build_neutral_pool output (regeneration drift)")
    except Exception as error:  # noqa: BLE001
        problems.append(f"neutral_pool.jsonl: unparseable ({error})")

    # Goldens.
    for name in ("retain", "rerank", "recall", "context_limits"):
        path = BENCH_ROOT / "goldens" / f"{name}.json"
        try:
            golden = json.loads(path.read_text())
        except Exception as error:  # noqa: BLE001
            problems.append(f"goldens/{name}.json: unparseable ({error})")
            continue
        for section in ("matrix", "adversarial"):
            if section in golden:
                where = f"goldens/{name}.json#{section}"
                problems.extend(validate_golden_case(golden[section]["case"], where))
                for ref in golden[section].get("reference_outputs", []):
                    if "label" not in ref or "expected_verdict" not in ref or "facts" not in ref:
                        problems.append(f"{where}: reference output needs label/expected_verdict/facts")
        if name == "rerank":
            for case in golden.get("cases", []):
                if "query" not in case or "graded" not in case:
                    problems.append(f"goldens/rerank.json: case {case.get('case_id')} needs query+graded")
                for entry in case["graded"]:
                    if "text" not in entry or "grade" not in entry:
                        problems.append(f"goldens/rerank.json: graded entry needs text+grade")
        if name == "recall" and "sample_trace" not in golden:
            problems.append("goldens/recall.json: missing sample_trace expectations")

    # Configs.
    offline = BENCH_ROOT / "configs" / "offline.json"
    try:
        config = json.loads(offline.read_text())
        for key in ("retain_matrix", "journal_default", "rerankers", "candidate_caps"):
            if key not in config:
                problems.append(f"configs/offline.json: missing {key}")
    except Exception as error:  # noqa: BLE001
        problems.append(f"configs/offline.json: unparseable ({error})")

    # Pinned prompt.
    prompt_path = BENCH_ROOT / "prompts" / "hindsight-v0.9.2-extraction.md"
    if not prompt_path.exists():
        problems.append("prompts/hindsight-v0.9.2-extraction.md: missing")
    elif "FactExtractionResponse" not in prompt_path.read_text():
        problems.append("prompts/hindsight-v0.9.2-extraction.md: does not contain the extraction schema")

    return problems
