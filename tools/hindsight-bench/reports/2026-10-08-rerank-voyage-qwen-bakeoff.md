# Reranker bake-off: VoyageAI rerank-3 family vs Qwen3-8B vs NVIDIA free vs Cohere Rerank 4 Pro, 2026-10-08

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
| nvidia/llama-nemotron-rerank-vl-1b-v2:free | 0.9691 | 1.89 s | $0 (free tier) | 0/18 |

\* from successful calls only; the 61% failure rate is disqualifying for the recall path
regardless of quality.

Per-case nDCG@10 (deterministic across repetitions):

| case                   | Pro    | voyage-3 | voyage-3-lite | voyage-2.5 | qwen3-8B | nvidia-free |
| ---------------------- | -----: | -------: | ------------: | ---------: | -------: | ----------: |
| current_live_directory | 0.9508 | 0.9508   | 0.9508        | 0.9508     | 0.9508   | 0.9468      |
| current_model_stack    | 0.9295 | **0.9422** | **0.9422**  | **0.9422** | **0.9422** | 0.9095 |
| negation_attribution   | 0.9737 | 0.9737   | 0.9737        | 0.9737     | 0.9737   | 0.9737      |
| unproven_causality     | **0.9942** | 0.9173 | 0.9173       | 0.9173     | 0.9905   | 0.9905      |
| corrected_deadline     | 1.0000 | 1.0000   | 1.0000        | 1.0000     | 1.0000   | 1.0000      |
| current_reranker       | 0.9173 | **0.9942** | **0.9942**  | 0.9173     | **0.9942** | **0.9942** |

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

### NVIDIA free (added after the first pass)

`nvidia/llama-nemotron-rerank-vl-1b-v2:free` — the multimodal 1.7B reranker, included as an
afterthought despite its vision-RAG framing and 10K context (the ~5K-token 300-doc pools fit).
18/18 calls, deterministic quality, $0.

- Deciding case: top-10 grades `[3, 3, 0, 0, 1]` — both "causation not established" documents
  at ranks 1–2, the explicit causal claim at rank 3. **Passes the unproven-causality test the
  way Pro does**, which no Voyage model does.
- Weakest case `current_model_stack` (0.9095, worst of all models): top-10 `[3, 0, 0, 2, 2]` —
  correct top-1, but ranks both stale-config documents above the partial-current ones. Pro is
  imperfect here too (`[3, 0, 2, 0, 2]`), just less so.
- Latency is the cost: median 1.89 s (first rep cold at 2.1–2.7 s, warm ~1.85 s) — ~0.8 s
  slower than Pro, which would push the ~3.85 s full recall toward ~4.7 s.
- Structural risks not measurable in a 3-minute sample: free tier has no SLA, OpenRouter
  free-tier daily/per-minute quotas apply (the 1000 calls/day limit has bitten this stack
  before, 2026-07-27), free endpoints can be withdrawn without notice, and the 10K window
  clips longer documents.

Also notable: fresh Pro numbers are substantially better than the 2026-08-29 reference
rankings on identical pools and goldens (mean 0.9609 vs 0.8943; unproven_causality 0.9942 vs
0.8824; current_reranker 0.9173 vs 0.7005) — the served model appears to have improved
server-side since August.

## Decisions

1. **Keep `cohere/rerank-4-pro`** — still the best quality/latency/reliability combination:
   top of the deciding case, 1.08 s median, 0 errors, per-search pricing at trivial personal
   volume.
2. Qwen3-Reranker-8B: best measured mean quality and near-Pro on the deciding case, but
   61% HTTP 503 within two minutes plus 2.5× latency — unusable in the synchronous recall
   path today. Re-test if its provider stabilizes.
3. **`nvidia/llama-nemotron-rerank-vl-1b-v2:free` is the best zero-cost option and the best
   swap candidate if rerank spend ever matters** — mean 0.9691 (ahead of Pro), passes the
   deciding case, 18/18 reliable in sample. Trade-offs: ~0.8 s slower per recall and
   free-tier SLA/quota/deprecation risk. Preferred over voyage-3-lite as the value pick
   because lite fails the deciding case.
4. voyageai/rerank-3-lite: fallback only if both cost matters and the deciding-case
   regression is acceptable (~44× cheaper than Pro, ~0.84 s).
5. voyageai/rerank-2.5: dominated (worst mean, same deciding-case failure); not a candidate.

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
