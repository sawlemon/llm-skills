# Methodology

This suite reproduces the 2026-08-29/30 Hindsight benchmark campaign. Read the
measured numbers in [`reports/2026-08-29-30-historical-results.md`](../reports/2026-08-29-30-historical-results.md);
this document explains how the tests work and why the scoring is designed the way
it is.

## Modes

- **offline** (default): deterministic, no network, no filesystem artifacts unless
  `--out-dir` is given. Suites run the real chunking/parsing/scoring code against
  bundled synthetic fixtures and reference outputs. Two runs with the same seed
  produce identical aggregates.
- **live**: repeats the original methodology against real endpoints. Requires
  `--allow-network`; anything that mutates Hindsight additionally requires
  `--allow-persistence --yes` and a generated `bench_<run_id>` bank.

## Suites

| suite                   | offline behavior                                                                                                 | live behavior                                                                                                                             |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `retain-matrix`         | scores bundled reference outputs (per-model verdicts + a corrupted negative control) against the golden criteria | runs the six-configuration matrix via direct OpenRouter calls, or via the server's read-only `dry-run-extract` with `--hindsight-dry-run` |
| `retain-adversarial`    | scores adversarial reference outputs                                                                             | same harness, adversarial fixture                                                                                                         |
| `journal-long`          | builds the synthetic journal, chunks it, asserts integrity (no character loss, all needles intact)               | extracts every chunk with the configured model at `--concurrency`, scores coverage                                                        |
| `boundary-context`      | asserts each pair's qualifier sits in a different chunk than its antecedent and the chunker is lossless          | extracts pairs combined vs split and records the observed markers                                                                         |
| `context-limit`         | recomputes acceptance math from recorded probes (input + reserved output vs window)                              | optionally probes near-limit and over-limit requests (over-limit expects HTTP 400)                                                        |
| `recall-trace`          | parses the sanitized trace fixture and compares phase timings to the golden                                      | calls the configured bank's recall endpoint with `trace=true` and aggregates phase medians                                                |
| `rerank-neutral`        | rebuilds each 300-doc pool, re-scores the recorded grade sequences, checks pool size                             | reranks each pool with each model and records nDCG/MRR/latency/cost                                                                       |
| `candidate-cap-scaling` | checks the recorded cap table for monotonic latency                                                              | sweeps caps with real calls, keeping pool and query fixed                                                                                 |

## Scoring design

The session's first scoring pass used per-fact substring checks and produced three
false failures that manual review had to overturn:

1. A model restated a superseded date **with an explicit correction qualifier** —
   correct behavior, flagged as a miss.
2. A model split "user doesn't own X / brother owns X" into two correctly
   attributed facts — flagged as mis-attribution.
3. Coverage checks matched literal phrases, not meaning — date normalization and
   fact splitting looked like misses.

The committed scorer fixes these structurally:

- **Corpus-level alias groups**: a required group passes when any of its aliases
  appears anywhere in the joined fact text (optionally requiring every `all`
  alias). Split facts and reworded facts still count.
- **`unless` qualifiers on forbidden content**: mentioning a superseded date is
  only a violation when no correction qualifier co-occurs.
- **Regex forbidden entries** for cases where a plain substring would always
  self-match (a path that is a prefix of its corrected form).
- **Recorded manual corrections as aliases**: the journal coverage groups count
  "no records were lost", "no data loss", and "migration" as equivalent — that is
  the encoded manual review, not expected prose.

Known limits: corpus-level aliasing is generous (a correction in one fact can
satisfy a forbidden check triggered by another fact), and alias matching is
lexical, not semantic. Treat `partial` verdicts as prompts for manual review of
the actual facts, not as ground truth.

## Reranker pools

Each golden case supplies graded documents (grade 3 exact answer, 2 useful
partial, 1 weak context, 0 stale/false) padded to 300 documents with the
deterministic neutral pool. Pool construction is a pure function, so the index →
grade mapping used for scoring always matches the pool sent to the API.

**Discarded methodology, do not reintroduce:** the first quality run padded pools
with real memories from the live bank while assigning them grade 0. Relevant but
ungraded distractors invalidated every score. Only the neutral-pool method is
implemented.

## Determinism

`build_journal` and `build_neutral_pool` are pure functions; `validate`
regenerates the committed neutral pool and compares it byte-for-byte. No RNG is
used anywhere. Timestamps appear only in run metadata, never in scored metrics.
