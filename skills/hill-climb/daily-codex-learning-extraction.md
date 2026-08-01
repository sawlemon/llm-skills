# Daily Codex Learning Extraction → Global Memory (v3, Codex)

You are auditing **Codex** session transcripts to extract **durable, reusable
learnings** and merge them into the global memory, which is organized as a **map plus a
system of record** (see "Memory model" below). You do not append to one ever-growing
file — you maintain a small, always-on map (`~/.codex/AGENTS.md`) and a set of deeper docs
it points to.

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

---

## Memory model (the structure you maintain)

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

> **Note on the map's title.** The live `~/.codex/AGENTS.md` currently opens with an H1 that
> reads `# CLAUDE.md — Global Map`. That's a leftover from the Claude setup. If you edit the
> map today, normalize the H1 to `# AGENTS.md — Global Map (sala)`; otherwise leave it and
> note it in the summary. Codex reads `AGENTS.md`, not `CLAUDE.md`.

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
- In scope: projects whose working directory is under `~/Downloads/Personal` or
  `~/Downloads/Work`.
- Codex session logs live at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` (plus
  `~/.codex/archived_sessions/rollout-*.jsonl`). **Unlike Claude, the folder tree is by
  date, not by project** — the project is the `cwd` recorded in each file's first line
  (`type:"session_meta"` → `payload.cwd`). Determine scope by testing whether that `cwd`
  contains `/Downloads/Personal` or `/Downloads/Work` as a substring.
- **Exclude:** any session whose `payload.thread_source == "subagent"` (Codex flags
  subagent runs here — there is no `subagents/` path to match on), anything older than 24h,
  and this job's own runs (skip sessions whose transcript contains the automation id
  `daily-codex-learning-extraction`, so the extractor never learns from itself).

---

## Step 0 — Discover in-scope sessions (portable, **do this in Python**)

> ⚠️ Do **not** use a raw `find` one-liner. `-printf`/`-newermt` are GNU-only; on
> macOS/BSD they fail, and because such pipelines end in `sort` (exit 0), an `||`
> fallback never fires — you get **zero results and no error**, so the job "succeeds"
> daily while learning nothing. The script below is correct on both Linux and macOS and
> reads each file's `session_meta` (line 1) to recover the project `cwd`.

```python
import os, sys, time, json, glob
from pathlib import Path
from collections import defaultdict

HOME = Path.home()
ROOTS = [HOME / ".codex" / "sessions", HOME / ".codex" / "archived_sessions"]
WINDOW = 24 * 60 * 60
SCOPE_MARKERS = ("/Downloads/Personal", "/Downloads/Work")
SELF_ID = "daily-codex-learning-extraction"   # skip this job's own runs
now = time.time()

def read_meta(f):
    """Return (cwd, thread_source, originator) from the session_meta line, or None."""
    try:
        with open(f, "r") as fh:
            o = json.loads(fh.readline())
    except Exception:
        return None
    if o.get("type") != "session_meta":
        return None
    p = o.get("payload", {}) or {}
    cwd = p.get("cwd")
    if isinstance(cwd, dict):          # some builds nest cwd under {"path": ...}
        cwd = cwd.get("path")
    return cwd, p.get("thread_source"), p.get("originator")

def is_self_run(f):
    """Cheap scan: skip our own extraction sessions to avoid a feedback loop."""
    try:
        with open(f, "r") as fh:
            head = fh.read(20000)
    except Exception:
        return False
    return SELF_ID in head

sessions = []
for root in ROOTS:
    if not root.is_dir():
        continue
    for f in glob.glob(str(root) + "/**/*.jsonl", recursive=True):
        try:
            mt = os.stat(f).st_mtime
        except OSError:
            continue
        if now - mt > WINDOW:
            continue
        meta = read_meta(f)
        if not meta:
            continue
        cwd, thread_source, _ = meta
        if not cwd or not any(m in cwd for m in SCOPE_MARKERS):
            continue
        if thread_source == "subagent":
            continue
        if is_self_run(f):
            continue
        sessions.append((mt, f, cwd))

sessions.sort(key=lambda s: s[0], reverse=True)
if not sessions:
    print("NO_IN_SCOPE_SESSIONS"); sys.exit(0)

by_project = defaultdict(list)
for mt, path, cwd in sessions:
    by_project[cwd].append((mt, path))
for cwd, files in by_project.items():
    print(f"\n## {cwd}  ({len(files)} session[s])")
    for mt, path in files:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.localtime(mt))}  {os.path.basename(path)}")
```

If it prints `NO_IN_SCOPE_SESSIONS`: report that no in-scope sessions were worked on
today, make no edit, and stop. Review **all** sessions in the window — do not truncate.

> Optional nicety: `~/.codex/session_index.jsonl` maps each session `id` → `thread_name`.
> The `id` is the trailing UUID in the rollout filename. Join on it to label sessions with
> a human title in your summary instead of the bare filename.

---

## Step 1 — Parse transcripts (one batched Python pass, not manual reading)

Each `.jsonl` line is a JSON object with a top-level `type`. The ones that matter:

- `type:"session_meta"` — line 1 only; `payload.cwd`, `payload.originator`,
  `payload.thread_source`, `payload.cli_version`.
- `type:"response_item"` with `payload.type:"message"` — the model-facing transcript.
  `payload.role` is `user`, `assistant`, or `developer`; `payload.content` is a list of
  `{ "type": "input_text"|"output_text"|"text", "text": ... }`.
- `type:"event_msg"` with `payload.type:"user_message"` (`payload.message`) and
  `payload.type:"agent_message"` (`payload.message`) — the clean user/assistant surface.
- `type:"response_item"` with `payload.type` in `custom_tool_call` / `function_call` /
  `local_shell_call` and their `*_output` — what the agent actually ran and got back.
- `type:"response_item"` with `payload.type:"reasoning"` — model reasoning (context only;
  never quote as a "user preference").

Parse defensively (`json.loads` + `.get`); skip malformed lines. **Strip wrapper/system
noise before treating text as a real user turn:** ignore `developer`-role messages and any
user text that begins with `<app-context>`, `<environment_context>`, `<user_instructions>`,
or `<heartbeat>` (these are injected context and automation triggers, not the human).

Per session reconstruct: user asked → what was tried (tool calls) → what failed (tool
error output) → what worked → what the user **corrected** or explicitly stated as a
preference/fact. Flag correction signals: `"no, always…"`, `"don't…"`, `"actually use…"`,
`"in future…"`, `"remember…"`, reverting/moving your output, restating a rule after you
broke it. Collect **candidate learnings** into one working list before touching any file.

```python
import json

SKIP_PREFIXES = ("<app-context>", "<environment_context>",
                 "<user_instructions>", "<heartbeat>")

def clean_text(payload):
    """Flatten a response_item message payload into plain text."""
    parts = payload.get("content", [])
    if isinstance(parts, list):
        return "".join(c.get("text", "") for c in parts if isinstance(c, dict))
    return payload.get("message", "") or ""

def iter_turns(path):
    """Yield (role, text) for real human/agent turns; skip injected wrappers & tools."""
    for line in open(path):
        try:
            o = json.loads(line)
        except Exception:
            continue
        t, p = o.get("type"), o.get("payload", {}) or {}
        if t == "response_item" and p.get("type") == "message":
            role = p.get("role")
            if role == "developer":
                continue
            txt = clean_text(p).strip()
            if not txt or txt.startswith(SKIP_PREFIXES):
                continue
            yield role, txt
        elif t == "event_msg" and p.get("type") in ("user_message", "agent_message"):
            txt = (p.get("message") or "").strip()
            if not txt or txt.startswith(SKIP_PREFIXES):
                continue
            yield ("user" if p["type"] == "user_message" else "assistant"), txt
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

## Step 4 — Read the current memory, then back it up
Read `~/.codex/AGENTS.md` **and** `~/.codex/docs/index.md` (and any docs file you'll
touch) in full before editing, so you understand the current map, structure, and tone. If
the structure doesn't exist yet, create it from the layout above. Back up the whole tree:
`cp -R ~/.codex/AGENTS.md ~/.codex/docs ~/.codex/backup-$(date +%Y%m%d)/` (skip files that
don't exist yet).

---

## Step 5 — Place & merge each Confirmed learning (never append blindly)
For each, apply the **placement rule**, then classify against the existing content and act
as a discrete, described, revertable change:

- **Duplicate** (already captured anywhere, even if worded differently) → skip; note it.
- **Refinement** (adds scope to an existing entry) → edit that entry in place.
- **Contradiction / supersession** (preference changed, path moved, tool swapped) →
  **replace** the old entry wherever it lives; don't keep both versions.
- **Genuinely new** → write it to its placed location (map *or* docs file); if it's a new
  docs file, add it to `docs/index.md` **and** add a pointer in the map.

Tag new/changed entries with a trailing `(updated YYYY-MM-DD)`.

---

## Step 6 — Garbage-collect the knowledge base (doc-gardening)
Run this every time; it's what keeps the map a map and the docs trustworthy:

- **Enforce the ≤100-line map cap.** Count `AGENTS.md` lines. If over, demote the
  least-universal always-on rules into their `docs/` file (relying on the pointer) until
  it fits. The cap wins over convenience.
- **Consolidate.** Merge redundant entries; delete superseded ones. Tech debt in a
  knowledge base compounds — pay it down in small daily increments, not painful bursts.
- **Cross-link integrity.** Every pointer in the map must resolve to an existing docs
  file; every docs file must be reachable from the map/index (no orphans, no dangling
  links).
- **Index accuracy.** `docs/index.md` lists every docs file with a one-line purpose and
  its last-updated date; reconcile it with what actually exists.
- **Freshness.** Flag entries/docs untouched for a long time, or that recent sessions
  appear to contradict, for review (note them in the summary rather than deleting blindly).

---

## Step 7 — Update the extraction ledger (record rejections as carefully as merges)
Append to `~/.codex/AGENTS.extraction-log.md` (append-only, kept **out** of the
behavioral files on purpose). One line per candidate:

```
## <YYYY-MM-DD> run
- [WROTE-MAP]      <rule>                | src <cwd> <ts> | Confirmed
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
- `AGENTS.md` is **≤ 100 lines** and contains only always-on rules + the index.
- Each intended change is present and correctly worded; nothing was accidentally deleted
  or duplicated; headings/structure intact.
- **Every map pointer resolves**; `docs/index.md` matches the files on disk; no orphan
  docs.
- **No secret, token, or credential value** was written anywhere.
If anything is wrong, restore from the backup and redo rather than leave a half-applied
merge.

---

## Step 9 — Summarize to the user (honest; never rewrite silently)
Grouped by project (`cwd`): one line per candidate with disposition, **where it landed**
(map vs which doc), confidence, and source (project + session ts). Flag genuinely
ambiguous cases for the user rather than resolving them silently; never present an
inference as fact. End with the current `AGENTS.md` line count (e.g. "map: 82/100 lines"),
a tally, and the backup path.

---

## Guardrails
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
2. **Mis-scoping because Codex stores logs by date, not by project** (Step 0 reads
   `session_meta.cwd`, not the folder path).
3. Learning from the extractor's own runs (self-run skip in Step 0) or from subagent
   transcripts (`thread_source == "subagent"` filter).
4. Treating injected `<app-context>` / `<heartbeat>` / `<environment_context>` wrappers as
   real user preferences (Step 1 prefix strip + developer-role skip).
5. **`AGENTS.md` bloating back into a 1,000-page manual** (hard ≤100-line cap + demotion).
6. Padding the memory with plausible-but-weak learnings (no-quota + the gates).
7. A single ambiguous signal hardening into a permanent misfiring rule (confidence ladder).
8. Task-specific artifacts leaking in as if durable (generalization gate).
9. Mistaking a tool/infra failure for a user preference (correction-vs-noise gate).
10. Dangling pointers / orphan docs / a stale index (cross-link + index checks).
11. Duplicate accumulation and compounding knowledge-base debt (daily garbage collection).
12. Stale/contradictory entries kept side by side (supersession replaces, not stacks).
13. Re-litigating the same rejected candidate daily (the extraction ledger).
14. Secrets written verbatim; silent overwrites; hallucinated learnings.
