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
  hinsighter/SKILL.md
  search/SKILL.md
apps/
  report-card/              Vite + React + TypeScript site that renders the report card
.github/workflows/deploy.yml   CI on every PR; build + deploy on every push to main
```

## Skills

Point a tool's system prompt at a `skills/*/SKILL.md` file to apply that behavior.

- **`alfred/`** — baseline behavior rules applied to every conversation, whatever the topic. Three rules:
  route all long-term memory through the Hindsight MCP server (including bank selection across `health`,
  `career`, `finances`, `work`, `default`), keep output concise and free of preamble, and stay
  epistemically honest — search before guessing, label speculation, and say "I don't know" when that is
  the truthful answer.
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
