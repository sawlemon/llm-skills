# Daily Claude Code Learning Extraction → Codex Global Memory (v3)

You are auditing **Claude Code** session transcripts to extract **durable, reusable
learnings** and merge them into the **Codex** global memory, which is organized as a **map
plus a system of record** (see "Memory model" below). The *source* is Claude Code's session
logs; the *destination* is Codex's `~/.codex/AGENTS.md` map and `~/.codex/docs/` tree. You
do not append to one ever-growing file — you maintain a small, always-on map and a set of
deeper docs it points to.

## Operating principle (read first)
The "score" of this job is the global memory. That metric is trivially gameable: the
cheap way to look productive is to add plausible-sounding learnings. So the primary
failure mode is **not** a lazy extractor — it is a *productive-looking* one that pads the
memory with weak, unverified, or task-specific entries until it rots into a manual nobody
(human or agent) can use.

Three ideas govern everything here:
- **Map, not manual.** `AGENTS.md` is a table of contents, not an encyclopedia. It stays
  **≤ 100 lines**, always. When everything is "important," nothing is; a giant file
  crowds out the task and rots into stale rules.
- **Progressive disclosure.** The agent starts from a small, stable entry point (the map)
  and is told *where to look next*. Detail lives in deeper docs, read on demand.
- **What the agent can't see doesn't exist.** Every learning must live in a versioned,
  repository-local file (markdown). If it isn't written down here, it's invisible to
  future sessions — so write the *right* things, in the *right* place, and no filler.

There is **no quota**. Zero merges is a correct, successful run when nothing durable
happened. Fewer, sharper, well-evidenced learnings beat more, weaker ones — always.

> **Source vs. destination — do not confuse them.** You *read* from Claude Code
> (`~/.claude/projects/**`) and you *write* to Codex (`~/.codex/AGENTS.md`,
> `~/.codex/docs/`, `~/.codex/AGENTS.extraction-log.md`). Never write learnings back into
> `~/.claude`, and never treat Codex's own logs as the source for this job.

---

## Memory model (the Codex structure you maintain)

```
~/.codex/
├── AGENTS.md                     # THE MAP — ≤100 lines, injected into every session
│                                 #   (1) a small set of always-on universal rules
│                                 #   (2) an index of pointers: "for X, see docs/…"
├── docs/                         # SYSTEM OF RECORD — read on demand via the map
│   ├── index.md                  #   catalog: every doc + one-line purpose + updated date
│   ├── environment.md            #   OS/shell, machines, SSH aliases, always-available tools
│   ├── coding-preferences.md     #   languages, libs to prefer/avoid, style, testing
│   ├── workflow-and-commands.md  #   standard flags, dry-run rules, git/PR conventions
│   ├── tooling-gotchas.md        #   portability quirks, auth quirks, commands that fail
│   └── projects/<project>.md     #   global-relevant notes/pointers per project (index only)
└── AGENTS.extraction-log.md      # append-only ledger (bookkeeping — never behavioral)
```

**`AGENTS.md` contains only two things and nothing else:**
1. **Always-on rules** — a *short* list (aim ≤ ~25 lines) of universal, high-frequency,
   high-cost-if-wrong rules, one line each. These are the things worth spending permanent
   context on in every session.
2. **Index / where-to-look** — one pointer per docs file, each with a *trigger*:
   `- Coding conventions → docs/coding-preferences.md  (consult before writing code)`.
   The trigger tells the agent *when* to open it. This is the progressive-disclosure hinge.

Everything else — the bulk of learnings — lives in the matching `docs/` file, not in the
map. The map only needs a pointer to the *category*, which usually already exists.

---

## Placement rule (map vs. doc) — apply to every learning that will be written

- Put a learning in the **always-on map** only if **all** are true: it applies to nearly
  every session; it fits in one line; and getting it wrong is expensive. Keep this set
  deliberately small.
- Otherwise → append it to the appropriate **`docs/` file** and make sure the map has a
  pointer to that file's category (add the pointer if missing).
- **The ≤100-line cap is inviolable.** If adding to the map would exceed it, **demote**
  the least-universal current always-on line(s) into their `docs/` file and rely on the
  pointer. The map never grows past a map.

---

## Scope
- Runs **daily**; review only sessions worked on in the **last 24 hours**.
- In scope: projects under `~/Downloads/Personal` or `~/Downloads/Work`.
- **Source logs live under `~/.claude/projects/**`** (Claude Code); each project maps to
  one subfolder whose name is the project's real path with `/` replaced by `-`. Filter to
  in-scope projects by matching `Downloads-Personal` / `Downloads-Work` as a substring of
  the encoded dir name. Ignore anything older than 24h, outside those roots, or under any
  `subagents/` path.

---

## Step 0 — Discover in-scope Claude Code sessions (portable, **do this in Python**)

> ⚠️ Do **not** use a raw `find` one-liner. `-printf`/`-newermt` are GNU-only; on
> macOS/BSD they fail, and because such pipelines end in `sort` (exit 0), an `||`
> fallback never fires — you get **zero results and no error**, so the job "succeeds"
> daily while learning nothing. The script below is correct on both Linux and macOS.

```python
import os, sys, time
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
PROJECTS = HOME / ".claude" / "projects"     # SOURCE: Claude Code logs
WINDOW = 24 * 60 * 60
SCOPE_MARKERS = ("Downloads-Personal", "Downloads-Work")
now = time.time()

def in_scope(name: str) -> bool:
    return any(m in name for m in SCOPE_MARKERS)

sessions = []
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

sessions.sort(key=lambda s: s[0], reverse=True)
if not sessions:
    print("NO_IN_SCOPE_SESSIONS"); sys.exit(0)

by_project = defaultdict(list)
for mt, path, proj in sessions:
    by_project[proj].append((mt, path))
for proj, files in by_project.items():
    print(f"\n## {proj}  ({len(files)} session[s])")
    for mt, path in files:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}  {path}")
```

If it prints `NO_IN_SCOPE_SESSIONS`: report that no in-scope sessions were worked on
today, make no edit, and stop. Review **all** sessions in the window — do not truncate.

---

## Step 1 — Parse transcripts (one batched Python pass, not manual reading)

Each Claude Code `.jsonl` line is a JSON object with a `type` (`user`, `assistant`,
`system`, `summary`, `attachment`, `file-history-snapshot`, tool events…). The real
conversation is in `type:"user"` / `type:"assistant"` lines, each carrying a nested
`message` object: `message.role` plus `message.content`, which is **either a plain string
or a list of blocks** (`{"type":"text","text":…}`, `{"type":"tool_use",…}`,
`{"type":"tool_result",…}`). Each line also carries useful context keys like `cwd`,
`gitBranch`, `sessionId`, and `timestamp`.

Parse defensively (`json.loads` + `.get`); skip malformed lines; handle `content` being a
`str` *or* a `list`. Per session reconstruct: user asked → what was tried → what failed →
what worked → what the user **corrected** or explicitly stated as a preference/fact. Flag
correction signals: `"no, always…"`, `"don't…"`, `"actually use…"`, `"in future…"`,
`"remember…"`, reverting/moving your output, restating a rule after you broke it. Collect
**candidate learnings** into one working list before touching any file.

```python
import json

def blocks_to_text(content):
    """Claude content is a str or a list of typed blocks; return plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                out.append(b.get("text", ""))
            elif b.get("type") == "tool_result":
                r = b.get("content", "")
                out.append(r if isinstance(r, str) else json.dumps(r)[:500])
        return "\n".join(out)
    return ""

def iter_turns(path):
    """Yield (role, text) for real user/assistant turns; skip system/meta lines."""
    for line in open(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("type") not in ("user", "assistant"):
            continue
        msg = o.get("message", {})
        if not isinstance(msg, dict):
            continue
        txt = blocks_to_text(msg.get("content", "")).strip()
        if txt:
            yield msg.get("role", o["type"]), txt
```

---

## Step 2 — Gate every candidate

A candidate advances only if it passes **all** gates (each is a defense against padding):

- **Gate 1 — Evidence.** Carries its exact evidence (session file + the specific
  turn/signal) and is phrased as a checkable claim. No evidence → not a candidate. Never
  write anything you're inferring rather than seeing.
- **Gate 2 — Generalization.** State it as a rule *without referring to the task it came
  from*. If it only makes sense in that task's context, it's a task-specific artifact —
  drop it.
- **Gate 3 — Correction vs. noise.** Is it a generalized instruction ("always/never…") or
  a one-time annoyance? Is it about the user's preference, or merely a tool/environment
  failure (which is not a fact about the user)? Only generalized behavioral corrections
  qualify.
- **Gate 4 — Smallest general rule the evidence supports.** Generalize enough to reuse,
  never more than the evidence licenses. If unsure how broadly it applies, scope narrow
  and mark provisional.
- **Gate 5 — Global vs. project-local.** "Would this be true in a *different* project?"
  If no → it belongs in `docs/projects/<project>.md` or that project's own repo
  `AGENTS.md`, not the global map.
- **Gate 6 — Tool-portability.** The learning comes from a Claude Code transcript but must
  hold for **Codex**. Drop or reword anything that is Claude-CLI-specific (a Claude-only
  command, flag, slash-command, or subagent mechanic) unless the *underlying* preference is
  tool-agnostic. Capture the durable intent, not the Claude-specific surface.

**Phrasing:** imperative + scoped — *what to do* and *when it applies*, one line where
possible, rationale only if non-obvious. Then **dedupe candidates against each other**
(a learning seen in two sessions is one entry, and that counts toward confirmation).

---

## Step 3 — Confidence tiers (confirmation ladder)

- **Confirmed** — user explicitly stated it as a rule, **or** corroborated across **≥2
  sessions/instances**. → Eligible to write.
- **Provisional** — inferred from a single instance / ambiguous signal. → Do **not**
  write it into the map or docs. Record it in the ledger (Step 7); promote to Confirmed
  only when it recurs or the user states it. A prior provisional that recurs today is
  promoted and written now (note the promotion in the summary).

---

## Step 4 — Read the current Codex memory, then back it up
Read `~/.codex/AGENTS.md` **and** `~/.codex/docs/index.md` (and any docs file you'll touch)
in full before editing, so you understand the current map, structure, and tone. If the
structure doesn't exist yet, create it from the layout above. Back up the whole tree:
`cp -R ~/.codex/AGENTS.md ~/.codex/docs ~/.codex/backup-$(date +%Y%m%d)/` (skip files that
don't exist yet).

---

## Step 5 — Place & merge each Confirmed learning (never append blindly)
For each, apply the **placement rule**, then classify against the existing Codex content
and act as a discrete, described, revertable change:

- **Duplicate** (already captured anywhere in `~/.codex`, even if worded differently) →
  skip; note it.
- **Refinement** (adds scope to an existing entry) → edit that entry in place.
- **Contradiction / supersession** (preference changed, path moved, tool swapped) →
  **replace** the old entry wherever it lives; don't keep both versions.
- **Genuinely new** → write it to its placed location (map *or* docs file); if it's a new
  docs file, add it to `~/.codex/docs/index.md` **and** add a pointer in the map.

Tag new/changed entries with a trailing `(updated YYYY-MM-DD)`.

---

## Step 6 — Garbage-collect the knowledge base (doc-gardening)
Run this every time; it's what keeps the map a map and the docs trustworthy:

- **Enforce the ≤100-line map cap.** Count `~/.codex/AGENTS.md` lines. If over, demote the
  least-universal always-on rules into their `docs/` file (relying on the pointer) until
  it fits. The cap wins over convenience.
- **Consolidate.** Merge redundant entries; delete superseded ones. Tech debt in a
  knowledge base compounds — pay it down in small daily increments, not painful bursts.
- **Cross-link integrity.** Every pointer in the map must resolve to an existing docs
  file; every docs file must be reachable from the map/index (no orphans, no dangling
  links).
- **Index accuracy.** `~/.codex/docs/index.md` lists every docs file with a one-line
  purpose and its last-updated date; reconcile it with what actually exists.
- **Freshness.** Flag entries/docs untouched for a long time, or that recent sessions
  appear to contradict, for review (note them in the summary rather than deleting blindly).

---

## Step 7 — Update the extraction ledger (record rejections as carefully as merges)
Append to `~/.codex/AGENTS.extraction-log.md` (append-only, kept **out** of the
behavioral files on purpose). One line per candidate:

```
## <YYYY-MM-DD> run
- [WROTE-MAP]      <rule>                | src <project> <ts> | Confirmed
- [WROTE-DOC]      <rule> → docs/<file>  | src … | Confirmed
- [DEMOTED]        <rule> map → docs/<file>  | to keep map ≤100 lines
- [SUPERSEDED]     <old entry> (@ <where>) | replaced by the line above
- [PROVISIONAL]    <rule>                | 1 instance; awaiting corroboration
- [PROMOTED]       <rule>                | provisional since <date>, recurred today
- [SKIPPED-dup]    <rule>                | already in <where>
- [PROJECT-LOCAL]  <rule>                | belongs in <project>
- [REJECTED]       <candidate>           | failed Gate <n>: <reason>
```

This stops the run re-litigating the same skips daily, gives an audit trail, and — with
the backup — lets an interrupted run resume immediately.

---

## Step 8 — Verify the write
Re-read and confirm:
- `~/.codex/AGENTS.md` is **≤ 100 lines** and contains only always-on rules + the index.
- Each intended change is present and correctly worded; nothing was accidentally deleted
  or duplicated; headings/structure intact.
- **Every map pointer resolves**; `~/.codex/docs/index.md` matches the files on disk; no
  orphan docs.
- **No secret, token, or credential value** was written anywhere.
If anything is wrong, restore from the backup and redo rather than leave a half-applied
merge.

---

## Step 9 — Summarize to the user (honest; never rewrite silently)
Grouped by project: one line per candidate with disposition, **where it landed** (map vs
which doc), confidence, and source (Claude project + session ts). Flag genuinely ambiguous
cases for the user rather than resolving them silently; never present an inference as fact.
End with the current `~/.codex/AGENTS.md` line count (e.g. "map: 82/100 lines"), a tally,
and the backup path.

---

## Guardrails
- **Read Claude, write Codex.** Source = `~/.claude/projects/**`; destination =
  `~/.codex/AGENTS.md` + `~/.codex/docs/`. Never write into `~/.claude`.
- **Map ≤ 100 lines, always.** If it won't fit, demote to docs — never grow the map.
- **No quota; padding is the worst outcome.** An empty run is a correct run.
- Everything durable must live in a versioned file — if the agent can't see it, it
  doesn't exist. Never rely on memory outside these files.
- **Never fabricate** a learning not clearly evidenced in a transcript.
- **Never store secrets/tokens/credentials verbatim** — reference existence + location.
- Keep project-local detail out of the global map/docs (index-only pointers at most).
- Never delete a whole section/doc except as a clear supersession; never overwrite without
  a backup and a diff summary.
- If nothing durable was found, say so and make no edit.

## Failure modes this prompt actively prevents
1. Silent no-op discovery on macOS/BSD (Step 0 is Python).
2. **Writing to the wrong tree** — learning back into `~/.claude` instead of `~/.codex`
   (explicit source/destination split).
3. **`AGENTS.md` bloating back into a 1,000-page manual** (hard ≤100-line cap + demotion).
4. Padding the memory with plausible-but-weak learnings (no-quota + the gates).
5. A single ambiguous signal hardening into a permanent misfiring rule (confidence ladder).
6. Task-specific artifacts leaking in as if durable (generalization gate).
7. **Claude-CLI-specific mechanics leaking into a Codex rule** (tool-portability gate).
8. Mistaking a tool/infra failure for a user preference (correction-vs-noise gate).
9. Dangling pointers / orphan docs / a stale index (cross-link + index checks).
10. Duplicate accumulation and compounding knowledge-base debt (daily garbage collection).
11. Stale/contradictory entries kept side by side (supersession replaces, not stacks).
12. Re-litigating the same rejected candidate daily (the extraction ledger).
13. Secrets written verbatim; silent overwrites; hallucinated learnings.
