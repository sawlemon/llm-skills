"""Stage 4: titles + description from the subtitles (user's prompt, Gemini), then automatic checks and a fact-check.

Usage: python3 -I metadata.py "<Video Name>" [--srt PATH]
Writes <video dir>/metadata-draft.md (raw model output, never overwritten) and metadata-check.json.
The agent then applies the fixes and writes metadata-FINAL.md (see SKILL.md).
"""
import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

TAMIL = re.compile("[\u0b80-\u0bff]")
WRONG_TERMS = {"transient dependenc": "transitive dependency"}


def srt_end_seconds(srt):
    ends = re.findall(r"--> (\d+):(\d+):(\d+),(\d+)", srt)
    h, m, s, ms = ends[-1]
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def mechanical_checks(draft, srt):
    issues = []
    titles = re.findall(r"\*\*([ABC]) \([^)]*\):\*\*\s*(.+)", draft)
    if len(titles) != 3:
        issues.append(f"expected 3 titles, found {len(titles)}")
    for label, t in titles:
        if len(t) >= 70:
            issues.append(f"title {label} is {len(t)} chars (limit 70)")
        if not TAMIL.search(t):
            issues.append(f"title {label} has no Tamil-script word")
    desc = draft.split("## 📝 Description", 1)[-1]
    words = len(desc.split())
    if words > 500:
        issues.append(f"description is {words} words (limit 500)")
    tags = desc.split("Tags (for SEO):", 1)[-1].strip().split(",") if "Tags (for SEO):" in desc else []
    if not 10 <= len(tags) <= 15:
        issues.append(f"{len(tags)} tags (want 10-15)")
    end = srt_end_seconds(srt)
    stamps = [int(m) * 60 + int(s) for m, s in re.findall(r"^\s*(\d{1,2}):(\d{2})\s*[-–—]", desc, re.M)]
    if stamps and (stamps[0] != 0 or stamps != sorted(stamps) or stamps[-1] > end):
        issues.append(f"timestamps must start at 00:00, increase, and stay under {end:.0f}s: {stamps}")
    for wrong, right in WRONG_TERMS.items():
        if wrong in draft.lower():
            issues.append(f"uses '{wrong}...' -> should be '{right}'")
    return {"titles": [{"label": l, "title": t, "chars": len(t)} for l, t in titles], "description_words": words,
            "tags": len(tags), "timestamps_s": stamps, "issues": issues}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--srt")
    a = ap.parse_args()
    state = common.load_state(a.video)
    srt_path = pathlib.Path(a.srt or state["stages"].get("subtitles", {}).get("srt", ""))
    if not srt_path.is_file():
        common.die("no subtitles: run subtitles.py first or pass --srt")
    srt = srt_path.read_text()
    model = common.CONFIG["models"]["metadata"]
    vdir = common.video_dir(a.video)

    prompt = (common.SKILL_DIR / "prompts" / "title-description.md").read_text() + srt
    if state.get("terms"):
        prompt += "\n\nCorrect spellings of names and terms in this video (the subtitles may mis-hear them): " + ", ".join(state["terms"])
    draft, usage, _ = common.gemini(model, [{"text": prompt}], {"temperature": 0.7})
    draft_path = common.fresh_path(vdir / "metadata-draft.md")
    draft_path.write_text(draft + "\n")
    print(f"draft: {draft_path} ({usage.get('totalTokenCount')} tokens, {usage.get('seconds')}s)")

    checks = mechanical_checks(draft, srt)
    terms = state.get("terms", [])
    fc_prompt = (common.SKILL_DIR / "prompts" / "fact-check.md").read_text().replace("{DRAFT}", draft).replace("{SRT}", srt)
    if terms:
        fc_prompt += ("\n=== CORRECT SPELLINGS ===\nThe subtitles may mis-hear these; treat these spellings as correct and flag "
                      "any variant in the draft (e.g. a mis-heard product or vulnerability name): " + ", ".join(terms) + "\n")
    fc_text, fc_usage, _ = common.gemini(model, [{"text": fc_prompt}], {"temperature": 0.1, "responseMimeType": "application/json"})
    try:
        checks["fact_check"] = json.loads(re.sub(r"^```\w*\s*|\s*```$", "", fc_text.strip()))
    except ValueError:
        checks["fact_check"] = {"error": "unparseable fact-check reply", "raw": fc_text[:2000]}
    check_path = common.fresh_path(vdir / "metadata-check.json")
    check_path.write_text(json.dumps(checks, indent=2, ensure_ascii=False) + "\n")

    print(json.dumps(checks, indent=2, ensure_ascii=False))
    common.save_state(a.video, "metadata", {"draft": str(draft_path), "check": str(check_path), "srt": str(srt_path),
                                            "model": model, "tokens": usage.get("totalTokenCount", 0) + fc_usage.get("totalTokenCount", 0)})


if __name__ == "__main__":
    main()
