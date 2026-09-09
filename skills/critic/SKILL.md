---
name: critic
description: Critique completed work, score its professional readiness out of 10, and return only evidence-backed improvements. Use when the user asks to criticise, critique, rate, grade, assess, or visually review code, websites, documents, writing, prompts, or the latest completed work.
---

# Critic

Review the work without changing it. Judge evidence, not effort or intent.

## Choose the target

1. Review the exact file, URL, branch, diff, artifact, brief, or acceptance criteria named by the user.
2. If no target is named, infer the latest completed work from the current conversation, recent tool activity, changed files, generated artifacts, or current repository state.
3. Do not silently switch to unrelated work. If no target is defensible, output only the information needed to identify one and do not score.

## Set the standard

1. Prefer the original request, specification, acceptance criteria, repository instructions, intended audience, and intended use.
2. When those are incomplete, apply professional standards appropriate to the artifact.
3. Treat `10/10` as ready for its intended audience or use with no material improvement to recommend. It does not require exceptional or award-level work.
4. Use integer scores consistently:
   - `10`: no material improvement found
   - `8-9`: ready, with minor improvements
   - `6-7`: usable, but notable improvements remain
   - `4-5`: major problems prevent professional readiness
   - `1-3`: substantially incomplete, incorrect, or unusable
   - `0`: no meaningful deliverable to assess

## Inspect and verify

1. Read the relevant instructions, source, request, and final artifact.
2. Run relevant non-destructive checks when available. These may include tests, builds, linting, link checks, source inspection, document rendering, and browser interaction.
3. Do not claim a check passed unless you ran it and observed the result. Do not lower a score for a check that is irrelevant to the intended use.
4. Never edit files, apply fixes, post comments, create issues, commit, or push.

## Require visual evidence when presentation matters

- For websites and web applications, use Browser Use to load the rendered interface, exercise important interactions and states, and inspect relevant viewport sizes. Source inspection alone is insufficient.
- For PDF, DOCX, slides, spreadsheets, and similar documents, open or render the deliverable, inspect every page, slide, or sheet at overview level, then inspect questionable parts at full size. Extracted text alone is insufficient.
- For writing and prompts, visual inspection is unnecessary when plain text is the deliverable. Inspect the rendering when typography, pagination, tables, layout, or presentation affects quality.
- For non-interface code, configuration, scripts, and plain text, use source evidence and deterministic checks unless their output has a material visual component.

Browser and desktop visual control are main-agent work. Do not delegate them. If required visual evidence cannot be opened or rendered, do not score. Output only the missing access, application, export, or rendering step needed for a valid review.

## Use expensive review sparingly

Use the main agent and deterministic tools by default. Do not use Astra for routine reviews. Use at most one narrowly scoped Astra pass only when the artifact spans several domains, the standard is genuinely ambiguous, or an independent judgment is likely to change the score.

## Output only the verdict and improvements

For a completed review, use this form:

```markdown
Score: 6/10

- [Critical] Concrete problem. Evidence: exact file, line, page, screen, or observed behavior. Improve it by doing X.
- [Major] Concrete problem. Evidence: exact file, line, page, screen, or observed behavior. Improve it by doing Y.
- [Minor] Concrete problem. Evidence: exact file, line, page, screen, or observed behavior. Improve it by doing Z.
```

Order findings by impact. Include only changes that would materially improve the work. Every item must give specific evidence and a concrete improvement. Merge duplicates and omit unsupported preferences.

Do not include praise, strengths, a recap, process narration, a checks section, a generic conclusion, or an invitation for follow-up. If no material improvement is found, output only `Score: 10/10`. If the review is blocked, omit the score and output only the blocker and exact unblocking step.
