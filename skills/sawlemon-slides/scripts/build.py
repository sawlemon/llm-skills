"""Build a self-contained Sawlemon "Paper Punch" HTML slide deck.

Usage:
  python3 -I build.py init  <deck-dir> --title "PHP2Shell" --topic "PHP2Shell · explained simply"
  python3 -I build.py build <deck-dir>

init   creates <deck-dir>/slides.html from the starter template (never overwrites) and deck.json.
build  wraps <deck-dir>/slides.html with the skill's CSS + JS into <deck-dir>/deck.html.
"""
import argparse
import html
import json
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ASSETS = SKILL / "assets"
FONTS = ("https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900"
         "&family=Permanent+Marker&family=JetBrains+Mono:wght@500;700&display=swap")

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} · sawlemon</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{fonts}">
<style>
{base}
{theme}
</style>
</head>
<body>
<main class="stage">
{slides}
<footer class="brandbar"><span class="logo">SAWLEMON</span><span class="topic">{topic}</span><span class="counter"></span></footer>
</main>
<script>
{js}
</script>
</body>
</html>
"""


def init(deck: Path, title: str, topic: str):
    deck.mkdir(parents=True, exist_ok=True)
    slides = deck / "slides.html"
    if slides.exists():
        print(f"kept existing {slides}")
    else:
        shutil.copy(ASSETS / "starter-slides.html", slides)
        print(f"wrote {slides}")
    meta = deck / "deck.json"
    meta.write_text(json.dumps({"title": title, "topic": topic or f"{title} · explained simply"}, indent=2) + "\n")
    print(f"wrote {meta}")


def build(deck: Path):
    slides_path, meta_path = deck / "slides.html", deck / "deck.json"
    if not slides_path.exists():
        sys.exit(f"missing {slides_path}; run init first")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {"title": deck.name, "topic": deck.name}
    slides = slides_path.read_text()
    out = deck / "deck.html"
    out.write_text(TEMPLATE.format(
        title=html.escape(meta["title"]), topic=html.escape(meta["topic"]), fonts=FONTS,
        base=(ASSETS / "base.css").read_text(), theme=(ASSETS / "theme.css").read_text(),
        slides=slides, js=(ASSETS / "deck.js").read_text()))
    steps = slides.count("data-steps=")
    print(f"wrote {out} ({slides.count('<section')} slides, {steps} step-by-step)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["init", "build"])
    ap.add_argument("deck", type=Path)
    ap.add_argument("--title", default="")
    ap.add_argument("--topic", default="")
    a = ap.parse_args()
    if a.cmd == "init":
        init(a.deck, a.title or a.deck.name, a.topic)
    else:
        build(a.deck)


if __name__ == "__main__":
    main()
