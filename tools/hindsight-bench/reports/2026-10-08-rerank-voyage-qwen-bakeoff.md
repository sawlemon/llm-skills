# Reranker bake-off: VoyageAI rerank-3 family vs Qwen3-8B vs Cohere Rerank 4 Pro, 2026-10-08

Follow-up to the 2026-08-29/30 campaign ([historical results](2026-08-29-30-historical-results.md)),
triggered by VoyageAI's 2026-09-30 release of `rerank-3` / `rerank-3-lite` on OpenRouter and
the availability of `qwen/qwen3-reranker-8b`. Machine-readable twin:
[`2026-10-08-rerank-voyage-qwen-bakeoff.json`](2026-10-08-rerank-voyage-qwen-bakeoff.json).

Method: the committed `rerank-neutral` live suite, unchanged — the 6 golden labeled cases
(current-vs-stale settings/paths/reranker, negation/attribution, unproven causality, corrected
dates), each padded with the deterministic neutral pool to 300 documents, `top_n=20`, scored by
nDCG@10/MRR. 3 repetitions (18 calls per model) for latency; quality was deterministic across
repetitions for every model. Run from the Hindsight host (`hplaptop`) against
`https://openrouter.ai/api/v1/rerank`, so latency is measured where production recall runs.
Total spend ≈ $0.17. Qwen quality figures are computed from its 7 successful calls only.

## Results

| model                 | mean nDCG@10 | median latency | cost / 300-doc call | errors     |
| --------------------- | -----------: | -------------: | ------------------: | ---------- |
| cohere/rerank-4-pro   | 0.9609       | 1.08 s         | $0.0075 (per search) | 0/18      |
| voyageai/rerank-3     | 0.9630       | 0.82 s         | $0.00042            | 0/18       |
| voyageai/rerank-3-lite| 0.9630       | 0.84 s         | $0.00017            | 0/18       |
| voyageai/rerank-2.5   | 0.9502       | 0.80 s         | $0.00042            | 0/18       |
| qwen/qwen3-reranker-8b| 0.9752 *     | 2.65 s         | $0.0062             | **11/18 (HTTP 503 upstream "service overloaded")** |

\* from successful calls only; the 61% failure rate is disqualifying for the recall path
regardless of quality.

Per-case nDCG@10 (deterministic across repetitions):

| case                   | Pro    | voyage-3 | voyage-3-lite | voyage-2.5 | qwen3-8B |
| ---------------------- | -----: | -------: | ------------: | ---------: | -------: |
| current_live_directory | 0.9508 | 0.9508   | 0.9508        | 0.9508     | 0.9508   |
| current_model_stack    | 0.9295 | **0.9422** | **0.9422**  | **0.9422** | **0.9422** |
| negation_attribution   | 0.9737 | 0.9737   | 0.9737        | 0.9737     | 0.9737   |
| unproven_causality     | **0.9942** | 0.9173 | 0.9173       | 0.9173     | 0.9905   |
| corrected_deadline     | 1.0000 | 1.0000   | 1.0000        | 1.0000     | 1.0000   |
| current_reranker       | 0.9173 | **0.9942** | **0.9942**  | 0.9173     | **0.9942** |

## The deciding case, again

On "did the timeout change cause the errors, or was causation unproven?" (top-10 grade
sequences, re-measured live):

- Rerank 4 Pro: `[3, 3, 0, 1, …]` — both "causation not established" documents at ranks 1–2;
  the explicit causal claim ranks 3rd.
- voyageai/rerank-3 and rerank-3-lite: `[3, 0, 3, 1, …]` — the explicit false causal claim
  ("Changing the timeout caused the API errors") ranks **2nd**, above the second
  unproven-causation document.

That is the same failure mode that eliminated Cohere Rerank 4 Fast on 2026-08-29. The Voyage
mean-nDCG edge over Pro (+0.002) comes entirely from the two "current vs superseded stack"
cases; it is a trade, not dominance.

Also notable: fresh Pro numbers are substantially better than the 2026-08-29 reference
rankings on identical pools and goldens (mean 0.9609 vs 0.8943; unproven_causality 0.9942 vs
0.8824; current_reranker 0.9173 vs 0.7005) — the served model appears to have improved
server-side since August.

## Decisions

1. **Keep `cohere/rerank-4-pro`** — still the quality leader on the negation/attribution/
   causality distinctions that durable memories care about; 0 errors.
2. Qwen3-Reranker-8B: best measured mean quality and near-Pro on the deciding case, but
   61% HTTP 503 within two minutes plus 2.5× latency — unusable in the synchronous recall
   path today. Re-test if its provider stabilizes.
3. voyageai/rerank-3-lite is the value fallback if rerank spend ever matters (~44× cheaper
   than Pro, ~0.84 s), accepting the deciding-case regression. At current volume (~$0.0075
   per recall) there is no cost pressure to switch.

## Harness notes

- `--model` (repeatable) was broken: `from_args` wrapped the append-list in a one-tuple,
  sending `"model": [array]` to the API. Fixed on this branch with a regression test; the
  runs above used `HINDSIGHT_BENCH_MODEL=<comma list>` which was already correct.
- OpenRouter rerank models still do not appear in `/api/v1/models`; slugs verified by
  probing `/api/v1/rerank` directly: `voyageai/rerank-3`, `voyageai/rerank-3-lite`,
  `voyageai/rerank-2.5`, `qwen/qwen3-reranker-8b` all live.
- Production context at run time: Hindsight on the bench host is compose-managed at
  `/home/alfred/hindsight` (moved out of `startup-services.sh` the same day); running
  container still configured with `cohere/rerank-4-pro`.
