# Bi-daily ZCode Learning Extraction → Global Memory (v6, ZCode)

You are auditing **ZCode** session transcripts to extract **durable, reusable
learnings** and merge them into the global memory, which is organized as a **map plus a
system of record** (see "Memory model" below). You do not append to one ever-growing
file — you maintain a small, always-on map (`~/.zcode/AGENTS.md`) and a set of deeper docs
it points to.

## Context boundary (read first)

This session runs with `injectAgentsMd: false` by design — ZCode does **not** inject
`~/.zcode/AGENTS.md` or any other global map/docs content into this conversation. That is
intentional, not a bug: an extraction job that reads its own target file as ambient
context risks anchoring on stale content instead of the run's actual staged diff. Treat
this file plus the runner's task-scoped artifacts (`manifest.json`,
`normalized_sessions.jsonl`, the `staging/` copies of live memory) as your **entire**
source of truth. Never assume the current map/docs content is already "in context" from
injection — read it fresh from `staging/` each run (Step 4).

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

## Transactional runner protocol

Use the deployed runner at the absolute path
`/Users/sala/.zcode/self-improve/zcode_learning_extractor.py` for **all database access,
checkpoint changes, backups, validation, recovery, and writes to live memory** — every
runner command below is `python3
/Users/sala/.zcode/self-improve/zcode_learning_extractor.py <command> ...` (this session's
cwd is not guaranteed, so the path must be absolute, never repo-relative). After
`prepare`, ordinary file tools are explicitly allowed inside the printed `run_dir` only:
read `manifest.json`, `normalized_sessions.jsonl`, and staged memory; write
`decisions.jsonl` and `session_dispositions.jsonl`; and edit files only under `staging/`.
Never edit `manifest.json`, `normalized_sessions.jsonl`, `commit.json`, `validation.json`,
`diff.patch`, `report.md`, or anything under
`~/.zcode/self-improve/extraction-control/`. The runner is the only thing that may touch
`~/.zcode/cli/db/db.sqlite`, `~/.zcode/v2/tasks-index.sqlite`, `~/.zcode/AGENTS.md`,
`~/.zcode/docs/**`, `~/.zcode/AGENTS.extraction-log.md`, or
`~/.zcode/self-improve/watermark.json`. You never edit those live paths directly, and you
never write `watermark.json` by hand. (The runner's canonical source lives in the
`llm-skills` repository at `skills/hill-climb/scripts/zcode_learning_extractor.py` and is
copied verbatim to the deployed path above — see "Deployment notes.")

1. Run `prepare` first. It opens both SQLite databases **read-only** (URI `?mode=ro` +
   `PRAGMA query_only`), reads the current watermark
   (`{"last_time_updated": <epoch ms>}`) as the lower bound, captures a fixed upper bound
   (now, in epoch ms), discovers every in-scope top-level session that either has that
   window itself as its `time_updated`, or has an eligible user/assistant message
   timestamped inside the window even if the session row's own `time_updated` later moved
   past the upper bound (both checks share one read snapshot/transaction, so a message
   that lands right at the boundary is never silently lost), normalizes its transcript
   (noise-stripped, secret-redacted, with per-event evidence hashes), copies live
   `AGENTS.md` + `docs/` + the ledger into a private staging directory, binds every
   security-sensitive field of the run (bounds, provenance, sessions, baseline hashes,
   watermark baseline, evidence digest, authorized target inventory) into a
   runner-controlled **trusted control record** outside the run directory (see "Memory
   model"), and prints a `run_id` and `run_dir`. It refuses to start if a previous run's
   commit was left incomplete (see step 4) — run `recover` on that `run_id` first. The
   watermark checkpoint and the `~/.zcode/v2/tasks-index.sqlite` automation-exclusion
   database both **fail preparation** rather than silently guessing if something is
   wrong: `prepare` only bootstraps the watermark window (now minus
   `--bootstrap-hours`) when `watermark.json` genuinely does not exist yet — an existing
   file that is unreadable, not valid JSON, the wrong schema, non-numeric, boolean,
   negative, or in the future is a hard error, unchanged. Likewise the tasks-index
   database is **required**: a missing file, an unreadable database, a missing
   `automation_runs` table, or a failed query stops `prepare` outright — it never
   substitutes an empty automation-exclusion set, which would let automation output leak
   into the map/docs undetected. A live target standing behind a symlink (dangling or
   not) is never silently skipped from the baseline either — it's a hard error.
2. Read only `run_dir/normalized_sessions.jsonl` (the normalized, evidence-hashed
   transcripts) and `run_dir/staging/AGENTS.md` + `run_dir/staging/docs/**` (the current
   live memory, copied for you). Apply Steps 1–6 below entirely against these staged
   files — never touch `~/.zcode/AGENTS.md` or `~/.zcode/docs/**` directly. Each
   normalized event carries `is_new`: a message with no timestamp, or one that falls
   outside `(lower_bound, upper_bound]`, is `is_new: false` — it may still inform your
   read of the session as context, but the validator rejects it as decision evidence.
3. Write your findings as two files in `run_dir`:
   - `decisions.jsonl` — one JSON object per candidate learning:
     `{"claim", "kind": "behavioral_rule"|"technical_fact", "scope": "global"|"project",
     "confidence": "confirmed"|"provisional", "disposition": "WROTE_MAP"|"WROTE_DOC"|
     "REFINED"|"SUPERSEDED"|"SKIPPED_DUP"|"PROVISIONAL"|"REJECTED", "destination":
     "docs/…" (required for write dispositions; **only** a write disposition's
     `destination` can ever authorize a memory change — a `destination` on
     `PROVISIONAL`/`REJECTED`/`SKIPPED_DUP` is rejected outright, never silently
     ignored), "supporting_destinations": ["docs/…", …] (optional, write dispositions
     only, and restricted to *structural* index/map files — exactly `AGENTS.md`,
     `docs/index.md`, `docs/projects/index.md`, or `docs/projects/<project>/index.md`;
     never an arbitrary content doc, which must be its own primary write decision), and
     "evidence": [{"session_id", "event_timestamp", "event_sha256"}, …], "reason"}`.
     Every decision needs a **nonempty** `evidence` array, and each entry must exactly
     match one real event from `normalized_sessions.jsonl` (its `session_id`,
     `event_sha256`, and — when you include it — `event_timestamp`) and be
     decision-eligible: `is_new: true` **and** a numeric epoch strictly inside
     `(lower_bound, upper_bound]`, both independently re-checked by the validator, not
     just trusted from `is_new`. `normalized_sessions.jsonl` itself is hash-pinned in the
     manifest — never edit it; the validator rejects the whole run if its bytes don't
     match. `confidence: provisional` may only pair with `disposition: PROVISIONAL`;
     every write disposition (`WROTE_MAP`/`WROTE_DOC`/`REFINED`/`SUPERSEDED`) requires
     `confidence: confirmed` **and** at least one cited evidence event whose `role` is
     `user` — a purely tool/assistant-sourced citation (e.g. a repeated tool failure) can
     support the *claim* but still needs a qualifying user correction or an explicit
     stated rule before it becomes a write. When a write necessarily also touches a
     structural index/map file (e.g. a new `docs/` file needs a `docs/index.md` entry and
     an `AGENTS.md` pointer, or a new project needs its own `docs/projects/<name>/index.md`
     and the `docs/projects/index.md` catalog), list those paths in that same decision's
     `supporting_destinations` — every changed memory file must be covered by some write
     decision's `destination` or `supporting_destinations`, and `supporting_destinations`
     only counts if the run has at least one primary write decision; it can never
     authorize an unrelated change by itself.
   - `session_dispositions.jsonl` — **one line per session `prepare` discovered**, even
     when it produced nothing: `{"session_id", "status": "contributed"|
     "reviewed_no_learning", "note"}`. `status` must be exactly one of those two values
     (nothing else validates), each `session_id` must appear exactly once, and every
     session marked `contributed` must be cited by at least one `decisions.jsonl`
     record's `evidence[].session_id` — mark it `reviewed_no_learning` instead if you
     looked at it but it produced no decision. The validator also checks this file
     against the manifest's session list and fails the run if any discovered session is
     missing or if it references a session outside this run — this is what prevents a
     session from being silently dropped between discovery and the summary.
4. Run `commit --run-id <id>` to finish in one step: it re-validates everything (schema,
   evidence hashes/eligibility, confidence/disposition combinations, destinations and
   `supporting_destinations`, secrets, the `AGENTS.md` line cap, map-pointer integrity,
   the ledger's append-only invariant, complete session accounting, that live memory
   hasn't changed since `prepare`, and that the manifest still matches the trusted
   control record `prepare` wrote), runs a full symlink preflight over every live
   target/staged destination/the watermark before touching anything, then backs up every
   live target **and** the watermark (with a manifest of hashes for later verification),
   binds that backup's path/digest/exact inventory into trusted apply state, and only
   then writes a durable **commit marker** (`run_dir/commit.json`) — before this point no
   live file has been touched at all. It applies the staged files, and — only after every
   staged file has been written — advances `~/.zcode/self-improve/watermark.json` to the
   run's upper bound. It then flips the commit marker to `completed` and prunes old run
   dirs/backups (keep the newest 5 by default, tune with `--keep N`). On validation
   failure it applies nothing and prints the errors so you can fix staging and re-run
   `commit`. To inspect before writing, run `validate --run-id <id>` and review
   `diff.patch` / `report.md`; `apply --run-id <id> --apply` still works as the explicit
   low-level write once validation has passed. The extraction ledger
   (`AGENTS.extraction-log.md`) is **append-only**: the validator rejects any staged
   version that doesn't start with the exact bytes of the live ledger — truncating it,
   replacing it, or editing an earlier entry in place all fail validation; only appending
   a new block is allowed.
5. **This is a recoverable commit, not an atomic one.** If the process is interrupted
   after `commit`/`apply` starts writing, the commit marker stays `in_progress` on disk —
   `prepare` for a new run will refuse to start until you run `recover --run-id <id>`.
   `recover` is **state-aware and idempotent**, never a blind restore, and requires a
   present, well-formed, run-matching commit marker with a recognized status before it
   acts at all — a missing, malformed, run-id-mismatched, or unrecognized-status marker
   fails closed with no filename-based fallback search for a plausibly-named backup ever
   attempted. It also requires the run's trusted control state to still exist (a legacy
   run without it is refused outright) and refuses outright if a *different* run
   currently owns the extraction lock; it is a no-op (only releasing a leftover same-run
   lock, never rolling anything back) for a run whose marker already says `completed` or
   `recovered` — recovering an old run a second time, or after a later run has since
   completed, must never clobber that later work. For a genuinely unresolved
   (`in_progress`) run it restores every live target (including the watermark) from the
   pre-run backup — but only after verifying the backup's path, naming, every file's
   hash, **and** that its inventory/presence/hashes exactly match the trusted apply
   state `commit`/`apply` recorded (not just that the backup is internally
   self-consistent — a swapped-in empty-but-valid manifest, or one with an extra
   "absent" entry naming a path the run never touched, is rejected too); a missing
   backup, a malformed manifest, a missing backed-up file, a hash mismatch, or an
   inventory that doesn't match trusted state **fails recovery closed**, leaving the
   marker, the normalized evidence, and the lock exactly as they were rather than
   guessing. Every restore destination is also symlink-preflighted *before* any of them
   is written, so discovering one unsafe target partway through a restore never leaves
   some files already restored and others not. A crash caught between the first commit
   marker and the durable backup (before any live file was touched) is safely aborted
   with no restore at all — but only when live memory *and* the watermark still exactly
   match the baseline `prepare` recorded for both, whether or not a watermark already
   existed (a run prepared by a runner too old to have recorded that baseline fails
   closed with an actionable error instead of guessing). Never advance the watermark
   yourself and never delete `commit.json`/the lock by hand; `recover` owns that. The
   extraction lock is published atomically (built fully, including its metadata, under a
   private temp name, then renamed into place in one step) so it can never be observed
   half-formed; if it still looks abandoned or malformed (present but missing its owner
   metadata — an interrupted acquisition, not a crash mid-commit, or a legacy plain-file
   lock), do not delete it by hand either; run `unlock-abandoned` first, which only
   removes it after confirming the owning process is not alive and no run still needs it
   for recovery. If a malformed lock and an incomplete commit deadlock each other
   (`unlock-abandoned` itself refuses while an incomplete commit exists), that deadlock
   is an **operator-only** situation: `repair-recover --run-id <id>
   --confirm-no-process` requires a human to have manually confirmed no extraction
   process for that run is still alive, still refuses if the lock identifies a pid that
   *is* alive, and otherwise claims the lock and performs the same verified recovery as
   `recover` — never run this unattended, and on any failure it leaves the marker,
   evidence, and control state exactly as `recover` would. Run `status` anytime to see
   the lock, the current watermark, the latest run, and any incomplete commits; run
   `prune --keep N` to clean up old runs; run `check-deployment` anytime (no `--run-id`,
   read-only, safe to run from any account with read access) to confirm the scheduled
   automation, its wrapper prompt, the deployed extraction prompt, and the deployed
   runner copy all still match what's expected — see "Deployment notes."

---

## Memory model (the structure you maintain)

```
~/.zcode/
├── AGENTS.md                     # THE MAP — ≤100 lines, injected into every OTHER session
│                                 #   (this extraction session itself runs without injection —
│                                 #   see "Context boundary" above)
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
│   ├── learning-extraction-v1.md #   this prompt (deployed body only, see appendix)
│   ├── zcode_learning_extractor.py #  the deployed runner copy (see "check-deployment")
│   ├── watermark.json            #   {"last_time_updated": <epoch ms>} — runner-owned
│   ├── extraction.lock/          #   runner mutex (a directory + owner.json metadata,
│   │                             #     not a bare file); present only while a run is in
│   │                             #     flight — see "unlock-abandoned" if it looks stuck
│   ├── extraction-runs/<run_id>/ #   per-run manifest, staging, decisions, commit marker
│   │                             #   (agent-editable — this is where you write/edit)
│   └── extraction-control/<run_id>/ # RUNNER-CONTROLLED TRUSTED STATE — never edit,
│                                 #   never read for task content. Mode 0700 dir /
│                                 #   0600 files: `control.json` binds every security-
│                                 #   sensitive manifest field (bounds, provenance,
│                                 #   sessions, baseline hashes, watermark baseline,
│                                 #   evidence digest, authorized targets) recorded at
│                                 #   `prepare` time; `apply.json` binds the pre-apply
│                                 #   backup's path, manifest digest, and exact
│                                 #   inventory/presence/hashes, written after the
│                                 #   backup is verified and before any live write.
│                                 #   `validate`/`apply`/`recover` all refuse a run
│                                 #   whose editable manifest/backup doesn't match this
│                                 #   state exactly, and refuse outright if it's
│                                 #   missing entirely (a legacy run).
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

## Execution boundary

The transactional runner protocol above is authoritative. The "legacy reference" blocks
under Scope and Step 1 below document the exact discovery query and parsing rules the
runner implements internally (`discover_sessions`/`normalize_session`/`strip_noise` in
`zcode_learning_extractor.py`) so you can audit them — do **not** execute that SQL/Python
yourself, and do not hand-edit `~/.zcode/AGENTS.md`, `~/.zcode/docs/**`,
`~/.zcode/AGENTS.extraction-log.md`, or `~/.zcode/self-improve/watermark.json` directly.

## Scope
- Runs **every 2 days** (20:00); the runner reviews every top-level session where
  *either* `watermark.last_time_updated < time_updated <= upper_bound`, *or* the session
  has an eligible user/assistant message with `watermark.last_time_updated <
  message.time_created <= upper_bound` even if the session's own `time_updated` later
  moved past `upper_bound` — this catches a message that landed inside the window just
  before an assistant reply nudged `time_updated` past it a moment later. Both checks run
  against one read snapshot, even across missed runs.
- In scope by default: sessions whose `session.directory` is under `~/Downloads/Personal`
  or `~/Downloads/Work` (configurable per invocation via `--scope-root`, e.g. for test
  fixtures).
- **Exclude** (the runner owns all of this): subagent sessions (`parent_id IS NOT NULL` /
  `task_type = 'subagent_child'`); scheduled/automation runs (title or first user text
  contains `<scheduled-task`, or the session id appears in
  `automation_runs.session_id` in `~/.zcode/v2/tasks-index.sqlite`); this job's own
  session, if supplied via `--self-session-id`; anything at or before the watermark.

### Legacy reference: discovery query (do not execute — the runner implements this)

```python
import json, sqlite3, sys, time
from pathlib import Path

HOME = Path.home()
DB = f"file:{HOME}/.zcode/cli/db/db.sqlite?mode=ro"          # ALWAYS read-only
WM = HOME / ".zcode/self-improve/watermark.json"
SCOPE = (HOME / "Downloads/Personal", HOME / "Downloads/Work")
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
    if not directory or not any(str(m) in directory for m in SCOPE): continue
    if sid in auto_ids: continue
    if title and "<scheduled-task" in title: continue
    sessions.append(dict(id=sid, dir=directory, title=title, updated=updated, created=created))
```

If `prepare` reports `session_count: 0`: this is a **correct, complete run** — write a
`session_dispositions.jsonl` that is empty (nothing to account for), stage an empty-run
note in the ledger, make no other edit, and `commit` (which still advances the watermark
to the run's upper bound). Review **all** discovered sessions — do not truncate the list.

---

## Step 1 — Parse transcripts (already done for you; read the normalized evidence)

`normalized_sessions.jsonl` (one JSON object per session, `events: […]`) is the runner's
output of the parsing rules below — you read this file, you do not re-parse the database.

### Legacy reference: normalization rules (do not execute — ported into `zcode_learning_extractor.py`)

Roles live inside the JSON: `json_extract(message.data,'$.role')`. Content parts are rows
in `part` joined on `message_id`, ordered by `message.sequence, part.sequence`:

- part `type:"text"` → the spoken text of that turn (user or assistant).
- part `type:"tool"` → tool call: `$.tool` (name), `$.state.status` (`completed`/`error`/
  `running`), `$.state.error` on failure. This is exactly what lands in
  `normalized_sessions.jsonl` as a `role: "tool"` event — you work from that normalized
  event, not from a fresh query against `tool_usage`/`turn_usage` or any other table the
  runner didn't already read. Stay inside the task boundary: normalized evidence only.
- part `type:"file"` → paste attachment: `$.url` points at the pasted file under
  `~/.zcode/tmp/paste-attachments/…`. If `$.mime` starts with `text/`, the runner reads it
  (capped at 4000 chars) — pasted docs are often the substance of a user turn.
- part `type:"reasoning"` → model reasoning; the runner never surfaces this as an event
  (never treat it as a "user preference" even if you see it elsewhere).

```python
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
```

Per session reconstruct: user asked → what was tried (tool calls) → what failed (tool
errors) → what worked → what the user **corrected** or explicitly stated as a
preference/fact. Flag correction signals: `"no, always…"`, `"don't…"`, `"actually use…"`,
`"in future…"`, `"remember…"`, reverting/moving your output, restating a rule after you
broke it. Collect **candidate learnings** into one working list before writing
`decisions.jsonl`.

---

## Step 2 — Gate every candidate

A candidate advances only if it passes **all** gates (each is a defense against padding):

- **Gate 1 — Evidence.** Carries its exact evidence (session id + the specific
  `event_sha256`) and is phrased as a checkable claim. No evidence → not a candidate.
  Never write anything you're inferring rather than seeing.
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
  sessions/instances**. → Eligible to write (`disposition` in `WROTE_MAP`/`WROTE_DOC`/
  `REFINED`/`SUPERSEDED`). The validator **hard-enforces** this pairing: a write
  disposition without `confidence: confirmed`, or a `confidence: provisional` decision
  with any disposition other than `PROVISIONAL`, fails validation outright.
- **Provisional** — inferred from a single instance / ambiguous signal. → Do **not**
  write it into the map or docs (`disposition: PROVISIONAL`, `confidence: provisional`,
  no `destination`); the ledger records it. Promote to Confirmed only when it recurs or
  the user states it. A prior provisional that recurs now is promoted and written (note
  the promotion in the summary and in the ledger).

---

## Step 4 — Read the staged current memory

Read `run_dir/staging/AGENTS.md`, `run_dir/staging/docs/index.md`, and any staged docs
file you'll touch **in full** before editing, so you understand the current map,
structure, and tone. This *is* the backup and the live-diff surface at once: `prepare`
already copied it from `~/.zcode`, and `commit`/`apply` will additionally back up every
live target before writing anything. You never run a manual `cp -R` step here.

---

## Step 5 — Place & merge each Confirmed learning (never append blindly)

Edit **`run_dir/staging/AGENTS.md`** and **`run_dir/staging/docs/**`** — never the live
`~/.zcode` paths. For each candidate, apply the **placement rule**, then classify against
the existing staged content and act as a discrete, described, revertable change:

- **Duplicate** (already captured anywhere, even if worded differently) → skip; note it
  (`disposition: SKIPPED_DUP`).
- **Refinement** (adds scope to an existing entry) → edit that entry in place
  (`disposition: REFINED`).
- **Contradiction / supersession** (preference changed, path moved, tool swapped) →
  **replace** the old entry wherever it lives; don't keep both versions
  (`disposition: SUPERSEDED`).
- **Genuinely new** → write it to its placed location (map *or* docs file)
  (`disposition: WROTE_MAP`/`WROTE_DOC`); if it's a new docs file, add it to
  `docs/index.md` **and** add a pointer in the map.

Tag new/changed entries with a trailing `(updated YYYY-MM-DD)`. Every write disposition
needs a `destination` in `decisions.jsonl` that matches the staged file you changed — the
validator rejects a memory change that no decision references.

---

## Step 6 — Garbage-collect the knowledge base (doc-gardening)

Run this every time against the **staged** files; it's what keeps the map a map and the
docs trustworthy:

- **Enforce the ≤100-line map cap.** Count `staging/AGENTS.md` lines. If over, demote the
  least-universal always-on rules into their `docs/` file (relying on the pointer) until
  it fits. The validator hard-rejects a commit over the cap.
- **Consolidate.** Merge redundant entries; remove superseded ones **by editing them out
  of the staged file that contains them** — the runner rejects a staged file that
  disappears entirely (see the Guardrails note on deletions), so a doc is trimmed down to
  its remaining content, never deleted as a file. Tech debt in a knowledge base
  compounds — pay it down in small increments, not painful bursts.
- **Cross-link integrity.** Every pointer in the map must resolve to an existing staged
  docs file; every docs file must be reachable from the map/index (no orphans, no
  dangling links). The validator checks pointer resolution; you're responsible for index
  accuracy.
- **Index accuracy.** `docs/index.md` lists every docs file with a one-line purpose and
  its last-updated date; reconcile it with what actually exists in staging.
- **Freshness.** Flag entries/docs untouched for a long time, or that recent sessions
  appear to contradict, for review (note them in the summary rather than deleting
  blindly).

---

## Step 7 — Write the extraction ledger and the session accounting

Append to **`run_dir/staging/AGENTS.extraction-log.md`** (append-only, kept **out** of the
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

Also write `run_dir/decisions.jsonl` (one line per candidate above, machine-readable —
see the runner protocol's schema) and `run_dir/session_dispositions.jsonl` (one line per
session `prepare` discovered — including sessions that yielded nothing). Both are
required before `validate`/`commit` will pass whenever `session_count > 0`. This is what
lets an interrupted run resume without re-litigating the same skips, and gives a
machine-checkable audit trail.

---

## Step 8 — Validate and commit

Run `validate --run-id <id>` and read `report.md` / `diff.patch` in `run_dir`. The
validator checks, among other things:
- `AGENTS.md` is **≤ 100 lines** and every map pointer resolves to a staged file.
- Every `decisions.jsonl` record has valid evidence hashes, a valid destination under
  `docs/` (project-scoped facts under `docs/projects/`), and no secret-like value.
- Every discovered session appears exactly once in `session_dispositions.jsonl` with an
  allowed `status`, and every `contributed` session is cited by some decision's evidence.
- Live memory has not changed since `prepare` (no stale-baseline race).
- No staged file has been deleted (see Guardrails).

If it fails, fix the staged files / `decisions.jsonl` / `session_dispositions.jsonl` and
re-run `validate` (or just `commit`, which validates first). Once it passes, run
`commit --run-id <id>` — this is the **only** step that touches
`~/.zcode/AGENTS.md`, `~/.zcode/docs/**`, `~/.zcode/AGENTS.extraction-log.md`, and
`~/.zcode/self-improve/watermark.json`, and it advances the watermark only after every
staged file is applied. `apply`/`commit` always **recomputes** this validation
immediately before writing anything live — a `validation.json` from an earlier `validate`
call is never trusted on its own, so editing staging after validating and jumping
straight to `apply` is safe, not a bypass. If `commit`/`apply` is interrupted, run
`recover --run-id <id>` before doing anything else — never hand-edit the watermark or
the live files to "fix" an interrupted run. `prune` never deletes a backup an
unresolved (`in_progress`) commit marker still points to, even if it's the oldest backup
on disk — recovery is never a race against your own housekeeping.

---

## Step 9 — Summarize honestly (never rewrite silently)

Grouped by project (`directory`): one line per candidate with disposition, **where it
landed** (map vs which doc), confidence, and source (session id). Flag genuinely
ambiguous cases rather than resolving them silently; never present an inference as fact.
End with the current `AGENTS.md` line count (from the committed result, e.g. "map: 82/100
lines"), a tally, and the `run_id` (from which `report.md`/`diff.patch` can be
re-inspected). If nothing durable was found, say so plainly — an empty run is a correct
run.

---

## Guardrails
- **Map ≤ 100 lines, always.** If it won't fit, demote to docs — never grow the map.
- **No quota; padding is the worst outcome.** An empty run is a correct run.
- Everything durable must live in a file — if the agent can't see it, it doesn't exist.
- The session DB is **read-only** (`?mode=ro` + `PRAGMA query_only`); the runner never
  writes to `db.sqlite` or `tasks-index.sqlite` under any code path.
- **Never edit live `~/.zcode/AGENTS.md`, `~/.zcode/docs/**`,
  `~/.zcode/AGENTS.extraction-log.md`, or `~/.zcode/self-improve/watermark.json`
  directly.** All writes go through `prepare` → staged edits → `validate` → `commit`.
- **Never fabricate** a learning not clearly evidenced in a transcript.
- **Never store secrets/tokens/credentials verbatim** — reference existence + location.
- Keep project-local detail out of the global map/docs (index-only pointers at most).
- **A whole staged file can never be deleted — the runner rejects staged deletions
  outright**, full stop, no supersession exception. An individual *entry* inside a file
  can be superseded/removed freely (that's a normal edit to the file's content, still
  present as a file); to retire an entire doc, trim it to a stub/redirect notice and
  update `docs/index.md` and the map pointer, rather than deleting the file.
- **The extraction ledger is append-only.** Never rewrite or trim an earlier ledger
  entry — the validator requires the staged ledger to start with the exact bytes of the
  live one; only append a new dated block.
- **Every changed memory file needs an authorizing decision.** A `destination` (or a
  write decision's `supporting_destinations`, for the index/map updates that
  necessarily accompany it) must cover every file the run changes — one decision can
  never wave through an unrelated change.
- **If `recover` or `unlock-abandoned` refuses**, do not work around it by hand-editing
  `commit.json`, the lock, or live files — a refusal means the runner could not prove
  the action was safe (wrong lock owner, unverifiable backup, or a process that might
  still be alive), and guessing is exactly what this protocol exists to avoid.
  `repair-recover` is the only sanctioned exception, and only for a human operator who
  has manually confirmed no extraction process is alive — never invoke it from an
  unattended automation run.
- **Never edit `~/.zcode/self-improve/extraction-control/**` by hand or treat it as task
  content.** It is runner-controlled trusted state, not something to read for context or
  write to "help" a stuck run — `validate`/`apply`/`recover` all refuse a run whose
  editable manifest or backup doesn't match it exactly, and refuse outright if it's
  missing.

## Failure modes this prompt actively prevents
1. **Silent writes to the live session DB** (read-only URI mode + `PRAGMA query_only` in
   the runner; this prompt never issues SQL against a writable handle).
2. **Watermarking a run that failed mid-commit** — the runner writes a durable commit
   marker before touching any live file, and advances the watermark only after every
   staged file has been applied; an interrupted commit is detected before the next
   `prepare` and requires `recover`. `recover` is state-aware and idempotent: it
   restores the pre-run backup only for a genuinely unresolved run (never for one
   already `completed`/`recovered`, which would silently clobber later work), refuses
   outright if a different run owns the extraction lock, and fails the recovery closed
   -- leaving the marker, evidence, and lock untouched -- if the backup is missing,
   malformed, or its hashes don't match, rather than guessing. This is a
   **recoverable**, not atomic, commit: the worst case of an interruption is redoing an
   already-finished run, never silently skipping evidence.
3. **Learning from its own automation runs** or from subagent transcripts (`parent_id IS
   NULL` + `<scheduled-task` + `automation_runs.session_id` + `--self-session-id`
   exclusions, all enforced by the runner).
4. Treating injected noise as real user preferences: TodoWrite reminders, `userselect`
   IDE pastes, `[$skill](path)` prefixes, `<!-- attach -->` markers, `[Request
   interrupted…]` notices, trailing `/plan`, agent task prompts, `<scheduled-task>`
   wrappers (runner's `strip_noise`).
5. **`AGENTS.md` bloating back into a 1,000-page manual** (hard ≤100-line cap enforced by
   the validator, not just prose).
6. Padding the memory with plausible-but-weak learnings (no-quota + the gates).
7. A single ambiguous signal hardening into a permanent misfiring rule (confidence
   ladder).
8. Task-specific artifacts leaking in as if durable (generalization gate).
9. Mistaking a tool/infra failure for a user preference (correction-vs-noise gate;
   recurring tool failures go to `docs/tooling-gotchas.md`).
10. Dangling pointers / orphan docs / a stale index (validator checks pointer
    resolution; you own index accuracy).
11. Duplicate accumulation and compounding knowledge-base debt (garbage collection).
12. Stale/contradictory entries kept side by side (supersession replaces, not stacks).
13. Re-litigating the same rejected candidate (the extraction ledger).
14. **A session silently dropped between discovery and the summary, or dishonestly
    marked** — the validator requires `session_dispositions.jsonl` to account for every
    session `prepare` discovered with an allowed, unique status, and requires a
    `contributed` claim to be backed by real decision evidence.
15. Secrets written verbatim; silent overwrites; hallucinated learnings (validator scans
    every changed file and every decision's claim/reason for secret-like values).
16. **A stale `validation.json` authorizing changes made after validation ran** — `apply`
    always recomputes validation against the current staged files immediately before
    writing anything live, so editing `decisions.jsonl`/staging/`session_dispositions.jsonl`
    after `validate` and then running `apply` directly can never skip review.
17. **`prune` deleting the only backup an interrupted commit can recover from** — a
    backup referenced by an `in_progress` commit marker is never removed, regardless of
    its age or the `--keep` value.
18. **A decision with no evidence, evidence for the wrong session, or evidence that
    doesn't match the cited event's timestamp** — every decision requires a nonempty
    evidence array, and each entry is checked against one real normalized event by
    `session_id` **and** `event_sha256` (and `event_timestamp` when given), not just
    against a bag of known hashes.
19. **A `confidence`/`disposition` mismatch, or a write with no human signal behind it**
    — `provisional` confidence may only pair with `PROVISIONAL`; every write disposition
    requires `confirmed` confidence **and** at least one cited evidence event with
    `role: user`, so a bare tool failure can never become a map/docs write on its own.
20. **One decision authorizing an unrelated file change** — every changed memory file
    must be covered by a decision's `destination` or (for a write decision only) its
    `supporting_destinations`, and a truncated, replaced, or in-place-edited extraction
    ledger fails validation even if some other file's diff looks fine.
21. **A checkpoint or lock in an ambiguous state being trusted as either "fine" or
    "safe to discard"** — an existing but broken `watermark.json` (unreadable,
    malformed, wrong schema, non-numeric, boolean, negative, or future) stops `prepare`
    instead of silently re-bootstrapping; the extraction lock is an atomically-created
    directory with owner metadata published immediately after, and a lock directory
    that exists without valid metadata blocks new runs until `unlock-abandoned` is used
    (which itself refuses if the owning process might still be alive or an incomplete
    commit still needs it).
22. **A crafted or stale backup path fooling `recover`** — a marker's `backup` path must
    resolve under `~/.zcode`, be a direct child of it, and match the
    `extraction-backup-<timestamp>-<run_id>` naming for the exact run being recovered;
    every backup inventory path is checked for traversal, and any symlinked backup
    directory, manifest, or backed-up file is rejected before any recovery read or
    write.
23. **Learning from a message with no reliable timestamp, or one inserted after the
    run's upper bound** — the runner normalizes evidence eligibility (`is_new`) from a
    single consistent read of the session database, and the validator independently
    re-checks each cited event's epoch against the manifest's upper bound rather than
    trusting that flag alone.
24. **A tampered editable manifest being trusted because it's internally consistent** —
    `prepare` binds every security-sensitive field into a runner-controlled trusted
    control record outside the run directory (mode 0700/0600); `validate`/`apply`
    recompute the same fields from the manifest and fail the run if they don't match
    exactly, and a run with no trusted control state at all (a legacy run) is refused
    rather than trusted on the manifest alone.
25. **A backup that is internally valid but not the one the runner actually made** — the
    trusted apply state written before any live write binds the backup's path, a digest
    of its manifest, and its exact inventory/presence/hashes; `recover` rejects a backup
    manifest that doesn't match that binding even if the manifest is otherwise
    self-consistent (an empty manifest that "verifies fine," or one with an extra
    absent-path entry naming something the run never touched, no longer produces a false
    success or an incorrect deletion).
26. **A missing/malformed/mismatched/unrecognized commit marker being treated as "safe
    to guess about"** — `recover` requires a present, well-formed, run-id-matching
    marker with a recognized status before acting at all, and never falls back to
    searching for a plausibly-named backup by filename.
27. **A message that lands inside the window but whose session row updates just past the
    upper bound being silently dropped** — a session is discovered if *either* its
    `time_updated` is in the window *or* it has an eligible user/assistant message
    timestamped inside the window, both checked against one read snapshot.
28. **A symlink swapped in for a live target, staged file, watermark, backup source, or
    restore destination redirecting a write or read outside `~/.zcode`** — every one of
    these is preflighted for symlinked ancestors before `apply`/`recover` writes
    anything, discovering an unsafe target never leaves some destinations already
    written and others not, and a symlinked live target is a hard prepare-time error
    rather than a silently omitted baseline entry.
29. **A crafted or symlinked run directory escaping the runs root** — every command and
    metadata access that resolves a caller-supplied `--run-id` to a directory goes
    through one central, safe resolver that rejects a symlinked run-directory entry and
    enforces containment under the runs root.
30. **A malformed-lock/incomplete-commit deadlock with no sanctioned way out** — the
    operator-only `repair-recover --run-id <id> --confirm-no-process` command exists
    exactly for this: it still refuses if the lock identifies a pid that is alive, and
    on any failure preserves evidence and state exactly as `recover` would rather than
    guessing its way through.
31. **Scheduler drift silently breaking the next scheduled run** — `check-deployment` is
    a read-only command that checks the deployed automation's cron/schedule/model
    against expectations, confirms it is enabled, recurring, and active, checks the
    wrapper prompt's provenance flags and non-injection declaration, and hashes the
    deployed extraction prompt and runner copy against what's expected — catching a
    disabled automation, a wrong cron, a stale runner copy, or an edited prompt before
    it silently produces a bad or skipped run.

---

## Deployment notes (this machine — not part of the executed prompt)

Everything above this section is the behavioral prompt, byte-identical to the deployed
copy at `~/.zcode/self-improve/learning-extraction-v1.md`. To redeploy elsewhere: copy
this file (minus this appendix) to that path, then schedule it. This appendix documents
the schedule and the automation prompt used to redeploy this workflow; it is not sent to
the model.

- **Schedule:** ZCode automation `automation-ff3ba2cc-a0f7-4ed1-919b-23f8f37cd111`,
  recurring, enabled, and active, at 20:00 local every 2 days: cron display
  `0 20 */2 * *`, and the automation's own structured schedule rule
  `{"unit": "daily", "interval": 2, "hour": 20, "minute": 0}`. `check-deployment`
  verifies both the cron string and the structured rule (not just one or the other),
  plus that the automation is enabled/recurring/active and that its wrapper prompt still
  carries the right `--automation-id`/`--model-id`/`--prompt-file` flags and the
  no-AGENTS.md-injection declaration — run it read-only anytime (`python3
  /Users/sala/.zcode/self-improve/zcode_learning_extractor.py check-deployment
  --automation-id automation-ff3ba2cc-a0f7-4ed1-919b-23f8f37cd111 --model-id <model>
  --cron "0 20 */2 * *"`) to catch scheduler drift before it silently breaks a run.
- **Runner location:** this repository's canonical copy of the runner lives at
  `skills/hill-climb/scripts/zcode_learning_extractor.py`. To redeploy, copy that file
  verbatim to the fixed absolute path `/Users/sala/.zcode/self-improve/zcode_learning_extractor.py`
  — the executed prompt body above (see "Transactional runner protocol") already assumes
  that exact path, and every command must be `python3
  /Users/sala/.zcode/self-improve/zcode_learning_extractor.py <command> ...`, always
  passing absolute paths for `--zcode-home` and any `--db-path`/`--tasks-db-path`
  overrides. Never rely on the current working directory; the automation's cwd is not
  guaranteed.
- **Automation prompt** (wraps this file; self-contained — no `AGENTS.md` injection is
  assumed, per the "Context boundary" section above):

  > Execute the ZCode learning extraction defined in
  > /Users/sala/.zcode/self-improve/learning-extraction-v1.md. Read that file in full
  > first, then follow it exactly: use `python3
  > /Users/sala/.zcode/self-improve/zcode_learning_extractor.py` (this exact absolute
  > path — never a repo-relative one; the automation's cwd is not guaranteed)
  > for all database access, checkpoint changes, backups, validation, recovery, and
  > live-memory writes. After `prepare`, file tools are explicitly allowed inside the
  > printed run directory to read `manifest.json`, `normalized_sessions.jsonl`, and staged
  > memory; write `decisions.jsonl` and `session_dispositions.jsonl`; and edit only files
  > under `staging/`. Never edit runner-generated metadata or anything under
  > `~/.zcode/self-improve/extraction-control/`. Then run `validate` and `commit`. Never
  > edit `~/.zcode/AGENTS.md`, `~/.zcode/docs/**`,
  > `~/.zcode/AGENTS.extraction-log.md`, or
  > `~/.zcode/self-improve/watermark.json` directly, and never advance the watermark by
  > hand — `commit` owns that, only after every staged file is applied. This session is
  > itself a scheduled automation run; pass its own session id as `--self-session-id` to
  > `prepare` if available, and rely on the runner's `automation_runs`/`<scheduled-task>`
  > exclusions otherwise — never learn from this run or from any other
  > `<scheduled-task>` session. If `prepare` reports an incomplete prior commit, run
  > `recover --run-id <id>` for it before doing anything else. If `prepare` instead
  > fails with a watermark or automation-database error, STOP and report it verbatim --
  > do not hand-edit `watermark.json` or the tasks-index database to work around it. If
  > `recover` itself refuses (wrong lock owner, or a backup it can't verify), STOP and
  > report that too; never hand-restore files or delete the lock/marker yourself. If the
  > extraction prompt file or the runner script is missing or unreadable, STOP and
  > report that fact; do not attempt to recreate or bootstrap either. If `prepare`
  > reports `session_count: 0`, write an empty `session_dispositions.jsonl`, stage an
  > empty-run ledger note, and `commit` — an empty run is a correct run and must still
  > advance the watermark. Apply every gate before writing anything; the map
  > (`~/.zcode/AGENTS.md`) must stay ≤ 100 lines; every decision needs real, eligible
  > evidence and, for a write, a confirmed-confidence user-role citation; record every
  > candidate disposition in `decisions.jsonl` and append (never rewrite) the staged
  > ledger; if `commit`/`apply` is interrupted, run `recover --run-id <id>` before any
  > new `prepare`. Never edit anything under
  > `~/.zcode/self-improve/extraction-control/` or treat it as task content — it is
  > runner-controlled trusted state, not yours to read or write. Never invoke
  > `repair-recover` yourself; it requires a human operator's manual confirmation and
  > must never be called from an unattended automation run — if `recover` and
  > `unlock-abandoned` both refuse, STOP and report the deadlock for a human to resolve.

- **Runtime state (never commit, machine-local):**
  - `~/.zcode/self-improve/watermark.json` — incremental gate (`last_time_updated`, epoch
    ms), runner-owned; a file that exists but fails validation stops `prepare` rather
    than being treated as absent
  - `~/.zcode/self-improve/extraction.lock/` — a directory (not a bare file), containing
    `owner.json` (`run_id`/`pid`/`created_at`); present only while a run is in flight. A
    lock directory without valid `owner.json` is treated as abandoned/malformed, not as
    "unlocked" — use `unlock-abandoned` (never `rm -rf`) to clear it, or the
    operator-only `repair-recover --confirm-no-process` if an incomplete commit blocks
    `unlock-abandoned` too
  - `~/.zcode/AGENTS.extraction-log.md` — append-only ledger
  - `~/.zcode/self-improve/extraction-runs/<run_id>/` — per-run **agent-editable**
    manifest, staging, decisions, commit marker (pruned to the newest 5 by
    `commit`/`prune`)
  - `~/.zcode/self-improve/extraction-control/<run_id>/` — per-run **runner-controlled,
    never agent-editable** trusted state (mode 0700 dir, 0600 files): `control.json`
    (written by `prepare`) and `apply.json` (written by `apply`/`commit` after the
    backup is verified, before any live write); pruned alongside its run
  - `~/.zcode/extraction-backup-<timestamp>-<run_id>/` — pre-commit backups of every live
    target plus the watermark, each with a `presence.json` manifest (inventory,
    pre-run presence, and a hash per backed-up file) that `recover` verifies before and
    after restoring, and cross-checks against the trusted apply state above (pruned
    alongside runs, except one still referenced by an unresolved commit)
- **Provenance:** v1 ported from `daily-codex-learning-extraction.md` (v3); v2 replaced
  the prose-only "back up, edit live files, advance the watermark by hand" workflow with
  the transactional runner in `skills/hill-climb/scripts/zcode_learning_extractor.py`,
  modeled on `codex_learning_extractor.py`'s prepare/validate/apply/commit/recover/status/
  prune protocol but reading ZCode's SQLite session store instead of JSONL rollouts; v3
  (this version) closed gaps found in review of v2: `apply` now always recomputes
  validation against the current on-disk staging immediately before writing anything live
  instead of trusting a possibly-stale `validation.json`; `prune` now never deletes a
  backup an in-progress commit marker still points to; `session_dispositions.jsonl`
  entries are now schema-checked (status must be `contributed` or `reviewed_no_learning`,
  session ids must be unique, and a `contributed` session must be cited by some decision's
  evidence); the executed prompt body now names the actual deployed absolute runner path
  instead of a repo-relative one; the stray invitation to query `tool_usage`/`turn_usage`
  directly was removed (out of the normalized-evidence-only task boundary); and the
  "delete superseded content" gardening guidance was reconciled with the runner's
  unconditional rejection of staged file deletions (entries are removed by editing the
  file they live in, never by deleting the file). The ZCode-specific noise-strip list,
  the `automation_runs.session_id` self-exclusion, and the discovery query were validated
  read-only against the live DB on 2026-08-28 (22 in-scope sessions discovered in a 3-day
  test window; digests extracted cleanly), and the full transactional protocol —
  including the v3 fixes — is now covered by `tests/test_zcode_learning_extractor.py`
  against synthetic fixtures. v4 (this version) closed nine further gaps found in a
  follow-up review: `recover` is now state-aware and idempotent (never restores a
  `completed`/`recovered` run, refuses if a different run owns the lock, and cannot
  overwrite a later run's work) and its backup restoration fails closed on a missing
  backup, a malformed manifest, a missing backed-up file, or a hash mismatch, verifying
  the restored content afterward; every decision now requires nonempty evidence
  validated against one real normalized event (session id, hash, and timestamp when
  given), a `confidence`/`disposition` pairing (`provisional` only with `PROVISIONAL`,
  every write disposition needs `confirmed` plus a user-role citation), and every
  changed memory file must be covered by a decision's `destination` or a write
  decision's new `supporting_destinations`; the extraction ledger is now enforced as
  strictly append-only; the watermark checkpoint fails preparation closed on anything
  other than a genuinely absent file (unreadable, malformed, wrong schema, non-numeric,
  boolean, negative, or future all reject rather than re-bootstrap); the extraction
  lock is now an atomically-created directory with owner metadata published
  immediately after (never a bare create-then-write file), with a new
  `unlock-abandoned` command as the only sanctioned way to clear a malformed/abandoned
  one; session discovery and transcript normalization now share one connection and
  explicit read transaction, and a message with no timestamp or one past the run's
  upper bound is `is_new: false` (context only, never decision evidence, independently
  re-checked by the validator); recovery now validates a marker's backup path/naming
  and its inventory before any read or write, rejecting traversal and symlinked
  paths; and the automation-exclusion database is now required for `prepare` (missing,
  unreadable, missing-table, or failed-query all stop preparation instead of silently
  treating automation runs as non-excluded). v5 (this version) closed seven material
  gaps a main-agent review found in v4: the manifest now records the watermark's
  pre-run presence/hash the same way it records live memory's, so `recover`'s
  before-any-live-write abort correctly stays safe for the normal case of an
  already-existing, unchanged watermark instead of only ever succeeding on a
  from-scratch bootstrap (a legacy manifest missing that field fails closed with an
  actionable error rather than guessing); `normalized_sessions.jsonl` is now hash-pinned
  in the manifest and `validate` requires an exact match, so evidence can no longer be
  fabricated or edited after `prepare`; evidence eligibility is now independently
  re-derived from the manifest's own `lower_bound`/`upper_bound` (requiring a real
  numeric, non-boolean epoch strictly inside that window) rather than only trusting the
  event's `is_new` flag; only a write disposition's `destination` can authorize a memory
  change — a `PROVISIONAL`/`REJECTED`/`SKIPPED_DUP` decision's `destination` is now
  rejected outright instead of silently entering the authorized set;
  `supporting_destinations` is now restricted to structural index/map files (`AGENTS.md`,
  `docs/index.md`, `docs/projects/index.md`, `docs/projects/<project>/index.md`) so it
  can no longer smuggle through an arbitrary content doc; the extraction lock is now
  published via a uniquely-named sibling temp directory with fsynced metadata,
  atomically renamed into place, closing the residual window where a lock directory
  could exist without its metadata; and the backup manifest schema is now stricter —
  presence values must be real booleans, hashes must cover *exactly* the present paths
  (no missing, no extra), and inventory entries must be unique safe relative paths.
  v6 (this version) closed eight further gaps found in a second Astra-style review: the
  editable manifest is no longer trusted on its own — `prepare` binds every
  security-sensitive field into a runner-controlled trusted control record outside the
  run directory (`self-improve/extraction-control/<run_id>/control.json`, mode
  0700/0600), and `validate`/`apply`/`recover` all fail closed if the manifest doesn't
  match it exactly or if it's missing (a legacy run); before any live write, `apply` now
  binds the verified backup's path, a digest of its manifest, and its exact
  inventory/presence/hashes into trusted apply state
  (`extraction-control/<run_id>/apply.json`), and `recover` cross-checks a candidate
  backup against that binding — not just against its own internal consistency — so a
  swapped-in empty-but-valid manifest, or one with an extra unauthorized "absent" entry,
  can no longer produce a false recovery success or an incorrect deletion; `recover` now
  requires a present, well-formed, run-id-matching marker with a recognized status
  before acting at all, with no filename-based backup search ever attempted as a
  fallback; session discovery now unions sessions whose `time_updated` is in the window
  with sessions that merely have an eligible user/assistant message timestamped in the
  window, closing the case where a session's `time_updated` moves just past the upper
  bound after the message that should count as evidence already landed inside it; every
  live target, staged source, the watermark, and every backup source/restore
  destination is now preflighted for a symlinked ancestor *before* `apply`/`recover`
  writes anything (not per-file as each write happens), so discovering an unsafe target
  partway through can no longer leave some destinations already written; a symlinked
  live target is now a hard prepare-time error instead of a silently omitted baseline
  entry; every command and metadata access that resolves a caller-supplied `--run-id` to
  a directory now goes through one central `resolve_run_dir` that rejects a symlinked
  run-directory entry and enforces containment; the new operator-only `repair-recover
  --run-id <id> --confirm-no-process` command breaks the deadlock where a malformed lock
  blocks `recover` and an incomplete commit blocks `unlock-abandoned` — it still refuses
  an identifiably alive lock owner even with `--confirm-no-process`, and preserves
  evidence/state on any failure exactly as `recover` would; and the new read-only
  `check-deployment` command verifies the deployed scheduler automation's cron display
  *and* structured schedule rule, its enabled/recurring/active flags, its wrapper
  prompt's provenance flags and non-injection declaration, and the deployed extraction
  prompt's and runner's content hashes, so scheduler or file drift is caught before it
  silently breaks or skips a scheduled run.
