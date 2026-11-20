# Hindsight reranker benchmark: Cohere Rerank 5 Fast (2026-11-20)

**Use `cohere/rerank-5-fast` for Hindsight.** It was 97–98% cheaper than Rerank 4 Pro on these pools, with comparable ranking quality. The configuration change is [homelab PR #38](https://github.com/sawlemon/homelab/pull/38). GLM and the production key cap are unchanged.

## Hard suite

Each of 24 fictional queries had 120 deterministically shuffled candidates: one direct answer (grade 3), one supporting note (grade 2), three query-specific distractors (grade 0), and 115 documents from the other cases (grade 0). Cases covered superseded decisions, lookalike identifiers, effective dates, exceptions, prerequisites, negation, causation, quoted claims, units, time zones, delegated authority, and corrections. All models received the same query and candidate order. No production memories were used.

| Model | nDCG@10 ↑ | Successful calls | Median latency | Mean billed cost per success | Distractor above direct answer |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cohere Rerank 5 Fast | 0.8003 | 24/24 | 0.746 s | $0.000110 | 10/24 |
| Cohere Rerank 4 Pro | 0.7954 | 23/24 | 0.844 s | $0.005000 | 12/23 |
| NVIDIA Nemotron 3.5 Rerank 8B Free | 0.7861 | 24/24 | 0.642 s | $0 | 12/24 |
| Cohere Rerank 5 Pro | 0.7690 | 23/24 | 0.799 s | $0.000252 | 12/23 |
| Qwen3 Reranker 0.6B | 0.6907 | 24/24 | 0.716 s | $0.002796 | 17/24 |

Ranking scores use the 22 cases completed by all models. Other columns use each model's successful calls. Each Pro model timed out once. OpenRouter reported $0.1905 across 120 attempts.

Fast put the direct answer in the top three on 21/24 cases. It ranked an obsolete release approval first and the actual decision fifth. On a different query, it put the final incident review first, while both Pro models put the unconfirmed cause first. The result supports a cheaper reranker, not treating its first result as authoritative. The free NVIDIA model was competitive on this sample, but the run does not establish quota or long-term availability. Qwen 0.6B was not a good substitute on the hard cases; local deployment was not tested.

## Baseline suite

The existing `rerank-neutral` suite ran six fictional queries with 300 candidates each. All 42 calls succeeded and OpenRouter reported $0.1242 total. Rerank 5 Fast scored 0.9737 nDCG@10 at $0.000196 per call, compared with 0.9609 and $0.007500 for Rerank 4 Pro. Rerank 5 Pro scored 0.9758 at $0.000443. The two V5 variants tied on five of six cases, including the false-causation test. Qwen3 8B scored 0.9752 at $0.006208 on the baseline and did not run on the hard suite.

These are synthetic reranker comparisons, not end-to-end recall measurements. Production savings depend on the number and length of candidate memories. An exhausted production OpenRouter key still blocks Hindsight independently of the reranker price.
