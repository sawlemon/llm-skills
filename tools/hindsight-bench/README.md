# hindsight-bench

Reproducible benchmark suite for Hindsight memory operations and OpenRouter
rerankers — the retain / recall / reranker evaluation harness built during the
2026-08-29/30 model-selection campaign. Measured results from that campaign:
[`reports/2026-08-29-30-historical-results.md`](reports/2026-08-29-30-historical-results.md).

Python **standard library only**. Offline mode is deterministic, needs no
network, and writes nothing unless `--out-dir` is given.

## Quick start

```bash
cd tools/hindsight-bench

python3 hindsight_bench.py list                       # show suites
python3 hindsight_bench.py validate                   # fixture/golden integrity
python3 hindsight_bench.py run --mode offline --suite all          # full offline suite
python3 hindsight_bench.py run --mode offline --suite rerank-neutral
python3 hindsight_bench.py score --results <dir>/run.json

python3 -m unittest discover -s tests -t . -v         # unit tests
```

## Suites

| suite                   | what it measures                                                           |
| ----------------------- | -------------------------------------------------------------------------- |
| `retain-matrix`         | retain fact-extraction model comparison (6 configurations)                 |
| `retain-adversarial`    | negation, attribution, uncertainty, unproven causality, corrections        |
| `journal-long`          | long-document chunking + extraction coverage (180K-char synthetic journal) |
| `boundary-context`      | qualifier/correction behavior across no-overlap chunk boundaries           |
| `context-limit`         | request sizing near the model context ceiling                              |
| `recall-trace`          | recall phase decomposition: embedding / retrieval / reranking              |
| `rerank-neutral`        | reranker relevance on a fixed 300-document synthetic pool                  |
| `candidate-cap-scaling` | reranker latency/cost vs candidate cap (50/100/200/300)                    |

## Live runs

Live suites call real endpoints and cost money. They need explicit gates — see
[docs/SECURITY.md](docs/SECURITY.md). Hindsight writes additionally require a
generated `bench_<run_id>` bank; personal banks are refused.

```bash
# retain matrix against real OpenRouter (key from the environment)
export OPENROUTER_API_KEY=sk-or-...   # set outside shell history / scripts
python3 hindsight_bench.py run --mode live --suite retain-matrix \
  --allow-network --runs 3 --json

# same matrix through the server's read-only dry-run extraction
python3 hindsight_bench.py run --mode live --suite retain-matrix \
  --allow-network --hindsight-dry-run \
  --hindsight-url http://REPLACE-ME:8888 --bank bench_myrun

# recall phase tracing (read-only)
python3 hindsight_bench.py run --mode live --suite recall-trace \
  --allow-network --hindsight-url http://REPLACE-ME:8888 --bank bench_myrun

# reranker sweep
python3 hindsight_bench.py run --mode live --suite rerank-neutral \
  --allow-network --json

# candidate caps
python3 hindsight_bench.py run --mode live --suite candidate-cap-scaling \
  --allow-network --candidate-caps 50,100,200,300
```

A Hindsight write is only ever attempted by an explicit persist run, which needs
**all** of: `--mode live --allow-network --allow-persistence --bank bench_<id> --yes`.

## Artifacts

With `--out-dir DIR`, each run writes `DIR/<run_id>/` containing `run.json`,
`manifest.json` (input SHA-256 provenance), `trace.jsonl` (metadata-only events),
and `report.md`. Layout and field reference: [docs/OUTPUT_SCHEMA.md](docs/OUTPUT_SCHEMA.md).

## Layout

```
hindsight_bench/        package (config, safety, chunking, scoring, clients, runner)
configs/                offline.json (suite defaults), live.example.json (placeholders)
fixtures/               synthetic retain/journal/retrieval data (all fictional)
goldens/                criteria, reference outputs, recorded probe tables
prompts/                pinned Hindsight v0.9.2 extraction system prompt
reports/                sanitized historical results (JSON + Markdown)
docs/                   METHODOLOGY, OUTPUT_SCHEMA, SECURITY
tests/                  offline unit tests (unittest, fake transports)
```

Methodology, including the discarded scoring approaches and why the current
criteria are alias-based: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).
