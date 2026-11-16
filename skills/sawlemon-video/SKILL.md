---
name: sawlemon-video
description: Sawlemon YouTube video production workflow — collect b-roll images/logos/screenshots, generate Tanglish SRT subtitles from audio, generate the cartoon thumbnail character, and write titles, description, X post and pinned comment. Use when the user invokes /sawlemon-video or asks for any of these steps for a Sawlemon video.
---

# Sawlemon video workflow

Sawlemon is a Tanglish (Tamil + English) cybersecurity YouTube channel, edited in Final Cut Pro, thumbnails composed in Canva.
Four stages, run in order or individually: **assets → subtitles → thumbnail → metadata**.
Invocation: `/sawlemon-video <stage|all> "<Video Name>" [inputs]`. If the stage or video name is missing, infer it from the
request; ask only if it cannot be inferred.

Everything stays local. Never upload, post or publish anything. Never overwrite existing files (scripts append `-2`, `-3`).
Verify every output and report exactly what was checked; if something failed or was skipped, say so.

## Setup facts

- Scripts: `scripts/` in this skill. Run with `python3 -I <skill>/scripts/<name>.py ...` (stdlib only, ffmpeg needed for subtitles).
- Models go through the local cliproxyapi (`config.json`; key read from its config, never printed):
  - `gemini-3.8-flash-high`: subtitles and metadata. It is the only model on the proxy that accepts audio. GPT and Claude
    models reject audio; the gemini-4-* models are not available on the free account.
  - `gpt-image-2.5-flare`: thumbnail character, **medium** quality by default (about 1–1.5% of the 5-hour GPT window
    per image). Use `high` only when the user asks.
- Per-video folder: `<library>/<Video Name>/` (library = `media/temp files`). It holds b-roll, `Readable close-ups/`,
  `SOURCES.md`, the `.srt`, metadata files, `social.md`, and `video.json` (stage state + key terms). Read `video.json`
  first to resume an interrupted video.
- Generic reusable logos go in the library root, not the video folder.

## Stage 1: assets (b-roll)

Input: a list of things the user wants on screen (logos, sites, repos, articles, diagrams).

1. `assets.py have <names...>` to see which logos already exist. Do not re-download those.
2. For each missing item, find the official source (official site, press kit, GitHub repo, Wikimedia). Prefer SVG → render
   to PNG with `sips -s format png in.svg --out out.png`; otherwise the largest official PNG.
3. Logos: PNG with genuine transparency, saved in the library root as `<brand>-logo-transparent[-<size>].png`. If only a
   light version exists, say it is for dark backgrounds in the name or notes.
4. Screenshots must be readable on a phone: open the page in the in-app browser (`browser-use:control-browser` skill) with
   viewport 2560x1440 (or 3840x2160), set `document.documentElement.style.zoom = 2–2.5`, capture the viewport, then crop
   tightly with `sips --cropToHeightWidth H W --cropOffset Y X`. Capture only the core content: no sidebars, nav, cookie
   banners or empty margins. Split dense pages into several close-ups instead of one shrunken full page. Do not
   stitch full-page screenshots of animated sites.
5. Put video-specific images in the video folder. Use numbered descriptive names (`01-...`, `02-...`), with close-ups in
   `Readable close-ups/`.
6. Write `SOURCES.md` in the video folder: file, what it shows, source URL, credit/licence notes. Flag non-commercial
   licences (e.g. xkcd CC BY-NC). Mark reconstructions/illustrations as such. Never present one as an authentic
   screenshot. Record researcher/author full names here; they go into the description later.
7. Diagrams the user asks for (e.g. a dependency chain): draw them as SVG and render with sips to a transparent 1920x1080 PNG.
   Never claim an image was generated unless the file exists locally.
8. Run `assets.py check "<Video Name>"` (and `check-file` for new root logos). Every file must pass. Then look at the
   images yourself (Read tool) before reporting.
9. Record the key names/terms of the story (products, vulnerability names, people, companies) with their exact spelling:
   they are passed to the subtitle and metadata stages.

## Stage 2: subtitles

```
python3 -I scripts/subtitles.py "<Video Name>" /path/to/audio.m4a --terms "Hacktron AI, HEIF Heist, libheif, ImageMagick, Discourse"
```

- Always pass `--terms` with the names from stage 1 or the user (stored in `video.json` and reused later). Without it,
  Gemini mis-hears names (e.g. "HEIF Heist" became "HeapHeist").
- The script splits the audio at pauses into ~1-minute chunks, transcribes each one, and retries bad chunks: hour-long
  timelines, zero-length cues or no cues. It reads malformed timestamps, rescales a stretched timeline, romanizes any
  Tamil-script lines in a text-only pass, wraps to 2 lines, and checks ordering.
- After it finishes: read the printed NOTES, grep the SRT for the key terms, and spot-read a few cues. Report the cue
  count, end time vs audio length, and anything unresolved. Timings are approximate (typically within ~1–3 s); tell the
  user to spot-check in Final Cut. Subtitles are verbatim; do not "correct" what the speaker said (e.g. keep "transient"
  in subtitles even though the right term is "transitive").

## Stage 3: thumbnail character

The user designs the thumbnail in Canva. This stage only produces the transparent character PNG.

```
python3 -I scripts/thumbnail.py "<Video Name>" <slug> "<expression and pose>" [--quality medium|high] [--ref PATH]
```

- Default reference: `media/thumbnail/cartoon-avatar-REFERENCE.png` (the user's cartoon self). Describe expression +
  pose concretely, e.g. "furious, out for revenge, punching his fist into his open palm".
- The script asks for a transparent background, makes the character fully opaque (the model returns alpha 250–254),
  keeps the raw output in `angry-avatar-originals/`, and warns if the character is cut off at the top or sides.
- Look at the result yourself. If it is cut off or off-model, tell the user and offer a re-roll (medium) rather than
  silently regenerating.
- Previous thumbnail style the user likes: white card, logo row, three huge Inter Black uppercase lines with the middle
  one red (#FF3131), cartoon character on the right.

## Stage 4: metadata (titles, description, X, pinned comment)

```
python3 -I scripts/metadata.py "<Video Name>"
```

1. The script runs the user's own prompt (`prompts/title-description.md`, verbatim; do not edit it without asking) on the
   SRT with Gemini, saves `metadata-draft.md`, runs mechanical checks (title < 70 chars, Tamil script in every title,
   ≤ 500 words, 10–15 tags, sane timestamps, wrong terms), and runs a Gemini fact-check against the subtitles. Output:
   `metadata-check.json`.
2. You then write `metadata-FINAL.md` from the draft. Keep its style, because the user prefers Gemini's punchy titles. Only fix:
   - every fact-check issue and mechanical issue (unsupported claims like "root access", wrong attribution like
     "ChatGPT RCE" when the RCE was on a forum server, transient → transitive, mis-heard names from `--terms`);
   - promises the speaker makes ("full names description-la") → add a **Research credit** block with full names and the
     original source link from `SOURCES.md`;
   - timestamps: check each against the SRT.
   Then re-read the fact-check yourself against the SRT, because the model check misses things. Tell the user exactly
   what you changed and why.
3. X post (`social.md`): one post per language option (English and Tanglish), ≤ 280 by X's weighted count. Check with
   `scripts/social.py count "<text>"`: emoji, arrows and Tamil script count 2, links count 23. Include a hook, the key
   chain, "Full breakdown in Tamil 👇", the video link placeholder `https://youtu.be/XXXXXXXXXXX`, and 3–4 hashtags.
   Add a reply post with research credits + source link. Do not tag handles you have not verified.
4. Pinned YouTube comment: `scripts/social.py pinned tanglish` (or `english`), which uses the X / LinkedIn links in `config.json`.

## Reporting

End each stage with: files written (as links), what was verified and how, what was not verified, and the one next action
for the user. Keep it short and non-technical.
