"""X post length counter (X's weighted rules) and the pinned YouTube comment.

Usage:
  python3 -I social.py count "<post text>"        # weighted length / 280
  python3 -I social.py count-file post.md          # each block separated by a line '---' is counted
  python3 -I social.py pinned [tanglish|english]   # pinned comment with the configured X / LinkedIn links
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

# twitter-text v3: these code point ranges weigh 1, everything else (emoji, Tamil script, arrows) weighs 2; URLs weigh 23.
LIGHT = [(0, 4351), (8192, 8205), (8208, 8223), (8242, 8247)]


def x_length(text):
    n = 0
    for part in re.split(r"(https?://\S+)", text):
        if part.startswith("http"):
            n += 23
        else:
            n += sum(1 if any(a <= ord(ch) <= b for a, b in LIGHT) else 2 for ch in part)
    return n


PINNED = {
    "tanglish": ("Indha maadhiri cybersecurity news & breakdowns daily update venum na, enna follow pannunga 👇\n\n"
                 "🐦 X: {x}\n💼 LinkedIn: {linkedin}\n\n"
                 "Adutha video-la enna topic cover pannanum nu comment-la sollunga! 🔐"),
    "english": ("Want quick cybersecurity updates between videos? Follow me here 👇\n\n"
                "🐦 X: {x}\n💼 LinkedIn: {linkedin}\n\n"
                "Drop a comment with the topic you want me to cover next! 🔐"),
}


def main():
    if len(sys.argv) < 2:
        common.die(__doc__)
    cmd = sys.argv[1]
    if cmd == "count":
        n = x_length(sys.argv[2])
        print(f"{n}/280 {'OK' if n <= 280 else 'TOO LONG'}")
    elif cmd == "count-file":
        for i, block in enumerate(pathlib.Path(sys.argv[2]).read_text().split("\n---\n"), 1):
            n = x_length(block.strip())
            print(f"block {i}: {n}/280 {'OK' if n <= 280 else 'TOO LONG'}")
    elif cmd == "pinned":
        style = sys.argv[2] if len(sys.argv) > 2 else "tanglish"
        print(PINNED[style].format(**common.CONFIG["social"]))
    else:
        common.die(__doc__)


if __name__ == "__main__":
    main()
