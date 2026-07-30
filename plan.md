# LLM Report Card — architecture and design decisions

Status: implemented and deployed. This document records what the system does and why it is built this
way. Author-facing instructions live in `README.md`; this is the design rationale behind them.

## Summary

`LLM_REPORT_CARD.md` is the single source of truth. A Vite plugin parses it at build time and inlines the
result as the `virtual:report-card` module, which a static React + TypeScript app renders as a searchable,
filterable model gallery published to GitHub Pages. There is no backend, database, CMS, account system,
analytics, or external API call. Editing the Markdown is the only step required to update the site.

The report card doubles as a hand-authored document and as structured data. Every design decision below
follows from holding that tension: authoring must stay frictionless, while the build must refuse to ship a
malformed card.

## Repository shape

npm workspaces, two unrelated concerns kept apart:

```
LLM_REPORT_CARD.md            data source — deliberately at the repo root, not inside the app
skills/                       system-prompt definitions (independent of the site)
apps/report-card/             the Vite + React site
  scripts/validate-report-card.mjs
  src/data/                   parser, types, Vite plugin, fixtures
  src/lib/                    filtering, hash routing, note rendering
  src/components/
.github/workflows/deploy.yml  CI on pull requests; build + deploy on pushes to main
```

The data file stays at the repo root because it is the human-facing artifact — it is read and edited far
more often than the app is developed, and it should not be buried under `apps/`. The app reaches it via an
explicit absolute path passed to the plugin from `vite.config.ts`, rather than resolving against the Vite
root, so the location is stated in exactly one place.

## Parsing and validation

`src/data/parseReportCard.ts` is a single-pass line scanner over the stripped document. It is hand-written
rather than built on a Markdown library because the grammar is narrow, the error messages need to be
specific, and the site otherwise carries zero runtime dependencies beyond React and its icon set.

Guarantees the parser enforces, each surfaced as `LLM_REPORT_CARD.md:<line>: <message>`:

- `##` provider, `###` model, and a table that must follow a model heading.
- Columns exactly `Aspect | Pros | Cons`; no ragged rows; no empty aspect cell.
- Model ids unique and URL-safe, derived as `<provider-slug>--<model-slug>`.
- **Aspect names validated against `CANONICAL_ASPECTS`** in `src/data/types.ts`. This is the guardrail that
  matters most in practice: without it, a typo such as `Tool use/agentic` silently mints a new aspect and a
  new filter facet on the public site, and nothing ever tells you. Near misses that differ only in case or
  whitespace are reported with the intended name suggested. Adding a real aspect means extending the
  constant first — deliberate friction, in exchange for a vocabulary that cannot drift.
- `card.aspects` is emitted in canonical order rather than first-seen order, so the aspect dropdown is
  stable regardless of the order sections happen to be authored in.

Fenced code blocks are stripped before parsing while preserving line numbers, which is what allows the
file's own "How to use" template to sit in the document without being read as data.

Cells hold multiple notes separated by top-level semicolons, with semicolons inside parentheses treated as
literal. This is a small bespoke convention, and it is the main cost of keeping the source hand-authorable
in Markdown; it is documented in `README.md` and covered by `splitNotes` tests.

## Testing strategy

The tests were originally asserted against the live report card, and CI broke twice on `main` because of
it — merging two Gemini entries changed a model count from 15 to 14 and failed four assertions that had
nothing to do with the change. The rule now:

- **Behavior is tested against fixtures.** `src/data/__fixtures__/` holds a representative card covering
  multiple providers, all ten aspects, empty cells, multi-note cells, nested-parenthesis semicolons,
  escaped pipes, a fenced template, and inline backticks. Assertions against it are exact and strict,
  because the fixture never changes underneath the suite.
- **The live document gets one smoke test**, asserting only invariants true of any valid card: it parses,
  ids are unique and URL-safe, each model resolves to a provider that contains it, the flattened model
  count equals the sum of per-provider counts, and every aspect is canonical. No hardcoded counts, names,
  or note text.
- **Component tests derive their expectations** from the imported data rather than naming models. Where a
  test needs a specific shape — a provider with exactly one model, a term appearing in only one note — it
  computes it at run time.
- **`npm run validate` checks the real document**, separately from the test suite, and CI runs it before
  the tests so a content error reports as `file:line` rather than as a Vite build failure.

The net effect: editing `LLM_REPORT_CARD.md` cannot fail the test suite. It can only fail validation, and
only for a genuine schema violation.

## Interface and interaction

- Landing view is a provider-grouped gallery with client-side search across model names, providers, aspect
  names, and note text, plus provider and aspect filters.
- Selecting a model opens an accessible modal (`role="dialog"`, `aria-modal`, focus moved in, focus
  trapped on Tab, Escape to dismiss) containing the complete Pros/Cons table.
- The selected model is mirrored in the URL fragment so links are shareable. Opening pushes a history
  entry; closing uses `replaceState`, so Back after dismissing a sheet returns where the user came from
  instead of reopening the sheet.
- Note text renders backtick-delimited spans as `<code>` via `src/lib/renderNote.tsx` — React nodes, not
  `dangerouslySetInnerHTML`, so content stays escaped. Without this, notes referring to identifiers such
  as `xdr_indicators` displayed their backticks literally.
- Apple-inspired presentation: system typography, restrained transform/opacity transitions, translucent
  navigation, light and dark appearance, and honest `prefers-reduced-motion` / `prefers-reduced-transparency`
  fallbacks. No decorative or auto-playing motion.
- The page states plainly that this is subjective personal observation, not benchmark data.

## CI and deployment

One workflow, two jobs. `ci` (lint, format check, validate, test, build) runs on pull requests, pushes to
`main`, and manual dispatch. `deploy` is guarded to skip pull requests entirely, so a fork PR structurally
cannot publish.

Concurrency is scoped per job rather than per workflow. CI runs cancel their own superseded runs per ref;
deploys serialise instead of cancelling, because interrupting a live Pages deployment can leave the site
half-published. Under the previous single workflow-level `pages` group, a new push could cancel a
deployment already in flight.

Node version is declared once in `.nvmrc` and consumed by both `engines.node` and `setup-node`'s
`node-version-file`, so local and CI cannot drift apart.

## Known limitations and deferred work

- **No time dimension.** The card records current state, but the subject matter is fast-moving models and
  some notes are already implicitly temporal ("did not like Opus 4.7 or 4.8 *at their initial launch*").
  Dated, append-only observation records — one per note, with a stable model id separate from the display
  name — would fix that, allow recency sorting, remove the empty-cell ceremony, and make a model rename
  stop being a URL-breaking change. This was considered and deliberately deferred to keep the authoring
  experience unchanged.
- **The ten-aspect grid is mostly empty** (roughly half of all aspect rows have no notes), because every
  model carries a full table whether or not there is anything to say. A record-per-observation model would
  remove this.
- **Side-by-side model comparison** is not implemented.
- **Type-aware linting** (`typescript-eslint` `recommendedTypeChecked`) is not enabled.
- **`Unknown Provider`** is a real provider section, not scaffolding — it holds notes on a model whose
  vendor is undisclosed. It should be re-homed if the vendor is ever identified.
