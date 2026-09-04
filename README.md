# llm-skills

Reusable LLM skills (`skills/`) — system-prompt definitions injected into LLM tools and apps
(Claude Code, Claude Desktop, Cherry Studio, …) — plus the Cherry Studio prompt hill-climbing harness
that maintains some of them.

> The LLM Report Card previously lived here; it now has its own repository at
> [sawlemon/llm-reportcard](https://github.com/sawlemon/llm-reportcard), published to
> <https://sawlemon.github.io/llm-reportcard/>.

## Layout

```
skills/
  alfred/SKILL.md
  hill-climb/SKILL.md
  hinsighter/SKILL.md
  search/SKILL.md
  ssd-backup/SKILL.md
tools/
  cherry-hillclimb/         daily prompt hill-climbing harness for a Cherry Studio assistant (see below)
  hindsight-bench/          reproducible Hindsight retain/recall/reranker benchmark suite (see below)
prompts/
  cherry-studio/<slug>/     current.md, candidate.md, history/, CHANGELOG.md per assistant (cherry-hillclimb output)
reports/
  cherry-hillclimb/         one dated report per propose run (learnings kept/rejected, diff)
```

## Skills

Point a tool's system prompt at a `skills/*/SKILL.md` file to apply that behavior.

- **`alfred/`** — baseline behavior rules applied to every conversation, whatever the topic. Three rules:
  route all long-term memory through the Hindsight MCP server (including bank selection across `health`,
  `career`, `finances`, `work`, `default`), keep output concise and free of preamble, and stay
  epistemically honest — search before guessing, label speculation, and say "I don't know" when that is
  the truthful answer.
- **`hill-climb/`** — daily learning-extraction personas.
  - `daily-claude-to-codex-learning-extraction.md` — audits Claude Code session transcripts
    (`~/.claude/projects/**`) and merges durable, gated, evidenced learnings into a small always-on map
    (`~/.codex/AGENTS.md`, capped at 100 lines) plus a system-of-record `~/.codex/docs/` tree. No quota —
    an empty run with nothing durable found is a correct outcome.
  - `daily-codex-learning-extraction.md` — the Codex-specific self-learning variant: audits **Codex**
    session transcripts (`~/.codex/sessions/**`) directly, reading each session's project `cwd` from its
    `session_meta` line and writing to the same `~/.codex/AGENTS.md` map + `~/.codex/docs/` tree.
    The transactional runner in `skills/hill-climb/scripts/codex_learning_extractor.py` handles session
    discovery, checkpointing, staging, validation, backups, apply, and recovery.
  - `cherry-studio-personal-prompt-hillclimb.md` — a different kind of persona: not a coding-agent
    instruction file but the exact system prompt sent to an LLM by `tools/cherry-hillclimb/analyze.mjs`
    (see "Cherry Studio prompt hill-climbing" below). Analyzes one Cherry Studio assistant's own recent
    chat history and proposes a justified edit to its own system prompt.
  - `zcode-learning-extraction.md` — the ZCode variant: audits **ZCode** session transcripts, which live
    in a local SQLite database (`~/.zcode/cli/db/db.sqlite`, tables `session`/`message`/`part`) rather
    than date-foldered JSONL, and merges durable, gated, evidenced learnings into `~/.zcode/AGENTS.md`
    (capped at 100 lines) plus `~/.zcode/docs/`. Runs every 2 days via a ZCode scheduled automation;
    excludes its own automation runs by joining against `automation_runs.session_id` in
    `~/.zcode/v2/tasks-index.sqlite`, and strips ZCode-specific injected noise (TodoWrite reminders,
    `userselect` IDE pastes, `[$skill](path)` prefixes, `<scheduled-task>` wrappers). The file's trailing
    "Deployment notes" section documents the exact schedule and automation prompt used to redeploy it.
- **`hinsighter/`** — the detailed operating protocol for the Hindsight MCP memory server. Documents the
  tool surface (`memoryRecall`, `memoryRetain`, `memorySyncRetain`, `memoryReflect`), the required
  `bank_id` on every call, bank definitions, decision gates for _should I recall / reflect / retain_,
  tagging conventions, and hard prohibitions (never store credentials, never fabricate a recall).
- **`ssd-backup/`** — backs up media from `~/Downloads` on the `hplaptop` host to a `Movies Backup`
  folder on an external USB SSD, then ejects it. Unlike the other entries this is an operational skill,
  not a persona: `scripts/ssd-backup.sh` is streamed to the host over `ssh bash -s` and does the whole
  run — mount by filesystem UUID, additive `rsync --ignore-existing` copy with no `--delete`, `sync`,
  unmount, power-off. The guardrails are in the script rather than in prose, because the drive holds the
  only copy of the data: it refuses to write unless the expected UUID is mounted read-write, never
  formats/repairs/deletes/overwrites, never removes source files, unmounts on any unexpected exit, and
  leaves checksum verification opt-in (`--verify`) since re-reading every byte wears the SSD. Documents
  the one-time polkit rule that lets `udisksctl` mount and eject from a non-interactive SSH session.
- **`search/`** — a factual search assistant persona. Accuracy first: never fabricate facts, statistics,
  names, dates, quotes, or sources; cross-check before answering; prefer primary/peer-reviewed/official
  sources and name them; admit uncertainty outright; lead with the answer; flag when information may be
  outdated or contested. Also carries auto-recall/auto-store memory rules.

## Cherry Studio prompt hill-climbing

`tools/cherry-hillclimb/` is a self-contained Node harness that improves a Cherry Studio assistant's
system prompt over time by mining its own recent chat history for durable, evidenced learnings — a small
daily "hill-climb" loop, not an automatic rewrite. See
[`tools/cherry-hillclimb/README.md`](tools/cherry-hillclimb/README.md) for exact run instructions,
environment variables, troubleshooting, and the operational decisions (model choice, debug-port launch
method, assistant-resolution gotchas) made while building and live-testing it.

Each day, `propose` (1) reads the assistant's live system prompt and the last 24h of its conversations
straight out of the running app over the Chrome DevTools Protocol, (2) sends both to an analyzer persona
(`skills/hill-climb/cherry-studio-personal-prompt-hillclimb.md`) via Cherry Studio's own local API server,
which returns gated, evidenced learnings and — only when confirmed learnings justify it — a candidate
prompt, and (3) writes `current.md`, `candidate.md`, and a dated report under `prompts/cherry-studio/…`
and `reports/cherry-hillclimb/` for you to review. Nothing is written back to the app until you run
`apply`, and `apply` refuses to run if the live prompt has drifted since the proposal (e.g. you edited it
in the UI meanwhile) or if verification after the dispatch doesn't match, rolling back in that case.

```bash
export CHERRY_API_KEY=cs-sk-…      # Cherry Studio → Settings → API Server, or ~/.cherry-hillclimb.env
npm run cherry:debug               # relaunch Cherry Studio with a loopback-only CDP debug port
npm run cherry:propose             # extract + analyze; writes candidate.md + a report, applies nothing
npm run cherry:diff                # print the current.md → candidate.md diff
npm run cherry:apply               # push the reviewed candidate.md into the live assistant
```

All four `cherry:*` scripts default to the assistant named `Personal`; pass `-- --assistant "Name"` to
target another one. `propose` also takes `-- --hours 24` (lookback window) and `-- --model <id>` (defaults
to a verified-compliant model, currently `gpt-5.6-terra` — see `tools/cherry-hillclimb/README.md` for why
this isn't simply the first model Cherry Studio's API server reports). The evidence gate is enforced
twice — once by the analyzer persona's instructions, once programmatically in `analyze.mjs`, which drops
any "confirmed" learning whose quoted evidence cannot be found verbatim in the extracted transcript before
it's allowed to justify a prompt edit.

## Hindsight benchmark suite

`tools/hindsight-bench/` is a Python-stdlib benchmark harness for Hindsight memory
operations and OpenRouter rerankers, built while selecting the Hindsight model stack
(retain extraction, long-journal chunking, context limits, recall phase tracing,
reranker quality/latency, candidate caps). Offline mode is deterministic and needs
no network or credentials; live suites are gated behind explicit flags and cost
money. The measured 2026-08-29/30 results live in the suite's
[`reports/`](tools/hindsight-bench/reports/2026-08-29-30-historical-results.md).

```bash
cd tools/hindsight-bench
python3 hindsight_bench.py validate
python3 hindsight_bench.py run --mode offline --suite all
python3 -m unittest discover -s tests -t . -v
```

## Commands

Node **26** (see `.nvmrc`; enforced by `engines.node` in `package.json`).

```bash
npm install       # install dependencies, enable the .githooks/pre-commit formatting guard
npm run format    # prettier --write .   (npm run format:check to verify only)
```

### Commit-time formatting guard

`npm install` / `npm ci` enables the repository's `.githooks/pre-commit` hook. It formats staged
Prettier-supported files and re-stages them before the commit is created; `.prettierignore` protects
hand-authored prose in `prompts/`, `reports/`, and `skills/`.
