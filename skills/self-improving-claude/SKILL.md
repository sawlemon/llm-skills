# Daily Claude Code Learning Extraction → Global `~/.claude/CLAUDE.md`

You are auditing Claude Code session transcripts to extract **durable, reusable
learnings** and merge them into the global memory file at `~/.claude/CLAUDE.md`.

## Purpose & success criteria

The point of this job is not to log activity — it is to make **future** Claude Code
sessions measurably better by maintaining one high-signal, deduplicated, actionable
memory file. A run is successful when, at the end:

- Every learning added is something future-Claude can **act on** (a rule, not an
  observation), phrased with a clear trigger.
- Nothing is duplicated, and anything a new session contradicts has been **replaced**,
  not stacked on top of.
- The global file stays **terse** and free of project-local noise.
- The user can see exactly what changed and why (a diff summary), and could revert it.

If a run adds three vague lines and two duplicates, it has made things *worse* — bias
toward extracting fewer, sharper learnings over more, weaker ones.

## Scope

- Runs **daily**. Review only sessions worked on in the **last 24 hours**.
- In scope: projects that live under `~/Downloads/Personal` or `~/Downloads/Work`.
- Session logs live under `~/.claude/projects/**` (Claude's own metadata store). Each
  project maps to one subfolder whose name is the project's real path with `/` replaced
  by `-` (e.g. `~/Downloads/Work/foo` → a dir like `-Users-<you>-Downloads-Work-foo`).
  Filter to in-scope projects by matching `Downloads-Personal` / `Downloads-Work` as a
  substring of the encoded dir name.
- Ignore anything older than 24h, outside those two roots, or under any `subagents/` path.

---

## Step 0 — Discover in-scope sessions (portable, **do this in Python**)

> ⚠️ Do **not** use a raw `find` one-liner for this. `-printf` and `-newermt` are
> GNU-only; on macOS/BSD they fail, and because such pipelines end in `sort` (which
> exits 0), an `||` fallback chain never triggers — you get **zero results and no error**.
> The job then "succeeds" daily while learning nothing. Use the script below; it is
> correct by construction on both Linux and macOS.

```python
import os, sys, time
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"
WINDOW = 24 * 60 * 60
SCOPE_MARKERS = ("Downloads-Personal", "Downloads-Work")

now = time.time()

def in_scope(name: str) -> bool:
    return any(m in name for m in SCOPE_MARKERS)

sessions = []  # (mtime, path, project_dir_name)
if PROJECTS.is_dir():
    for proj in PROJECTS.iterdir():
        if not proj.is_dir() or not in_scope(proj.name):
            continue
        for f in proj.rglob("*.jsonl"):
            if "subagents" in f.parts:
                continue
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if now - mt <= WINDOW:
                sessions.append((mt, str(f), proj.name))

sessions.sort(key=lambda s: s[0], reverse=True)  # newest first

if not sessions:
    print("NO_IN_SCOPE_SESSIONS")
    sys.exit(0)

by_project = defaultdict(list)
for mt, path, proj in sessions:
    by_project[proj].append((mt, path))

for proj, files in by_project.items():
    print(f"\n## {proj}  ({len(files)} session[s])")
    for mt, path in files:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}  {path}")
```

If it prints `NO_IN_SCOPE_SESSIONS`: **report that no in-scope sessions were worked on
today, make no edit, and stop.** Do not fabricate learnings to fill an empty run.

Group results by project directory (already grouped above) so each learning can be
attributed to its source. Review **all** sessions in the window — do not truncate.

---

## Step 1 — Parse transcripts (one batched Python pass, not manual reading)

Each `.jsonl` line is a JSON object with a `type` (`user`, `assistant`, `system`,
`summary`, tool events, etc.). Parse defensively with `json.loads` — schemas vary
across Claude Code versions, so use `.get(...)` everywhere and skip malformed lines.

For **each** session, reconstruct the arc:

> user asked → what was tried → what failed → what finally worked → what the user
> **corrected** or explicitly stated as a preference/fact.

Extract into a readable, ordered reconstruction per session:

- user text turns (verbatim-ish, trimmed),
- assistant text turns (trimmed),
- `tool_use` name + a short summary of the input,
- `tool_result` outcome (ok/error + first ~200 chars).

Pay special attention to **correction and preference signals**, e.g.:
`"no, always…"`, `"don't do X"`, `"actually use…"`, `"in future…"`, `"remember that…"`,
`"that's wrong"`, a user reverting/moving something Claude produced, or the user
restating a rule after Claude broke it.

Run this over the whole day's files in one script and collect **candidate learnings**
into a single working list before touching `CLAUDE.md`.

---

## Step 2 — Extract only durable, high-value learnings

A candidate qualifies only if it is **all three**: new, durable (useful in a *future,
different* session), and specific (concrete enough to act on). When in doubt, drop it.

### What to extract

- Corrections to your approach ("always do X instead of Y").
- Stable facts about the user, their machines, hosts, tools, or workflow (incl. aliases
  like "when I say <term>, use SSH host <host>").
- Stable preferences (formatting, tone, libraries/tools to prefer or avoid, testing).
- Gotchas/pitfalls **likely to recur** (a command that fails a certain way, an auth
  quirk, a path that moved, a portability trap).
- New/renamed projects, paths, hosts, or credential *locations* (never values).

### What to exclude

- One-off task specifics and transient debugging details.
- Anything already in `CLAUDE.md` (even worded differently).
- Anything **project-local** — it belongs in that project's own `CLAUDE.md`, not global.
- Anything you're inferring rather than seeing clearly evidenced. If unsure, skip it (or
  flag it as low-confidence in the summary), but don't write it.

### Phrase every learning as an actionable rule

This is what makes the file improve your sessions instead of just growing. Each learning
should be **imperative + scoped** — say *what to do* and *when it applies* — one line
where possible, with a short rationale only if non-obvious.

| ❌ Weak / rejected | ✅ Rewritten |
|---|---|
| "User likes clean code." | "Prefer the Python standard library; don't add third-party deps or a venv unless asked." |
| "Fixed the auth bug today." | *(one-off — exclude)* |
| "Be careful with find." | "This machine uses BSD/macOS `find`; GNU-only flags (`-printf`, `-newermt`) fail silently — use Python or `stat -f` for portable file discovery." |
| "User mentioned their laptop." | "When the user says 'HP laptop', operate over SSH host `hplaptop`." |
| "Ran a script with a flag." | "Run destructive/queue scripts with `--dry-run` first and pass `--bank` explicitly." |

### The global vs. project-local test

For each candidate ask: *"Would this be true and useful in a **different** project?"*

- **Yes** → global, eligible for `CLAUDE.md`.
- **No** → project-local. Do **not** add it to the global file; list it in the summary
  under that project as "project-local — belongs in <project>/CLAUDE.md" so the user can
  place it. (Example of local: "teardown docs for repo X go in X/teardown/".)

Before moving on, **dedupe the candidate list against itself** so the same learning
surfacing in two sessions is merged into one entry.

---

## Step 3 — Read the current global file in full

Read `~/.claude/CLAUDE.md` **entirely** before editing so you understand its structure,
headings, and tone. If it doesn't exist, create it using the recommended skeleton below.

Take a timestamped backup before any write so a bad merge is recoverable:
`cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak-$(date +%Y%m%d)` (skip if the file is new).

---

## Step 4 — Classify each candidate, then merge (never append blindly)

For every remaining candidate, classify against the existing file and act:

- **Duplicate** (already captured, even if worded differently) → skip; note in summary.
- **Refinement** (adds scope/specificity to an existing bullet) → edit that bullet in
  place; don't add a second one.
- **Contradiction / supersession** (new info conflicts with existing — preference
  changed, path moved, tool swapped) → **replace** the old content. Do not keep both the
  old and new versions. Optionally append the change date.
- **Genuinely new** → add under the most relevant existing heading; create a new heading
  only if none fits.

**Consolidation pass (every run):** because this runs daily, actively prune. Merge
now-redundant bullets and delete superseded ones so the file trends toward terse and
current, not ever-growing. Preserve existing structure, tables, and tone.

**Lightweight provenance (optional):** append a trailing `(YYYY-MM-DD)` to new/changed
bullets. This lets future runs spot stale entries and avoid re-adding. Keep it to a date
tag — do not build heavy provenance tables that clutter the file.

---

## Step 5 — Verify the write

After editing, **re-read** `CLAUDE.md` and confirm:

- each intended add/change is present and correctly worded,
- no section was accidentally deleted or duplicated,
- the file still parses as the same structure (headings intact),
- **no secret, token, or credential value** was written anywhere.

If anything looks wrong, restore from the backup and redo, rather than leaving a
half-applied merge.

---

## Step 6 — Summarize the diff to the user (never rewrite silently)

Report, **grouped by project**, one line per candidate with its disposition and source:

```
### <project>   (session <YYYY-MM-DD HH:MM>)
- [ADDED]         <learning>
- [CHANGED]       <old> → <new>
- [SUPERSEDED]    <removed old> (replaced by the CHANGED/ADDED line above)
- [SKIPPED-dup]   <learning> (already in <heading>)
- [PROJECT-LOCAL] <learning> — belongs in <project>/CLAUDE.md
- [LOW-CONF]      <learning> — evidence too thin, not written
```

End with a one-line tally (e.g. "3 added, 1 changed, 2 skipped as duplicates, 1
project-local") and the path to the backup you took.

---

## Recommended `~/.claude/CLAUDE.md` structure

Use this skeleton when creating the file, and slot new learnings into these sections so
the file stays discoverable:

```
# CLAUDE.md — Global preferences & learnings

## About me / environment
- OS & shell, machines, SSH host aliases, always-available tooling

## Coding preferences
- Languages; libraries to prefer/avoid; style; testing conventions

## Tone & output
- Formatting, verbosity, when to use artifacts/files

## Workflow & commands
- Standard flags, dry-run rules, git/PR conventions

## Tooling gotchas
- Portability quirks, auth quirks, commands that fail a certain way

## Project registry (index only)
- <name> → <path> → one-line description   # details live in each project's own CLAUDE.md
```

---

## Guardrails

- **Never fabricate** a learning not clearly evidenced in a transcript.
- **Never store secrets/tokens/credentials verbatim** — reference that one exists and
  where it lives, never its value.
- Keep the global file **terse** and free of project-local details.
- Never let the file grow unboundedly — consolidate every run.
- Never delete a whole section unless it's a clear supersession, and never overwrite
  without a backup and a diff summary.
- If nothing durable was found across the day's sessions, say so and make **no edit**.

## Failure modes this prompt actively prevents

1. **Silent no-op discovery on macOS/BSD** — Step 0 uses Python, so the job can't
   "succeed" while finding nothing.
2. **Vague, non-actionable learnings** — Step 2 forces imperative, scoped phrasing.
3. **Duplicate accumulation / file bloat** — Step 4's dedup + consolidation pass.
4. **Stale/contradictory entries kept side by side** — supersession replaces, not stacks.
5. **Project-local noise leaking into global** — the global-vs-local test gates every add.
6. **Secrets written verbatim** — excluded at extraction and re-checked at verification.
7. **Silent overwrites** — mandatory backup + diff summary; changes are reversible.
8. **Hallucinated learnings** — confidence threshold; skip-when-unsure over guess.
