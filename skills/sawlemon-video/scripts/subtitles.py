"""Stage 2: audio -> validated Tanglish SRT via Gemini, transcribed in ~1-minute chunks cut at pauses.

Usage: python3 -I subtitles.py "<Video Name>" /path/to/audio.(m4a|mp3|wav|mov)
Writes <library>/<Video Name>/<Video Name>.srt (never overwrites) and records it in video.json.
"""
import base64
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

TIME = re.compile(r"\d{1,2}(?:[:.,]\d{1,3}){1,3}")
TAMIL = re.compile("[\u0b80-\u0bff]")
PROMPT = (common.SKILL_DIR / "prompts" / "transcribe.md").read_text()


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]).stdout)


def cut_points(mp3, total):
    """Pause midpoints closest to each whole minute, at least 35 s apart (background music needs -25 dB)."""
    log = subprocess.run(["ffmpeg", "-i", str(mp3), "-af", "silencedetect=noise=-25dB:d=0.25", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    mids = [(s + e) / 2 for s, e in zip(starts, ends)]
    cuts, target = [], 60.0
    while target < total - 30:
        prev = cuts[-1] if cuts else 0.0
        cands = [m for m in mids if m - prev > 35 and m < total - 20]
        if not cands:
            break
        best = min(cands, key=lambda m: abs(m - target))
        if abs(best - target) > 25:  # no pause near this minute: hard cut rather than a giant chunk
            best = target
        cuts.append(round(best, 2))
        target = best + 60
    return cuts


def parse_time(token):
    """Seconds from HH:MM:SS,mmm and the malformed variants Gemini emits (MM:SS:mmm, MM:SS,mmm, HH:MM:SS)."""
    parts = re.split(r"[:.,]", token)
    if len(parts) == 4:
        h, m, s, ms = parts
    elif len(parts) == 3 and len(parts[2]) == 3:
        h, (m, s, ms) = "0", parts
    elif len(parts) == 3:
        (h, m, s), ms = parts, "0"
    else:
        (m, s), h, ms = parts, "0", "0"
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def fmt(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def parse_chunk(text, dur):
    """Return (cues, problems). Cues are [start, end, text] relative to the chunk."""
    cues, problems = [], []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l.strip() for l in block.strip().splitlines() if l.strip()]
        idx = next((k for k, l in enumerate(lines) if "-->" in l), None)
        if idx is None:
            continue
        times = TIME.findall(lines[idx])
        if len(times) != 2:
            problems.append(f"unreadable timestamp {lines[idx]!r}")
            continue
        s, e = parse_time(times[0]), parse_time(times[1])
        body = " ".join(lines[idx + 1:])
        if cues and s < cues[-1][0] - 0.05:
            problems.append(f"out of order at {s:.2f}s")
        cues.append([s, e, body])
    if not cues:
        problems.append("no cues")
    else:
        if max(c[1] for c in cues) > dur * 1.2:
            problems.append(f"timeline runs to {max(c[1] for c in cues):.1f}s for a {dur:.1f}s clip")
        crushed = sum(e - s < 0.3 for s, e, _ in cues)
        if crushed >= 2:
            problems.append(f"{crushed} zero-length cues (timing drifted)")
    return cues, problems


def romanize(cues, model):
    """Replace any Tamil-script text with romanized Tanglish via a text-only Gemini pass. Returns tokens used."""
    todo = [{"id": i, "text": c[2]} for i, c in enumerate(cues) if TAMIL.search(c[2])]
    if not todo:
        return 0
    instruction = ("These are subtitle lines from a Tanglish (Tamil + English) YouTube video. Rewrite each one so that every "
                   "Tamil-script word is written in romanized English letters, the way Tamil speakers type Tanglish "
                   "(e.g. வந்து -> vandhu, பண்ணிருக்காங்க -> pannirukaanga, அப்படின்னா -> apdina). Keep English words, "
                   "word order and meaning exactly the same. Do not translate or summarise. Return a JSON array of "
                   "objects with the same ids: [{\"id\": 0, \"text\": \"...\"}].\n\n")
    tokens = 0
    for attempt in (1, 2):
        text, usage, _ = common.gemini(model, [{"text": instruction + json.dumps(todo, ensure_ascii=False)}],
                                       {"temperature": 0.1, "responseMimeType": "application/json"})
        tokens += usage.get("totalTokenCount", 0)
        text = re.sub(r"^```\w*\s*|\s*```$", "", text.strip())
        try:
            fixed = {int(o["id"]): o["text"] for o in json.loads(text)}
        except (ValueError, KeyError, TypeError):
            print(f"romanize try {attempt}: unparseable reply")
            continue
        for item in todo:
            new = fixed.get(item["id"])
            if new and not TAMIL.search(new):
                cues[item["id"]][2] = new
        todo = [{"id": i, "text": c[2]} for i, c in enumerate(cues) if TAMIL.search(c[2])]
        print(f"romanize try {attempt}: {len(todo)} lines still contain Tamil script")
        if not todo:
            break
    return tokens


def transcribe_chunk(path, dur, model, terms):
    mm, ss = divmod(dur, 60)
    end = f"00:{int(mm):02d}:{ss:06.3f}".replace(".", ",")
    prompt = PROMPT.replace("{DURATION}", f"{dur:.2f}").replace("{CLIP_END}", end)
    if terms:
        prompt += ("\nNames and technical terms that occur in this video. When you hear them, spell them exactly like this: "
                   + ", ".join(terms) + "\n")
    parts = [{"inlineData": {"mimeType": "audio/mp3", "data": base64.b64encode(path.read_bytes()).decode()}},
             {"text": prompt}]
    return common.gemini(model, parts, {"temperature": 0.2, "maxOutputTokens": 32768})


def two_lines(words):
    text = " ".join(words)
    if len(text) <= 42 or len(words) < 2:
        return text
    k = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:k]) + "\n" + " ".join(words[k:])


def finish(cues):
    """Repair near-zero cues, split >84-char cues, wrap to 2 lines, remove overlaps."""
    for k in range(1, len(cues)):
        prev, cur = cues[k - 1], cues[k]
        if cur[1] - cur[0] < 0.6:  # squeezed cue shares the previous span, split by text length
            a, b = prev[0], max(cur[1], prev[1])
            mid = a + (b - a) * len(prev[2]) / (len(prev[2]) + len(cur[2]))
            prev[1], cur[0], cur[1] = mid, mid, b
    out = []
    for s, e, t in cues:
        groups, cur = [], []
        for w in t.split():
            if cur and len(" ".join(cur + [w])) > 84:
                groups.append(cur)
                cur = []
            cur.append(w)
        groups.append(cur)
        if len(groups) > 1 and len(groups[-1]) <= 2:
            groups[-2].extend(groups.pop())
        total = sum(len(" ".join(g)) for g in groups)
        t0 = s
        for g in groups:
            t1 = t0 + (e - s) * len(" ".join(g)) / total
            out.append([t0, t1, two_lines(g)])
            t0 = t1
    for a, b in zip(out, out[1:]):
        a[1] = min(a[1], b[0])
    return out


def main():
    args = sys.argv[1:]
    terms = []
    if "--terms" in args:
        i = args.index("--terms")
        terms = [t.strip() for t in args[i + 1].split(",") if t.strip()]
        del args[i:i + 2]
    if len(args) != 2:
        common.die('usage: subtitles.py "<Video Name>" <audio-or-video-file> [--terms "HEIF Heist, libheif, ..."]')
    name, src = args[0], pathlib.Path(args[1]).expanduser()
    terms = terms or common.load_state(name).get("terms", [])
    if terms:
        common.set_terms(name, terms)
    if not src.exists():
        common.die(f"{src} not found")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            common.die(f"{tool} is required")
    model = common.CONFIG["models"]["transcribe"]
    work = pathlib.Path(tempfile.mkdtemp(prefix="sawlemon-subs-"))
    mp3 = work / "audio.mp3"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "48k", str(mp3)])
    total = duration(mp3)
    bounds = [0.0] + cut_points(mp3, total) + [total]
    print(f"audio {total:.1f}s -> {len(bounds) - 1} chunks at {bounds[1:-1]} | work dir {work}")

    cues, usage_total, notes = [], 0, []
    for i, (a, b) in enumerate(zip(bounds, bounds[1:])):
        dur = b - a
        clip = work / f"chunk{i}.mp3"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-to", str(b), "-i", str(mp3), "-c:a", "libmp3lame", "-b:a", "48k", str(clip)])
        attempts = []
        for attempt in (1, 2, 3):
            text, usage, _ = transcribe_chunk(clip, dur, model, terms)
            (work / f"chunk{i}-try{attempt}.srt").write_text(text + "\n")
            usage_total += usage.get("totalTokenCount", 0)
            chunk, problems = parse_chunk(text, dur)
            print(f"chunk {i} ({a:.1f}-{b:.1f}s) try {attempt}: {len(chunk)} cues, {usage.get('seconds')}s, problems: {problems or 'none'}")
            attempts.append((len(problems), -len(chunk), chunk, problems))
            if not problems:
                break
        _, _, chunk, problems = min(attempts, key=lambda t: t[:2])
        if not chunk or any(p.startswith(("no cues", "out of order")) for p in problems):
            common.die(f"chunk {i} still failing after 3 tries: {problems}. Raw outputs in {work}")
        if problems:
            notes.append(f"chunk {i}: {problems} (timeline rescaled to fit; spot-check timing)")
        last = max(c[1] for c in chunk)
        scale = min(1.0, dur / last) if last else 1.0  # compress a slightly stretched timeline
        cues.extend([s * scale + a, min(e * scale, dur) + a, t] for s, e, t in chunk)

    tamil_lines = sum(bool(TAMIL.search(c[2])) for c in cues)
    if tamil_lines:
        print(f"{tamil_lines} cues contain Tamil script -> romanizing")
        usage_total += romanize(cues, model)
        left = sum(bool(TAMIL.search(c[2])) for c in cues)
        if left:
            notes.append(f"{left} cues still contain Tamil script; fix by hand")
    cues = finish(cues)
    srt = "\n".join(f"{n}\n{fmt(s)} --> {fmt(e)}\n{t}\n" for n, (s, e, t) in enumerate(cues, 1))
    dest = common.fresh_path(common.video_dir(name) / f"{name}.srt")
    dest.write_text(srt)
    shortest = min(e - s for s, e, _ in cues)
    print(f"\nSAVED {dest}\n{len(cues)} cues, ends {fmt(cues[-1][1])} (audio {fmt(total)}), shortest cue {shortest:.2f}s, "
          f"~{usage_total} Gemini tokens")
    for n in notes:
        print("NOTE:", n)
    common.save_state(name, "subtitles", {"srt": str(dest), "audio": str(src), "cues": len(cues), "model": model,
                                          "tokens": usage_total, "notes": notes})


if __name__ == "__main__":
    main()
