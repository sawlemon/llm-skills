# Security notes

## Credentials

- `OPENROUTER_API_KEY` is read from the process environment only, at call time.
  It is never written to config files, manifests, traces, or reports, and the
  redaction layer strips anything credential-shaped from error text.
- `HINDSIGHT_API_TOKEN` (optional) is attached as a bearer header to Hindsight
  requests and never logged.
- `.env.example` documents the variables; real env files are git-ignored.

## Network and persistence gates

Three independent gates (see `hindsight_bench/safety.py`):

1. `--allow-network` — required for any outbound request. Offline mode refuses
   to run with network gates enabled.
2. `--allow-persistence` — required for any Hindsight write.
3. `--dry-run` — blocks every mutating Hindsight request outright (mutually
   exclusive with `--allow-persistence`).

Additional write restrictions:

- Writes are refused for personal banks (`default`, `library`, `agents`,
  `career`, `crowdstrike`) and any bank not named `bench_<...>`.
- Read-only Hindsight calls (`/health`, recall, `dry-run-extract`, telemetry)
  need only `--allow-network`; `dry-run-extract` never persists anything.

The unit tests assert, with a recording fake transport, that a dry-run retain
session issues zero mutating requests.

## Data hygiene

- All committed fixtures are synthetic and declare `"synthetic": true`; persons,
  employers, and events in them are fictional.
- No personal journal text, live memory text, private hostnames, usernames, or
  infrastructure paths are committed. The historical report keeps measured
  aggregates only.
- `--include-text` is refused in live mode; it exists for inspecting synthetic
  offline fixtures.

## Scanning before commit

```bash
grep -RInE 'sk-[A-Za-z0-9]|api[_-]?key\s*[:=]|authorization|password|secret' \
  tools/hindsight-bench --exclude-dir=artifacts
```

Any hit should be a documentation placeholder or an env-var _name_, never a value.
