# Hindsight model benchmarks, 2026-08-29 to 2026-08-30

Sanitized historical record of the retain / recall / reranker benchmark campaign.
Machine-readable twin: [`2026-08-29-30-historical-results.json`](2026-08-29-30-historical-results.json).
Raw model responses, live memory text, generation IDs, hostnames, usernames, and
infrastructure paths are excluded; these are measured aggregates only. Re-running
the live suites produces fresh numbers, not these.

Environment: Hindsight 0.9.2 (slim image), self-hosted; embeddings
`perplexity/pplx-embed-v1-0.6b`; reranker `cohere/rerank-4-pro`; baseline retain
model `z-ai/glm-5.3-flash` with global `reasoning_effort=high`.

## Why the investigation started

Live telemetry (last 100 LLM requests in the `agents` bank):

| scope | n | median | mean | max |
|---|---:|---:|---:|---:|
| retain fact extraction | 12 | 13.97s | 14.04s | 21.60s |
| background consolidation | 30 | 16.11s | 19.58s | 55.58s |
| consolidation dedup | 2 | 5.44s | 5.44s | 7.30s |

Hindsight v0.9.2 synchronous retain waits for extraction, embeddings, entity/link
work, and DB writes; consolidation runs afterward in the background. Extraction is
one schema-constrained LLM request per ~3,000-character chunk, chunks concurrent.

## Retain model matrix (direct calls, exact live prompt, strict JSON schema)

| model | success | median | notes |
|---|---|---:|---|
| GLM 5.3 Flash, effort=high | 3/3 | 7.79s | accurate; slow |
| GLM 5.3 Flash, effort=none | 0/3 | — | endpoint rejects `none`; `low` is the practical floor |
| **GPT-OSS 20B, effort=low** | **3/3** | **2.12s** | qualifiers preserved on manual review; ~$0.00049/call |
| GPT-OSS 120B, effort=low | 3/3 | 11.43s | 3 different providers routed; 4.9–15.5s spread |
| Gemini 2.5 Flash-Lite | 3/3 | 4.77s | dropped the recorded-call count and the API-key rule; weakened qualifiers |
| Mistral Small 3.2 | 2/3 | 29.94s | one unparseable response; slow |

Automated criteria scoring was 13 checks; the two "misses" for GLM/GPT-OSS were
scoring artifacts (a superseded date restated with an explicit correction). Those
lessons are encoded as alias/`unless` criteria in `goldens/retain.json`.

## Adversarial extraction (negation, attribution, uncertainty, unproven causality)

| model | median | automated | outcome |
|---|---:|---|---|
| GLM 5.3 Flash | 1.86s | 11/11 ×3 | clean |
| GPT-OSS 20B | 0.81s | 9/11 ×3 | one artifact (split facts) + one real subtlety: omitted the unproven-causation qualifier sentence while never asserting causation |
| Gemini 2.5 Flash-Lite | 2.98s | 8/11 ×3 | weakened qualifications, over-extracted |

The GPT-OSS causality omission is deliberately recorded as a miss in the committed
criteria; the historical manual review accepted it as a trade-off. Both readings are
documented in `goldens/retain.json`.

## Long journal (the "44-minute transcript" question)

Synthetic 180,000-character / 29,726-word journal, 12 planted durable facts,
chunked by the live Hindsight v0.9.2 chunker:

- 78 chunks (max 2,962 chars, avg 2,307)
- Extraction with `openai/gpt-oss-20b:nitro` (low reasoning, 8-way concurrency):
  **78/78 chunks, 18.4s wall, median call 1.48s, p95 2.30s**
- 12/12 planted facts recovered (automated checks said 9/12; manual review confirmed
  all 12 — date normalization and fact splitting fooled the string checks)
- 0 duplicate facts; 261,780 input / 3,616 output tokens; **$0.0157 total**

The large input-token total is Hindsight's ~3,300-token extraction prompt repeated
per chunk, not journal volume.

## Chunk boundaries are the real limitation

Same fact pairs, combined versus independent no-overlap chunks:

- Decision + correction → combined: one corrected fact. Split: **both** the obsolete
  decision and the correction persist as separate facts.
- Event + unproven-causality qualifier → split preserves both but the qualifier
  becomes a separate memory.
- Third-party claim + unverified qualifier → split loses the pronoun antecedent
  ("her claim" with no Maya in the same chunk).

Conclusion: for long journals, boundary context — not model context size — is what
to fix (importer-side overlap or a post-extraction reconciliation pass).

## Direct context-limit probes (GPT-OSS 20B via Groq)

| request | prompt tokens | result |
|---|---:|---|
| 390,000 chars | 77,942 | accepted, 6.0s, all zone facts recovered, $0.006 |
| 460,000 chars | 91,713 | accepted, 6.5s, 4/5 needles; missed an end-of-context qualifier, $0.007 |
| 600,000 chars | ~154,012 + 3,000 reserved | rejected 400 before inference: 131,072-token window exceeded |

Extraction recall degrades before the hard ceiling, and the window covers system
prompt + input + reserved output. Normal retain never approaches this (chunks are
~500–900 tokens).

## Recall: no generative LLM at all

Recall makes one query-embedding call and one reranker call. Nine traced
mid-budget recalls (3 queries × 3 runs): embedding 0.93s, DB retrieval+fusion 0.06s,
reranking 2.04s; internal total 3.07s; client-visible 3.85s. The database is never
the bottleneck; the two OpenRouter calls are.

## Rerankers (the only usable non-free OpenRouter options are Cohere's three)

Latency, identical 300-document pool, 5 runs:

| model | median | cost/300 docs |
|---|---:|---:|
| Rerank 4 Pro | 1.39s | $0.0075 |
| Rerank 4 Fast | 1.02s | $0.0060 |
| Rerank v3.5 | 1.00s | $0.0030 |

Clean quality (6 labeled cases, neutral 300-doc pools): Pro nDCG@10 0.894 (5/6
relevant top-1), Fast 0.865 (4/6), v3.5 0.845 (4/6). Deciding case: on
"did the timeout change cause the errors, or was causation unproven?", Fast ranked
the explicit causal claim above the unproven-causation documents; Pro did not.

**Decision: keep Rerank 4 Pro.** Fast saves ~0.4s of a 3.85s recall — not worth the
regression on exactly the distinction durable memories care about.

Methodology correction: an earlier quality run padded pools with real memories from
the live bank (graded 0 as distractors) — relevant-but-ungraded distractors made the
scores invalid. It was discarded and replaced by the neutral-pool method; the
committed suite only implements the clean version.

## Candidate caps (direct calls)

| cap | Pro | Fast | v3.5 |
|---:|---|---|---|
| 50 | 1.54s / $0.0025 | 1.51s / $0.0020 | 1.43s / $0.0010 |
| 100 | 1.69s / $0.0025 | 1.52s / $0.0020 | 1.46s / $0.0010 |
| 200 | 2.00s / $0.0050 | 1.58s / $0.0040 | 1.57s / $0.0020 |
| 300 | 2.14s / $0.0075 | 1.74s / $0.0060 | 1.66s / $0.0030 |

Cap 100 would save ~0.45s and two-thirds of rerank cost, but bank-level quality at
lower caps was not validated — leave `HINDSIGHT_API_RERANKER_MAX_CANDIDATES` at 300
until a quality-validated sweep says otherwise.

## Production rollout (2026-08-30)

Retain-only change in the startup script (backup kept):

```bash
HINDSIGHT_API_RETAIN_LLM_MODEL=openai/gpt-oss-20b:nitro
HINDSIGHT_API_RETAIN_LLM_REASONING_EFFORT=low
HINDSIGHT_API_RETAIN_LLM_EXTRA_BODY={"provider":{"require_parameters":true}}
```

Verified: retain-specific effort variable confirmed in the running image's source
(resolved before the global value); startup script executed; health OK; logs show
GPT-OSS retain at `low` with GLM reflect/consolidation unchanged at `high`; dry-run
extraction 5/5 on the adversarial sample (1.74s) and multi-chunk sample (1.42s);
telemetry chunks 1.02–1.57s versus 9.6–19.4s for the immediately preceding GLM calls.
`low` reasoning still emits ~10–190 reasoning tokens per call; the endpoint rejects
`none`.

## Standing decisions

1. Retain: `openai/gpt-oss-20b:nitro`, low reasoning.
2. Reranker: keep `cohere/rerank-4-pro`.
3. Candidate cap: keep 300 pending a quality-validated sweep.
4. Chunk size: keep 3,000 chars; fix boundary context in the importer, not by
   inflating chunks.
5. Rerankers measure relevance, not truth — stale facts must be invalidated; no
   reranker reliably ranks a corrected statement above a stale one.
