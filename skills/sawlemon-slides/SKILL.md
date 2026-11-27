---
name: sawlemon-slides
description: Build Sawlemon YouTube explainer slide decks — minimal, big-word HTML slides in the locked "Paper Punch" brand style, with step-by-step animated diagrams for attack flows, plus a speaker-notes markdown file. Use when the user invokes /sawlemon-slides or asks for slides/PPT/a deck to explain a vulnerability, breach, or tech story for a Sawlemon video.
---

# Sawlemon slides

Sawlemon is a Tanglish cybersecurity YouTube channel. The slides are **something for viewers to look at while the user
talks**. They are not a document. Slide text is English. Detailed explanations go in the speaker notes and in chat,
never on the slide.

Invocation: `/sawlemon-slides "<Topic>" [notes/links]`. Output goes in the video folder used by the `sawlemon-video`
skill: `<library>/<Topic>/slides/` (library = `/Users/sala/Downloads/Personal/sawlemon/media/temp files`).

## Locked brand style: Paper Punch (do not offer alternatives)

The style is cream paper with a dotted grid, black Inter Black uppercase headings, red `#FF3131` accents, yellow `#FFD23F`
highlights, thick black borders with hard offset shadows, a Permanent Marker kicker, and a SAWLEMON footer bar.
It matches the user's thumbnail style. It is fixed in `assets/theme.css`.

- **Never** propose the neon/synthwave style. The user rejected it as "awful, AI-generated garbage". Do not
  run a style bake-off unless the user asks for one. If they do, any dark alternative must also come in a light version.

## Content rules (the user's "golden rule")

- Use **a few big words per slide**: a title, then 3–4 words per box, then at most one short punch line. Write no
  paragraphs, and keep each slide well under 20 words (excluding names/IDs).
- Use large type only. Never shrink fonts to fit more text. Cut text instead.
- **Show, don't write.** Explain any mechanism (request flow, memory, auth chain) as a **step-by-step diagram**
  (`data-steps`), so each → press changes the picture. Do not explain it in a block of text.
- Keep one analogy for the whole deck (e.g. PHP = hotel, worker = room, request = guest, reset = housekeeping), and
  pair it with the real technical term.
- Go technical straight away where the user asks, using real terms (`memory_limit`, use-after-free) explained simply.
- Always end with an **"In one sentence"** summary slide, then the SAWLEMON outro and a small sources line.
- Facts must come from primary sources (vendor advisory, researcher blog, CVE/GHSA, CERT/CISA). Verify versions,
  dates, CVSS and researcher full names. Put the names on screen; the user shows credits on screen.

Typical flow (11 slides): title → what is X → analogy → where it breaks → bug #1 (steps) → bug #2 (steps) → attack in
3 moves → how bad → twist/context → fix → one sentence.

## Workflow

1. **Recall, then research.** Use Hindsight `recall` first. Then confirm the facts from primary sources (Exa search/fetch).
2. **Scaffold:**
   `python3 -I <skill>/scripts/build.py init "<library>/<Topic>/slides" --title "<Topic>" --topic "<Topic> · explained simply"`
   This writes `slides.html` (starter) and `deck.json`. It never overwrites an existing `slides.html`.
3. **Write `slides.html`.** Copy patterns from `examples/php2shell/slides.html`, which is a proven, user-approved deck.
   Building blocks:
   | Pattern | Classes |
   |---|---|
   | Title | `s-title`, `h1.mega` (one `.hl` box), `.lead`, `.chips` |
   | Statement + big stat | `s-php`, `.split`, `.lead.big`, `.stat .num/.lbl`, `.punch` |
   | Analogy flow | `.flow > .node(.main/.good)` + `.arrow` + `.rule` |
   | Three beats | `.beats > .beat(.hot)` + `.arrow` + `.punch` |
   | Progress bar visual | `.membar` (`.mb-track`, `.mb-limit`) |
   | Numbered moves | `.steps > .step(.hot) > .n/.ico/h3/p` |
   | Four facts + meter | `.grid4 > .card.row`, `.meter` |
   | Versions / fix | `s-fix`, `.versions .v`, `.punch` |
   | Step-by-step diagram | `section.s-anim[data-steps=N]`, `.lane .lchip`, `.diagram` (absolute px children), `.caprow .cap`, `.shell` |
   **Step-by-step mechanics:** add `data-show="n"` (and optionally `data-hide="m"`) to any element so it shows only
   while n ≤ step < m. Add `fx` to fade it. Captions are `.cap.fx` with exactly one per step (the step number badge
   comes from `data-show`). Lane chips highlight which request is running. The stage is a fixed 1920×1080, so you can
   position diagram parts in absolute px (see `.blk`, `.slot`, SVG `.ptr` arrow in the example). Use `.s-xxx[data-cur="n"]`
   for step-specific effects.
4. **Build:** `python3 -I <skill>/scripts/build.py build "<deck-dir>"` writes a self-contained `deck.html`. Fonts
   load from Google Fonts, so internet is needed.
5. **Verify visually.** Serve the folder (`python3 -I -m http.server 8765 --bind 127.0.0.1`, in the background) and open
   `deck.html?still#1` in the in-app browser at 1920×1080. `?still` turns off animations. `#5.3` jumps to slide 5, step 3.
   Run `assets/check-layout.js` through `tab.playwright.evaluate`; it must return `[]`. Then screenshot every slide and
   every step and look at them. Fix awkward wraps with `&nbsp;`. Inside flex containers, wrap mixed text in
   a single element so `.hl` spans don't get gaps.
6. **Speaker notes:** write `speaker-notes.md` next to the deck. Give each slide simple-technical-English bullets
   (short sentences, real terms, no extra detail), give step slides one bullet per → press, and add a quotable
   **one-liner** for the key slides. Include the details cut from the slides (stopgap configs, affected setups, credits,
   sources). The example is in `examples/php2shell/speaker-notes.md`.
7. **Report:** give links to `deck.html` and `speaker-notes.md`, say what was checked (overflow result, which
   slides/steps were viewed), and list anything not verified.

## Presenting

Use → / Space / click-right for the next step or slide and ← / click-left to go back. F toggles fullscreen. Home and End
jump to the first and last slide. Dots in the top-right show the build step.
