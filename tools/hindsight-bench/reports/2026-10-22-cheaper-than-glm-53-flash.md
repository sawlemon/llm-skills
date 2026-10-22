# Cheaper-than-GLM-5.3-Flash candidates, including DeepSeek v4.1 Flash (2026-10-22)

**Bottom line: keep `z-ai/glm-5.3-flash`.** It is effectively the price floor for
this memory workload on OpenRouter. DeepSeek v4.1 Flash is 6–60× more expensive,
not cheaper, and every model that IS cheaper than GLM 5.3 Flash either fails the
structured extraction task outright or comes from a free provider that is broken
or rate-limited today. No switch was made.

## Why the investigation started

OpenRouter spend this month is dominated by GLM 5.3 Flash (~$4.0) and Rerank 4 Pro
(~$2.7). The question: is there a model that is cheaper than GLM 5.3 Flash and at
least as good for the Hindsight server's general/reflect roles (GLM 5.3 Flash at
`reasoning_effort=high` is the live configuration; retain already runs
`openai/gpt-oss-20b:nitro`, reranking was re-decided on 2026-10-08).

## Step 1 — DeepSeek v4.1 Flash is not cheaper (disqualified on price)

OpenRouter catalog prices, USD per million tokens (2026-10-22):

| model | input | output | blended (80/20 in/out) |
| --- | ---: | ---: | ---: |
| **z-ai/glm-5.3-flash** (current) | **$0.0052** | **$0.1985** | **$0.0439** |
| deepseek/deepseek-v4.1-flash | $0.30 | $1.20 | $0.2880 |
| deepseek/deepseek-v4.1-flash-1017 | $0.15 | $0.60 | $0.1440 |
| deepseek/deepseek-v4-flash-0731 (previous server model) | $0.0444 | $0.1333 | $0.0622 |

Memory workloads are input-dominated (the August journal run measured 261,780
input vs 3,616 output tokens), so GLM's near-free input pricing is decisive: at
DeepSeek v4.1 Flash prices the same usage that costs ~$4/month on GLM would cost
roughly $25–80/month. The live model comparison was aborted before spending bench
budget on it. (There is no "GLM 5.1 Flash" on OpenRouter; the flash line is
4.7 → 5.3, and 4.7 is pricier than 5.3.)

## Step 2 — catalog scan for anything cheaper that could still be smart

All OpenRouter models cheaper than GLM 5.3 Flash's blended price AND supporting
structured outputs (`response_format` json_schema strict is required by the
extraction path):

| candidate | price (in/out $/M) | verdict |
| --- | --- | --- |
| nvidia/nemotron-3-super-120b-a12b:free | $0 / $0 | **404 from NVIDIA provider** — its function endpoint returns "Not found for account" on every call (with or without reasoning effort). Unusable. |
| nvidia/nemotron-3.5-super-vl:free | $0 / $0 | Responds, but extracted **0 usable facts** (2/13 matrix, 2/19 adversarial criteria) at 88–536 s per call. Unusable. |
| xingchen-agi/xing4.0-29b-a4b:free | $0 / $0 | HTTP 429 "temporarily rate-limited upstream" on all calls. Unusable today. |
| nex-agi/nex-n2.5-mini | $0.025 / $0.10 | HTTP 503 "service unavailable" from provider on all calls. Unusable today. |
| openai/gpt-oss-20b | $0.018 / $0.09 | Already the retain model; the August campaign measured it weaker than GLM on adversarial extraction (dropped the unproven-causation qualifier). Not better. |
| mistralai/mistral-nemo | $0.029 / $0.03 | 2024-era 12B class; strictly weaker than GLM 5.3 Flash. Not benched. |
| google/gemma-3-4b-it | $0.04 / $0.05 | 4B class; strictly weaker. Not benched. |
| openrouter/free | $0 / $0 | Randomly routes across free models — the wrong kind of nondeterminism for a memory system. Not benched. |

## Live run (retain-matrix + retain-adversarial, 3 runs each)

Run from the Hindsight host against OpenRouter, run id `20261022T150158Z-60d88d`
(artifacts on the host under `live-runs/2026-10-22-cheaper-than-glm/`; wall time
~22 min; GLM calls ≈ $0.005, free models $0).

| config | matrix | adversarial | median latency |
| --- | --- | --- | ---: |
| **glm-high (z-ai/glm-5.3-flash, effort=high)** | **13/13 criteria ×3 — pass** | 17/19 ×3 (see note) | 21.8 s / 14.7 s |
| nemotron-3-super-120b-free-high | error (all calls) | error (all calls) | — |
| nemotron-3.5-super-vl-free | fail — 2/13, 0 facts | fail — 2/19, 0 facts | 132.6 s / 101.9 s |
| xing4-29b-free | error (all calls) | error (all calls) | — |
| nex-n2.5-mini-high | error (all calls) | error (all calls) | — |

GLM's two stable adversarial misses (identified by re-scoring one live response
with the committed criteria):

- `berlin_uncertain` — scoring artifact: GLM wrote "have not made a final
  decision or applied for a visa", which does not substring-match the alias list
  ('no decision', 'not decided', …). Correct by human reading.
- `causality_unproven` — real omission of the "causation not established"
  qualifier, the same trade-off recorded for GPT-OSS 20B in the August campaign.
  The forbidden criterion (asserting the false cause) was never violated.

GLM matrix latency was 21.8 s median vs 7.8 s in the August record on identical
prompts — provider variance of the kind previously noted for OpenRouter routing;
quality scores were identical across all 3 repetitions.

## Free-tier viability note

OpenRouter free-model quotas are 1,000 requests/day when ≥$10 credits have been
purchased (this account qualifies; 20 requests/min at both tiers). Volume for
general/reflect (~100–300 calls/day) would fit — but today every free candidate
that supports this request shape is broken, rate-limited, or returns garbage, so
the free tier is not a production option for this workload regardless of quota.

## Harness fix made during this run

`parse_extraction` crashed the whole run with `TypeError` when a model returned
`message.content: null` (common with reasoning-style free models). Fixed to raise
`ExtractionParseError` (recorded as a per-case error) with a regression test;
matrix entries for the four benched candidates are committed in
`configs/offline.json` for future re-tests.

## Decision

1. **Keep `z-ai/glm-5.3-flash` for general + reflect.** Nothing cheaper passed;
   nothing at the same price passed better.
2. **Re-test the free candidates opportunistically** (the 404/429/503s may be
   transient provider outages) — `--model nemotron-3-super-120b-free-high ...`
   with the committed matrix entries makes that a one-liner. Do not hold your
   breath for the 120B: its sibling that did answer returned no facts at all.
3. If spend must drop further, the levers are effort, not models: GLM's output
   price ($0.1985/M) is where its cost lives, and `effort=high` burns reasoning
   tokens as output. Dropping reflect/general to `effort=low`/`medium` is the
   cheapest real saving available — a quality trade this benchmark has not
   evaluated end-to-end.
