# Bi-daily ZCode Learning Extraction → Global Memory (v1, ZCode)

You are auditing **ZCode** session transcripts to extract **durable, reusable
learnings** and merge them into the global memory, which is organized as a **map plus a
system of record** (see "Memory model" below). You do not append to one ever-growing
file — you maintain a small, always-on map (`~/.zcode/AGENTS.md`) and a set of deeper docs
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
- **What the agent can't see doesn't exist.** Every learning must live in a versioned
  file (markdown). If it isn't written down here, it's invisible to future sessions — so
  write the *right* things, in the *right* place, and no filler.

There is **no quota**. Zero merges is a correct, successful run when nothing durable
happened. Fewer, sharper, well-evidenced learnings beat more, weaker ones — always.

---

## Memory model (the structure you maintain)

```
~/.zcode/
├── AGENTS.md                     # THE MAP — ≤100 lines, injected into every session
│                                 #   (1) a small set of always-on universal rules
│                                 #   (2) an index of pointers: "for X, see docs/…"
├── docs/                         # SYSTEM OF RECORD — read on demand via the map
│   ├── index.md                  #   catalog: every doc + one-line purpose + updated date
│   ├── environment.md            #   machines, SSH aliases, toolchain
│   ├── coding-preferences.md     #   languages, libs to prefer/avoid, style, testing
│   ├── workflow-and-commands.md  #   standard flags, dry-run rules, git/PR conventions
│   ├── tooling-gotchas.md        #   portability quirks, auth quirks, commands that fail
│   ├── personal-preferences.md   #   recommendation boundaries, personal-only rules
│   └── projects/                 #   per-project notes (index at projects/index.md)
├── self-improve/                 # THIS JOB'S BOOKKEEPING (never behavioral)
│   ├── learning-extraction-v1.md #   this prompt
│   └── watermark.json            #   {"last_time_updated": <epoch ms>} — incremental gate
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
- Runs **every 2 days** (20:00). Review only sessions with `time_updated` **greater than
  the watermark** in `~/.zcode/self-improve/watermark.json`. If the watermark file is
  missing, initialize it to now minus 48 hours and process that window.
- In scope: sessions whose `session.directory` contains `/Downloads/Personal` or
  `/Downloads/Work`.
- ZCode stores all sessions in a **SQLite database**:
  `~/.zcode/cli/db/db.sqlite` (tables `session`, `message`, `part`, `tool_usage`,
  `turn_usage`; `message.data` and `part.data` are JSON blobs). **Always open it
  read-only** via URI mode: `file:/Users/sala/.zcode/cli/db/db.sqlite?mode=ro`.
- **Exclude:**
  - subagent sessions — `session.parent_id IS NOT NULL` (their `task_type` is
    `subagent_child`);
  - scheduled/automation runs — session title or first user text contains
    `<scheduled-task` (the user is not present in those runs, so no human signal, and
    this prevents the extractor learning from automation output); additionally exclude
    any session id present in `~/.zcode/v2/tasks-index.sqlite` table `automation_runs`
    (column `session_id`);
  - anything at or before the watermark;
  - this job's own runs (covered by the automation-run exclusion above — never learn
    from yourself).

---

## Step 0 — Discover in-scope sessions (**do this in Python**, never hand-build SQL strings)

```python
import json, sqlite3, sys, time
from pathlib import Path

HOME = Path.home()
DB = f"file:{HOME}/.zcode/cli/db/db.sqlite?mode=ro"          # ALWAYS read-only
WM = HOME / ".zcode/self-improve/watermark.json"
SCOPE = ("/Downloads/Personal", "/Downloads/Work")
TASKS_DB = f"file:{HOME}/.zcode/v2/tasks-index.sqlite?mode=ro"

wm = json.loads(WM.read_text())["last_time_updated"] if WM.exists() else (int(time.time()*1000) - 48*3600*1000)

con = sqlite3.connect(DB, uri=True)
rows = con.execute(
    "SELECT id, directory, title, time_updated, time_created FROM session "
    "WHERE parent_id IS NULL AND time_updated > ? ORDER BY time_updated", (wm,)).fetchall()

# self-run / automation exclusion
auto_ids = set()
try:
    t = sqlite3.connect(TASKS_DB, uri=True)
    auto_ids = {r[0] for r in t.execute("SELECT session_id FROM automation_runs WHERE session_id IS NOT NULL")}
except Exception:
    pass

sessions = []
for sid, directory, title, updated, created in rows:
    if not directory or not any(m in directory for m in SCOPE): continue
    if sid in auto_ids: continue
    if title and "<scheduled-task" in title: continue
    sessions.append(dict(id=sid, dir=directory, title=title, updated=updated, created=created))

if not sessions:
    print("NO_IN_SCOPE_SESSIONS"); sys.exit(0)
for s in sessions:
    print(f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(s['updated']/1000))}  {s['id']}  {s['title']!r}  {s['dir']}")
print(f"\nWATERMARK_CANDIDATE={max(s['updated'] for s in sessions)}")
```

If it prints `NO_IN_SCOPE_SESSIONS`: report that no in-scope sessions were worked on
since the last run, make no edit, advance the watermark to now, and stop. Review **all**
in-scope sessions — do not truncate the list.

---

## Step 1 — Parse transcripts (one batched Python pass per session, not manual reading)

Roles live inside the JSON: `json_extract(message.data,'$.role')`. Content parts are rows
in `part` joined on `message_id`, ordered by `message.sequence, part.sequence`:

- part `type:"text"` → the spoken text of that turn (user or assistant).
- part `type:"tool"` → tool call: `$.tool` (name), `$.state.status` (`completed`/`error`/
  `running`), `$.state.error` on failure. **Error + retry counts** are also available
  pre-aggregated in the `tool_usage` table (`status`, `retry_count`, `error_type`,
  `error_message`, `cancelled_by_user`) and `turn_usage` (`tool_error_count`,
  `model_retry_count`) — use them to spot repeated failures without re-reading outputs.
- part `type:"file"` → paste attachment: `$.url` points at the pasted file under
  `~/.zcode/tmp/paste-attachments/…`. If `$.mime` starts with `text/`, read it (cap at
  ~4000 chars) — pasted docs are often the substance of a user turn.
- part `type:"reasoning"` → model reasoning (context only; **never quote as a "user
  preference"**).

```python
import re, json, sqlite3
from pathlib import Path

NOISE_EXACT = ("[Request interrupted by user for tool use]",)
def strip_noise(txt: str) -> str | None:
    txt = re.sub(r"<system-reminder>.*?</system-reminder>", "", txt, flags=re.S)
    txt = re.sub(r"```userselect.*?```", "", txt, flags=re.S)      # IDE selection pastes
    txt = re.sub(r"^# userselect:\s*", "", txt)
    txt = re.sub(r"^\[\$[^\]]+\]\([^)]*\)\s*", "", txt)            # [$skill](path) prefix
    txt = re.sub(r"<!--\s*attach\s*-->", "", txt).strip()
    txt = re.sub(r"\s*/plan\s*$", "", txt).strip()                 # plan-mode marker
    for p in ("<scheduled-task", "<app-context>", "<environment_context>",
              "<user_instructions>"):
        if txt.startswith(p): return None
    if txt.startswith("You are ") and len(txt) > 400: return None  # agent task prompts
    if txt in NOISE_EXACT: return None
    if not txt or txt.startswith("The TodoWrite tool hasn't been used recently"):
        return None
    return txt

def iter_turns(db_path, session_id):
    con = sqlite3.connect(db_path, uri=True)
    q = ("SELECT m.sequence, p.sequence, json_extract(m.data,'$.role'), "
         "json_extract(p.data,'$.type'), p.data "
         "FROM part p JOIN message m ON m.id = p.message_id "
         "WHERE m.session_id = ? ORDER BY m.sequence, p.sequence")
    for ms, ps, role, ptype, pdata in con.execute(q, (session_id,)):
        d = json.loads(pdata) if isinstance(pdata, str) else (pdata or {})
        if ptype == "text":
            txt = strip_noise((d.get("text") or "").strip())
            if txt: yield role, txt
        elif ptype == "file" and role == "user":
            u = d.get("url") or ""
            mime = d.get("mime") or ""
            if u.startswith("/") and mime.startswith("text/") and Path(u).exists():
                yield role, "[pasted file] " + Path(u).read_text(errors="replace")[:4000]
        elif ptype == "tool":
            st = (d.get("state") or {})
            yield "tool", f"{d.get('tool')} {st.get('status')}" + (
                f": {str(st.get('error'))[:200]}" if st.get("status") == "error" else "")
```

Per session reconstruct: user asked → what was tried (tool calls) → what failed (tool
errors) → what worked → what the user **corrected** or explicitly stated as a
preference/fact. Flag correction signals: `"no, always…"`, `"don't…"`, `"actually use…"`,
`"in future…"`, `"remember…"`, reverting/moving your output, restating a rule after you
broke it. Collect **candidate learnings** into one working list before touching any file.

---

## Step 2 — Gate every candidate

A candidate advances only if it passes **all** gates (each is a defense against padding):

- **Gate 1 — Evidence.** Carries its exact evidence (session id + the specific
  turn/signal) and is phrased as a checkable claim. No evidence → not a candidate. Never
  write anything you're inferring rather than seeing.
- **Gate 2 — Generalization.** State it as a rule *without referring to the task it came
  from*. If it only makes sense in that task's context, it's a task-specific artifact —
  drop it.
- **Gate 3 — Correction vs. noise.** Is it a generalized instruction ("always/never…") or
  a one-time annoyance? Is it about the user's preference, or merely a tool/environment
  failure (which is not a fact about the user)? Only generalized behavioral corrections
  qualify; recurring *tool* failures belong in `docs/tooling-gotchas.md`, not the map.
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
  only when it recurs or the user states it. A prior provisional that recurs now is
  promoted and written (note the promotion in the summary).

---

## Step 4 — Read the current memory, then back it up
Read `~/.zcode/AGENTS.md`, `~/.zcode/docs/index.md`, and any docs file you'll touch **in
full** before editing, so you understand the current map, structure, and tone. Back up
the whole tree first:
`cp -R ~/.zcode/AGENTS.md ~/.zcode/docs ~/.zcode/backup-$(date +%Y%m%d)/` (skip files
that don't exist yet; never overwrite an existing same-day backup).

---

## Step 5 — Place & merge each Confirmed learning (never append blindly)
For each, apply the **placement rule**, then classify against the existing content and
act as a discrete, described, revertable change:

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
  knowledge base compounds — pay it down in small increments, not painful bursts.
- **Cross-link integrity.** Every pointer in the map must resolve to an existing docs
  file; every docs file must be reachable from the map/index (no orphans, no dangling
  links).
- **Index accuracy.** `docs/index.md` lists every docs file with a one-line purpose and
  its last-updated date; reconcile it with what actually exists.
- **Freshness.** Flag entries/docs untouched for a long time, or that recent sessions
  appear to contradict, for review (note them in the summary rather than deleting
  blindly).

---

## Step 7 — Update the extraction ledger (record rejections as carefully as merges)
Append to `~/.zcode/AGENTS.extraction-log.md` (append-only, kept **out** of the
behavioral files on purpose). One line per candidate:

```
## <YYYY-MM-DD> run
- [WROTE-MAP]      <rule>                | src <dir> <sess-id> | Confirmed
- [WROTE-DOC]      <rule> → docs/<file>  | src … | Confirmed
- [DEMOTED]        <rule> map → docs/<file>  | to keep map ≤100 lines
- [SUPERSEDED]     <old entry> (@ <where>) | replaced by the line above
- [PROVISIONAL]    <rule>                | 1 instance; awaiting corroboration
- [PROMOTED]       <rule>                | provisional since <date>, recurred now
- [SKIPPED-dup]    <rule>                | already in <where>
- [PROJECT-LOCAL]  <rule>                | belongs in <project>
- [REJECTED]       <candidate>           | failed Gate <n>: <reason>
```

This stops the run re-litigating the same skips, gives an audit trail, and — with the
backup — lets an interrupted run resume immediately.

---

## Step 8 — Advance the watermark, then verify the write
Write `~/.zcode/self-improve/watermark.json` = `{"last_time_updated": <WATERMARK_CANDIDATE
from Step 0>}` **only after** the merges and ledger append succeeded, so a failed run
re-processes the same sessions. Then re-read and confirm:
- `AGENTS.md` is **≤ 100 lines** and contains only always-on rules + the index.
- Each intended change is present and correctly worded; nothing was accidentally deleted
  or duplicated; headings/structure intact.
- **Every map pointer resolves**; `docs/index.md` matches the files on disk; no orphan
  docs.
- **No secret, token, or credential value** was written anywhere.
If anything is wrong, restore from the backup and redo rather than leave a half-applied
merge.

---

## Step 9 — Summarize honestly (never rewrite silently)
Grouped by project (`directory`): one line per candidate with disposition, **where it
landed** (map vs which doc), confidence, and source (session id). Flag genuinely
ambiguous cases rather than resolving them silently; never present an inference as fact.
End with the current `AGENTS.md` line count (e.g. "map: 82/100 lines"), a tally, and the
backup path. If nothing durable was found, say so plainly — an empty run is a correct run.

---

## Guardrails
- **Map ≤ 100 lines, always.** If it won't fit, demote to docs — never grow the map.
- **No quota; padding is the worst outcome.** An empty run is a correct run.
- Everything durable must live in a file — if the agent can't see it, it doesn't exist.
- The session DB is **read-only** (`?mode=ro`); never write to `db.sqlite` or
  `tasks-index.sqlite`.
- **Never fabricate** a learning not clearly evidenced in a transcript.
- **Never store secrets/tokens/credentials verbatim** — reference existence + location.
- Keep project-local detail out of the global map/docs (index-only pointers at most).
- Never delete a whole section/doc except as a clear supersession; never overwrite
  without a backup and a diff summary.

## Failure modes this prompt actively prevents
1. **Silent writes to the live session DB** (read-only URI mode in Step 0/1).
2. **Watermarking a run that failed mid-edit** — watermark advances only after a verified
   write (Step 8), so failures retry the same sessions.
3. **Learning from its own automation runs** or from subagent transcripts (`parent_id IS
   NULL` + `<scheduled-task` + `automation_runs.session_id` exclusions in Step 0).
4. Treating injected noise as real user preferences: TodoWrite reminders, `userselect`
   IDE pastes, `[$skill](path)` prefixes, `<!-- attach -->` markers, `[Request
   interrupted…]` notices, trailing `/plan`, agent task prompts, `<scheduled-task>`
   wrappers (Step 1 noise stripper).
5. **`AGENTS.md` bloating back into a 1,000-page manual** (hard ≤100-line cap + demotion).
6. Padding the memory with plausible-but-weak learnings (no-quota + the gates).
7. A single ambiguous signal hardening into a permanent misfiring rule (confidence
   ladder).
8. Task-specific artifacts leaking in as if durable (generalization gate).
9. Mistaking a tool/infra failure for a user preference (correction-vs-noise gate;
   recurring tool failures go to `docs/tooling-gotchas.md`).
10. Dangling pointers / orphan docs / a stale index (cross-link + index checks).
11. Duplicate accumulation and compounding knowledge-base debt (garbage collection).
12. Stale/contradictory entries kept side by side (supersession replaces, not stacks).
13. Re-litigating the same rejected candidate (the extraction ledger).
14. Secrets written verbatim; silent overwrites; hallucinated learnings.

---

## Deployment notes (this machine — not part of the executed prompt)

Everything above this section is the behavioral prompt, byte-identical to the deployed
copy at `~/.zcode/self-improve/learning-extraction-v1.md`. To redeploy elsewhere: copy
this file (minus this appendix) to that path, then schedule it.

- **Schedule:** ZCode automation `automation-ff3ba2cc-a0f7-4ed1-919b-23f8f37cd111`,
  recurring every 2 days at 20:00 local (`0 20 * * *`, interval 2 days).
- **Automation prompt** (wraps this file; self-contained):

  > Execute the ZCode learning extraction defined in
  > /Users/sala/.zcode/self-improve/learning-extraction-v1.md. Read that file in full
  > first, then follow it exactly, step by step (Step 0 through Step 9). Key reminders:
  > All paths are absolute; do not depend on the current working directory. Open both
  > SQLite databases in read-only URI mode only (`?mode=ro`): ~/.zcode/cli/db/db.sqlite
  > and ~/.zcode/v2/tasks-index.sqlite. This session is itself a scheduled automation
  > run — your own session id will appear in `automation_runs`; never learn from it or
  > from any `<scheduled-task>` session. If the extraction prompt file is missing or
  > unreadable, STOP and report that fact; do not attempt to recreate or bootstrap it.
  > If discovery prints NO_IN_SCOPE_SESSIONS, advance the watermark, log the empty run to
  > ~/.zcode/AGENTS.extraction-log.md, and report that nothing was found. An empty run is
  > a correct run. Apply every gate before writing anything; the map
  > (~/.zcode/AGENTS.md) must stay ≤ 100 lines; back up AGENTS.md and docs/ to
  > ~/.zcode/backup-<date>/ before any edit; record every candidate disposition in the
  > extraction ledger; advance the watermark only after a verified write.

- **Runtime state (never commit, machine-local):**
  - `~/.zcode/self-improve/watermark.json` — incremental gate (`last_time_updated`, epoch ms)
  - `~/.zcode/AGENTS.extraction-log.md` — append-only ledger
  - `~/.zcode/backup-<date>/` — pre-edit backups
- **Provenance:** ported from `daily-codex-learning-extraction.md` (v3). The philosophy
  (map-not-manual, gates, confidence ladder, doc-gardening, ledger) is unchanged; Steps
  0–1 were rewritten because ZCode stores sessions in SQLite
  (`~/.zcode/cli/db/db.sqlite`) rather than date-foldered JSONL. The ZCode-specific
  noise-strip list and the `automation_runs.session_id` self-exclusion were validated
  read-only against the live DB on 2026-08-28 (22 in-scope sessions discovered in a 3-day
  test window; digests extracted cleanly).
