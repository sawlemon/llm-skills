# llm-skills

Reusable LLM skills (`skills/`) — system-prompt definitions injected into LLM tools and apps
(Claude Code, Claude Desktop, …) — plus tooling that maintains some of them.

> The LLM Report Card previously lived here; it now has its own repository at
> [sawlemon/llm-reportcard](https://github.com/sawlemon/llm-reportcard), published to
> <https://sawlemon.github.io/llm-reportcard/>.

## Layout

```
skills/
  big-brain/SKILL.md
  critic/SKILL.md
  grill-me/SKILL.md
  grilling/SKILL.md
  hill-climb/SKILL.md
  i-have-adhd/SKILL.md
  research/SKILL.md
tools/
  hindsight-bench/          reproducible Hindsight retain/recall/reranker benchmark suite (see below)
```

## Skills

Point a tool's system prompt at a `skills/*/SKILL.md` file to apply that behavior.

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
  - `zcode-learning-extraction.md` — the ZCode variant: audits **ZCode** session transcripts stored in a
    local SQLite database (`~/.zcode/cli/db/db.sqlite`) and merges durable, gated, evidenced learnings
    into `~/.zcode/AGENTS.md` (capped at 100 lines) plus `~/.zcode/docs/`. Runs every 2 days via a ZCode
    scheduled automation with `injectAgentsMd: false`. The transactional runner at
    `skills/hill-climb/scripts/zcode_learning_extractor.py` handles session discovery, evidence
    normalization, staging, validation, backup, commit, recovery, lock management, and deployment
    checking. Both SQLite databases are opened read-only; evidence is hash-pinned and bound to
    runner-controlled trusted state outside the agent-editable run directory; every live write is
    preflighted, validated, and backed up before the watermark advances. The runner is recoverable, not
    atomic. See the prompt's deployment appendix, the runner's module docstring, and
    `tests/test_zcode_learning_extractor.py` (121 tests) for the full trust model.
- **`critic/`** — a read-only reviewer for completed code, websites, documents, writing, and prompts.
  Scores professional readiness out of 10 and returns only evidence-backed improvements, ordered by
  impact. It requires rendered inspection for work whose presentation or interaction affects quality and
  refuses to score when required visual evidence is unavailable.
- **`big-brain/`** — an explicitly invoked orchestration mode that preserves the main top-tier model for
  critical decisions while delegating token-heavy exploration and consolidation to Luna, and code or
  reasoning-heavy execution to Sonnet. It requires complete task contracts, parallelizes independent work,
  and keeps final review and responsibility with the main model.

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
hand-authored prose in `skills/`.
