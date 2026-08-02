# llm-skills

Two things live here:

1. **Reusable LLM skills** (`skills/`) — system-prompt definitions injected into LLM tools and apps
   (Claude Code, Claude Desktop, Cherry Studio, …).
2. **The LLM Report Card** (`LLM_REPORT_CARD.md` + `apps/report-card/`) — a running per-model log of
   observed strengths and weaknesses, built into a static site and published to GitHub Pages at
   <https://sawlemon.github.io/llm-skills/>.

> These notes are subjective personal observation from day-to-day use — not benchmark data, not measurements.

## Layout

```
LLM_REPORT_CARD.md          single source of truth for the site (stays at the repo root)
skills/
  alfred/SKILL.md
  hill-climb/SKILL.md
  hinsighter/SKILL.md
  search/SKILL.md
apps/
  report-card/              Vite + React + TypeScript site that renders the report card
tools/
  cherry-hillclimb/         daily prompt hill-climbing harness for a Cherry Studio assistant (see below)
prompts/
  cherry-studio/<slug>/     current.md, candidate.md, history/, CHANGELOG.md per assistant (cherry-hillclimb output)
reports/
  cherry-hillclimb/         one dated report per propose run (learnings kept/rejected, diff)
.github/workflows/deploy.yml   CI on every PR; build + deploy on every push to main
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
  - `cherry-studio-personal-prompt-hillclimb.md` — a different kind of persona: not a coding-agent
    instruction file but the exact system prompt sent to an LLM by `tools/cherry-hillclimb/analyze.mjs`
    (see "Cherry Studio prompt hill-climbing" below). Analyzes one Cherry Studio assistant's own recent
    chat history and proposes a justified edit to its own system prompt.
- **`hinsighter/`** — the detailed operating protocol for the Hindsight MCP memory server. Documents the
  tool surface (`memoryRecall`, `memoryRetain`, `memorySyncRetain`, `memoryReflect`), the required
  `bank_id` on every call, bank definitions, decision gates for _should I recall / reflect / retain_,
  tagging conventions, and hard prohibitions (never store credentials, never fabricate a recall).
- **`search/`** — a factual search assistant persona. Accuracy first: never fabricate facts, statistics,
  names, dates, quotes, or sources; cross-check before answering; prefer primary/peer-reviewed/official
  sources and name them; admit uncertainty outright; lead with the answer; flag when information may be
  outdated or contested. Also carries auto-recall/auto-store memory rules.

## The report card

`LLM_REPORT_CARD.md` is the **single source of truth**. There is no database and no CMS — the Vite build
reads the markdown, parses it, and inlines the result as the `virtual:report-card` module
(`apps/report-card/src/data/reportCardPlugin.ts`). Every push to `main` redeploys the site from that file,
so editing the markdown is the only step needed to update the published page.

A malformed report card **fails the build** with the offending line number, rather than silently shipping a
broken page. The same parser runs under `npm test`, so problems surface locally too.

### Commit-time formatting guard

`npm install` / `npm ci` enables the repository's `.githooks/pre-commit` hook. It formats staged
Prettier-supported files and re-stages them before the commit is created; `.prettierignore` still
protects source-of-truth prose such as `LLM_REPORT_CARD.md`. GitHub Actions keeps the final
`format:check` as a backstop for commits made with hooks bypassed or from another environment.

### Authoring an observation

The structure is provider → model → aspect table:

```markdown
## Anthropic

### Claude Opus 5

| Aspect | Pros | Cons |
|---|---|---|
| Reasoning | holds a long chain without drifting | |
| Coding | strong refactors; self-verifies with tests | over-eager on unrequested cleanup |
| Instruction-following | | |
| Tool use / agentic | | |
| Context handling | | |
| Speed / latency | | |
| Cost / efficiency | | |
| Refusals / safety behavior | | |
| Formatting / output quality | | |
| Other | | |
```

Rules the parser enforces:

- `##` is the provider heading, `###` is the model heading. A table must follow a model heading.
- Columns must be exactly `Aspect | Pros | Cons`, in that order.
- Strengths go in `Pros`, weaknesses in `Cons`. Never mix the two.
- Multiple notes in one cell are separated by **semicolons** (`;`). Semicolons inside parentheses are
  ignored, so `foo (a; b); bar` is two notes, not three. Empty cells are fine.
- Aspect names are **validated against a canonical list** and anything else is a build error. The list is
  `CANONICAL_ASPECTS` in `apps/report-card/src/data/types.ts`:
  `Reasoning`, `Coding`, `Instruction-following`, `Tool use / agentic`, `Context handling`,
  `Speed / latency`, `Cost / efficiency`, `Refusals / safety behavior`, `Formatting / output quality`,
  `Other`. A near miss (differing only in case or whitespace) is reported with the intended name
  suggested, so `tool use/agentic` tells you to write `Tool use / agentic`. To add a genuinely new aspect,
  extend `CANONICAL_ASPECTS` first.
- Fenced code blocks are stripped before parsing, which is why the template in the file's own
  "How to use" section is not treated as data.

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

## Commands

Node **26** (see `.nvmrc`; enforced by `engines.node` in `package.json`) and npm workspaces.

```bash
npm install       # install root + workspace dependencies
npm run dev       # dev server for the report-card site; edits to LLM_REPORT_CARD.md hot-reload
npm run validate  # parse LLM_REPORT_CARD.md and report schema errors as file:line
npm test          # vitest — parser grammar (fixtures) + component tests
npm run lint      # eslint (flat config, typescript-eslint + react-hooks + react-refresh)
npm run format    # prettier --write .   (npm run format:check to verify only)
npm run build     # tsc -b && vite build → apps/report-card/dist
```

CI runs `lint`, `format:check`, `validate`, `test`, and `build` on every pull request against `main`;
pushes to `main` additionally deploy `apps/report-card/dist` to GitHub Pages.

Editing `LLM_REPORT_CARD.md` cannot break the test suite — tests assert against fixtures, and the live
document is only checked for invariants that hold for any valid card. A genuine schema error fails
`npm run validate` (and the build) with a line number instead.
