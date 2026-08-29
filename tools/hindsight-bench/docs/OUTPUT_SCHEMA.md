# Output schema

## run.json (written under `--out-dir/<run_id>/`)

```json
{
  "schema_version": 1,
  "tool_version": "1.0.0",
  "run_id": "20260830T120000Z-abc123",
  "started_at": "2026-08-30T12:00:00.000+00:00",
  "finished_at": "...",
  "mode": "offline",
  "seed": 20260830,
  "suites": ["retain-matrix"],
  "cases": [],
  "aggregate": {"total": 36, "by_status": {"pass": 36}, "by_suite": {}}
}
```

Case record:

```json
{
  "case_id": "gpt-oss-20b-low",
  "suite": "matrix",
  "status": "pass",
  "metrics": {"latency_s": {"n": 3, "median": 2.118, "min": 2.075, "max": 3.29, "p95": 3.29}},
  "criteria": {"role": true, "final_deadline": true},
  "error": null,
  "error_code": null
}
```

Statuses: `pass`, `fail` (ran and did not meet criteria), `skip` (e.g. a provider
rejects a parameter — recorded with `error_code` such as `REASONING_MANDATORY`),
`error` (transport/parse failure).

`error_code` conventions: `REASONING_MANDATORY`, `HINDSIGHT_UNREACHABLE`,
`HTTP_<status>`.

## manifest.json

Adds `python`, `platform`, `hindsight_dry_run_extract`, `input_hashes`
(SHA-256 of every fixture/golden/prompt/config file used), and `finished_at`.
The hashes make a run reproducible against the exact inputs it used.

## trace.jsonl

One JSON object per event, metadata only:

```json
{"ts": "...", "run_id": "...", "suite": "recall-trace", "case": "...", "phase": "rerank",
 "model": "...", "cap": 100, "latency_s": 1.69}
```

Never present: query text, memory text, prompts, Authorization headers, API keys,
hostnames. Everything passes through the redaction layer in `safety.py` regardless.

## What is deliberately NOT committed

- Generated journals and pools (rebuilt deterministically at run time).
- Raw model responses, generation IDs, and live traces (the historical report
  keeps sanitized aggregates only).
- Any artifact directory (`artifacts/` is git-ignored).
