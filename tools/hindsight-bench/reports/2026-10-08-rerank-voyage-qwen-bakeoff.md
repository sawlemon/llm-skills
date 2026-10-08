# Reranker comparison: Cohere Rerank 4 Pro vs the new VoyageAI, Qwen, and NVIDIA models (2026-10-08)

**Bottom line: keep Cohere Rerank 4 Pro.** It still gives the best combination of ranking
accuracy, speed, and reliability. The new VoyageAI models are cheaper and slightly faster but
fail the most important test. The Qwen model scores highest but fails 61% of its calls. The
free NVIDIA model is the best no-cost option and the only alternative worth considering.

Machine-readable results: [`2026-10-08-rerank-voyage-qwen-bakeoff.json`](2026-10-08-rerank-voyage-qwen-bakeoff.json).
The previous comparison (2026-08-29/30) that chose Rerank 4 Pro is in
[`2026-08-29-30-historical-results.md`](2026-08-29-30-historical-results.md).

## Background

Hindsight is a memory service. When you ask it a question, it first pulls candidate memories
from its database, then a **reranker model** sorts those candidates so the most relevant ones
come first. The reranker runs on every recall, so its accuracy decides whether the right
memory surfaces, and its speed and price decide how the recall feels and costs.

The reranker in production is **Cohere Rerank 4 Pro** (chosen on 2026-08-29, ~$0.0075 per
recall). On 2026-09-30, VoyageAI released two new rerankers on OpenRouter (`rerank-3` and
`rerank-3-lite`), and Qwen and NVIDIA rerankers were also available. This comparison checks
whether any of them should replace Pro.

## How the test works

The benchmark asks each model the same **6 test questions**. Each question comes with a pool
of **300 candidate documents**:

- **4–5 hand-written documents with a known relevance grade.** Grade 3 = directly answers the
  question. Grade 2 = partially answers it. Grade 1 = related but incomplete. Grade 0 = looks
  relevant but is wrong — these are deliberate traps, for example an outdated setting
  presented as current, or a claim of causation when the source only said the timing was
  suspicious.
- **~295 neutral filler sentences** that have nothing to do with the question.

The model must rank the pool. We score its top 10 with **nDCG@10**, a standard ranking metric
from 0.0 to 1.0 (1.0 = the relevant documents are on top in the correct order). A model that
falls for a trap — ranking a grade-0 document above grade-3 ones — loses points.

Each model answered all 6 questions **3 times** (18 calls total). Ranking scores were
identical across repetitions for every model, so quality numbers are stable; latency is the
median of all 18 calls. The test ran from the server that hosts Hindsight, against
OpenRouter's rerank endpoint, so latency reflects real usage. Total cost: about $0.17.

The 6 questions test the distinctions that matter for durable memories: which setting is
current vs superseded, which path is live vs rollback-only, who really owns the thing
(negation/attribution), whether causation was claimed or only suspected, and dates after a
correction.

## Results

| model                                  | mean nDCG@10 | median latency | cost per call (300 docs) | failed calls |
| -------------------------------------- | -----------: | -------------: | -----------------------: | ----------- |
| **cohere/rerank-4-pro** (current)      | 0.9609       | 1.08 s         | $0.0075                  | 0 of 18     |
| voyageai/rerank-3                      | 0.9630       | 0.82 s         | $0.0004                  | 0 of 18     |
| voyageai/rerank-3-lite                 | 0.9630       | 0.84 s         | $0.0002                  | 0 of 18     |
| voyageai/rerank-2.5                    | 0.9502       | 0.80 s         | $0.0004                  | 0 of 18     |
| qwen/qwen3-reranker-8b                 | 0.9752 *     | 2.65 s         | $0.0062                  | **11 of 18** |
| nvidia/llama-nemotron-rerank-vl-1b-v2:free | 0.9691    | 1.89 s         | $0 (free tier)           | 0 of 18     |

\* Qwen's quality score is computed only from its 7 successful calls. Its provider returned
"service overloaded" (HTTP 503) on 11 of 18 calls within two minutes. A reranker that fails
this often makes the whole recall fail, so it is not usable regardless of quality.

Per-question scores (nDCG@10; best per row in bold):

| question                | Pro    | voyage-3 | voyage-3-lite | voyage-2.5 | qwen3-8B | nvidia-free |
| ----------------------- | -----: | -------: | ------------: | ---------: | -------: | ----------: |
| live directory          | 0.9508 | 0.9508   | 0.9508        | 0.9508     | 0.9508   | 0.9468      |
| current model stack     | 0.9295 | **0.9422** | **0.9422**  | **0.9422** | **0.9422** | 0.9095    |
| negation / attribution  | 0.9737 | 0.9737   | 0.9737        | 0.9737     | 0.9737   | 0.9737      |
| unproven causality      | **0.9942** | 0.9173 | 0.9173       | 0.9173     | 0.9905   | 0.9905      |
| corrected deadline      | 1.0000 | 1.0000   | 1.0000        | 1.0000     | 1.0000   | 1.0000      |
| current reranker        | 0.9173 | **0.9942** | **0.9942**  | 0.9173     | **0.9942** | **0.9942** |

## The test that decides the choice

Question: *"Did changing the timeout cause the errors, or was causation unproven?"*

The pool contains two documents saying causation was **not** established (grade 3), one saying
errors simply *followed* the change (grade 1), and a trap saying the timeout change outright
**caused** the errors (grade 0). A good reranker must put the "unproven" documents on top and
must not let the confident-but-wrong claim outrank them.

What the top of each ranking looked like (grades, best to worst possible: 3, 3, 1, 0, 0):

- **Rerank 4 Pro — `[3, 3, 0, 1]`: passes.** Both "causation not established" documents at
  ranks 1–2; the false causal claim drops to rank 3.
- **NVIDIA free — `[3, 3, 0, 0, 1]`: passes.** Same correct shape as Pro. Qwen3-8B scored
  0.9905 here (nearly Pro's 0.9942), though its full ordering was not recorded.
- **voyageai/rerank-3 and rerank-3-lite — `[3, 0, 3, 1]`: fail.** The false claim ("changing
  the timeout caused the errors") lands at **rank 2**, above the second "unproven" document.

This matters because a memory system must never surface "X caused Y" when the stored memory
only says "Y happened after X". The same trap eliminated Cohere's own Rerank 4 Fast in the
August comparison. The VoyageAI models' tiny lead in average score (+0.002 over Pro) comes
entirely from the two "which setting is current" questions — it is a trade, not an
improvement.

One more observation: Pro scored much higher today than in the August record on identical
questions (mean 0.9609 vs 0.8943). The served model appears to have improved since August,
which widens its lead over everything except the unreliable Qwen.

## Notes on each candidate

- **voyageai/rerank-3 / rerank-3-lite** — reliable (0 errors), ~0.83 s, and very cheap
  (per-token billing, ~$0.0002–0.0004 per recall vs Pro's $0.0075). Both fail the causality
  trap as described above. They do beat Pro on the "which setting is current" questions
  (0.9942 vs 0.9173 on the reranker question), which is where their small average lead comes
  from. Fine models in general; the wrong fit for this memory system's hardest requirement.
- **voyageai/rerank-2.5** — the previous VoyageAI generation. Lowest average score of all and
  fails the causality trap. Dominated by its own successors; not a candidate.
- **qwen/qwen3-reranker-8b** — the most accurate rankings when it answers (mean 0.9752, near
  Pro on the causality trap), but the provider was overloaded for 61% of calls and each
  successful call took 2.65 s. Unusable in the synchronous recall path today. Worth retesting
  if its provider stabilizes.
- **nvidia/llama-nemotron-rerank-vl-1b-v2:free** — a 1.7B multimodal reranker (built for
  reranking images in vision pipelines) that also handles text. Surprisingly strong: second
  best average (0.9691, ahead of Pro), passes the causality trap like Pro, 0 errors, and it
  is free. Costs of using it: latency (1.89 s median, about 0.8 s slower than Pro — a full
  recall would go from ~3.85 s to ~4.7 s), and free-tier risks — no service-level guarantee,
  OpenRouter free-tier daily quotas (which have caused 429 outages in this stack before),
  endpoints that can be withdrawn, and a small 10K-token window that clips unusually long
  documents (the standard 300-short-document pool fits fine). Its one weak spot is the
  "current model stack" question (0.9095, worst of all models): it ranked both outdated-config
  documents above the partially-current ones. Pro is imperfect there too, just less so.

## Decision

1. **Keep `cohere/rerank-4-pro` in production.** Best on the deciding test, fastest of the
   accurate options, zero failures, and ~$0.0075 per recall is trivial at personal volume.
2. **Do not use Qwen3-Reranker-8B** until its provider stops returning 503s.
3. **If rerank cost ever needs to go to zero, switch to
   `nvidia/llama-nemotron-rerank-vl-1b-v2:free`** — it is the only alternative that both
   beats Pro on average and passes the causality trap. Accept ~0.8 s slower recalls and the
   free-tier risks listed above. This displaces voyage-3-lite as the designated fallback,
   because lite fails the causality trap.

## Appendix: harness and environment notes

- Models are scored by the committed `rerank-neutral` suite in this repository
  (`tools/hindsight-bench`). The synthetic questions and neutral filler pool are fictional;
  no real memories were sent to any provider.
- OpenRouter's rerank models do not appear in its public `/api/v1/models` catalog. The slugs
  above were verified live against the undocumented `/api/v1/rerank` endpoint
  (2026-10-08). `nvidia/llama-nemotron-rerank-vl-1b-v2` without the `:free` suffix returns 404.
- A bug was found and fixed in the benchmark CLI during this run: passing the repeatable
  `--model` flag sent the model list as an array instead of separate runs, and every call
  failed with HTTP 400. Fixed with a regression test on this branch; earlier runs used the
  equivalent environment variable, which was already correct.
- Production context at test time: Hindsight runs from a compose file on its host server,
  configured with `cohere/rerank-4-pro`; that configuration was not changed by this report.
