# cherry-hillclimb

Daily prompt hill-climbing harness for a Cherry Studio assistant: reads that assistant's
own recent chat history, extracts gated/evidenced learnings via an LLM, and proposes a
justified edit to its own system prompt for human review before anything is applied.

This file is written for an LLM/agent invoking these scripts in a future session with no
other context. Read it before running anything or modifying this harness.

## Quick start (exact order)

```bash
# one-time: put the Cherry Studio API key where config.mjs looks for it
echo 'CHERRY_API_KEY=cs-sk-...' > ~/.cherry-hillclimb.env   # get the key from
                                                              # Cherry Studio > Settings > API Server
chmod 600 ~/.cherry-hillclimb.env

cd /Users/sala/Downloads/Personal/llm-skills
npm run cherry:debug     # (re)launches Cherry Studio with a CDP debug port; idempotent
npm run cherry:propose   # extract last 24h + analyze; writes candidate.md + a report; applies nothing
npm run cherry:diff      # print the current.md -> candidate.md diff for review
npm run cherry:apply     # push the reviewed candidate.md into the live assistant
```

All four `cherry:*` scripts default to the assistant named **Personal**. To target a
different assistant: `npm run cherry:propose -- --assistant "Career"` (same flag on
`diff`/`apply`; must match an existing assistant name exactly, or the run aborts).
`propose` also takes `-- --hours <n>` (default 24) and `-- --model <id>` (default: see
"Model selection" below).

`apply` is a **separate, explicit step** from `propose` on purpose — nothing is ever
written to the live app just from running `propose`. Always read the report and
`cherry:diff` output before running `apply`.

## What gets written where

- `prompts/cherry-studio/<slug>/current.md` — snapshot of the live prompt at the start of
  the most recent `propose` run, with its sha256 in an HTML-comment header. `<slug>` is the
  assistant name lowercased/hyphenated (`Personal` → `personal`).
- `prompts/cherry-studio/<slug>/candidate.md` — the analyzer's proposed replacement prompt
  (raw text, no header). Identical to `current.md`'s prompt content when nothing was
  confirmed-and-justified.
- `prompts/cherry-studio/<slug>/history/<timestamp>.md` — a snapshot taken immediately
  before every `apply`, for rollback.
- `prompts/cherry-studio/<slug>/CHANGELOG.md` — appended on every successful `apply`.
- `reports/cherry-hillclimb/<date>-<slug>.md` — one report per `propose` run: learnings
  kept/rejected with reasons, and the diff.

## Decisions made while building/testing this (2026-08-02) — do not "simplify" these away

1. **Launching the debug-port build.** `restart-debug.sh` launches Cherry Studio with
   `open -a "/Applications/Cherry Studio.app" --args --remote-debugging-port=$PORT`, **not**
   `nohup ... &`. This was verified the hard way: a plain `nohup "$APP_BIN" ... & disown`
   started inside a sandboxed/PTY shell session gets its whole process group reaped the
   moment that shell session ends, even with `disown` — the app would launch, respond on
   the debug port for a few seconds, then silently vanish with no crash log. `open -a`
   detaches the process via macOS launchservices instead of the invoking shell, and
   survives fine. If you ever rewrite this script, keep using `open -a`.
2. **Analyzer model choice.** `lib/analyze.mjs` hardcodes a preference list
   (`PREFERRED_MODEL_SUFFIXES = ["gpt-5.6-terra", "gpt-5.6-sol", "claude-opus-5"]`) instead
   of just taking `GET /v1/models`'s first entry. Verified: that first entry was
   `claude-sonnet-5` (via Cherry Studio's local `cpa` provider), and given the exact same
   analyzer persona + payload it replied conversationally instead of returning JSON — it
   treated the transcript-to-analyze as a conversation to continue rather than data to
   analyze. `gpt-5.6-terra` complied reliably in the same test. If `propose` starts failing
   with `Analyzer did not return valid JSON`, check whether Cherry Studio's model list
   changed and update this preference list — don't just revert to taking the first model.
3. **Assistant id vs. name.** The **Personal** assistant's `id` is literally the string
   `"default"` — which is *also* the id of a completely separate object,
   `state.assistants.defaultAssistant` (a permanently-empty-prompt placeholder Cherry
   Studio ships with, unrelated to any user-named assistant). `lib/assistant.mjs` resolves
   assistants **by `name`** from the `assistants` array only, and explicitly asserts the
   match isn't that empty-prompt sibling. Never resolve by id alone.
4. **Career/Personal prompt collision.** As of 2026-08-02, the **Career** assistant
   happened to carry a byte-identical prompt to **Personal** (same Hindsight memory
   protocol pasted into both). This harness only ever writes to the assistant named on the
   command line; once Personal's prompt is edited they will diverge from Career — that is
   expected, not a bug, and does not need reconciling.
5. **Evidence is re-verified, not trusted.** The analyzer persona is instructed to cite a
   verbatim quote per learning, but `lib/analyze.mjs`'s `enforceEvidenceGate` independently
   checks every `confidence: "confirmed"` learning's quote against the actual extracted
   transcript text before it's allowed to justify a prompt edit. If zero learnings survive
   verification, `candidate_prompt` is forced back to the original regardless of what the
   model returned — a model can propose edits, but only programmatically-verified evidence
   can make them stick.
6. **Drift guard on apply.** `apply.mjs` reads `current.md`'s recorded sha256 and compares
   it to the *live* prompt's sha256 before writing anything. If they don't match (e.g. you
   edited the prompt in the Cherry Studio UI after `propose` ran, or a stale `current.md`
   from a `--hours 0` dry run is lying around), it refuses and tells you to re-run
   `propose`. This was verified live: it correctly blocked an apply attempt after the live
   prompt had moved on from what `current.md` recorded.
7. **Pre-apply snapshot + post-apply verification.** Every `apply` writes a timestamped
   pre-apply snapshot to `history/` *before* dispatching the change, then re-reads the live
   state afterward and compares it to `candidate.md`. On a mismatch it automatically
   re-dispatches the pre-apply snapshot (best-effort rollback) and exits non-zero — don't
   assume a non-crashing dispatch means the write succeeded; the script already checks this
   for you.
8. **Protected baseline in the persona.** The analyzer persona
   (`skills/hill-climb/cherry-studio-personal-prompt-hillclimb.md`) is instructed to treat
   the existing Hindsight memory operating protocol section of the prompt as protected —
   additive/refining edits only, never removed or weakened, unless there's direct confirmed
   evidence the user asked for that. This is enforced by instruction only (not code); if you
   change the target assistant's prompt structure, re-check this still makes sense.

## Live-tested end-to-end (2026-08-02)

Resolution, extraction (26 messages / 3 topics over a real 24h window), analysis
(3 confirmed learnings applied, 2 correctly demoted to provisional, 3 correctly rejected
for failing the generalization gate), apply, persistence across an app restart, rollback to
the exact original prompt (sha256 `10ecbd328d57ec23a9a65786040a1be56ffd75f4a44ed35f73f6bda1e9749c3f`
confirmed byte-identical after rollback), and the drift guard were all exercised against the
real running app — not just written and assumed to work.

## Troubleshooting

- `Cannot reach Cherry Studio debug port 9223` → run `npm run cherry:debug` first (safe to
  re-run any time; it quits and relaunches Cherry Studio if needed).
- `CHERRY_API_KEY not set` → Cherry Studio → Settings → API Server → copy the key (starts
  `cs-sk-`) into `~/.cherry-hillclimb.env` as `CHERRY_API_KEY=...`, or `export` it.
- `Analyzer did not return valid JSON` → the selected model didn't follow the persona's
  JSON-only instruction; see decision #2 above.
- `No assistant named "X" found` / `N assistants named "X" found` → check the exact
  assistant name in Cherry Studio; `--assistant` must match exactly and uniquely.
- `Live prompt ... no longer matches the proposal's current.md snapshot` → the prompt
  changed since `propose` ran (UI edit, or a stale dry-run); re-run
  `npm run cherry:propose`.
- `Missing current.md/candidate.md` on `apply`/`diff` → run `propose` first for that
  assistant.

## Environment variable overrides

- `CHERRY_DEBUG_PORT` (default `9223`) — CDP debug port, used by `restart-debug.sh` and
  `lib/cdp.mjs`. Must match between the two.
- `CHERRY_API_BASE` (default `http://127.0.0.1:23333`) — Cherry Studio's local API server.
- `CHERRY_API_KEY` — required; see Quick start.
