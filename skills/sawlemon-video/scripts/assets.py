"""Stage 1 helpers: find existing logos in the library, and verify collected PNGs.

Usage:
  python3 -I assets.py have <name> [<name> ...]   # which requested logos/assets already exist in the library root
  python3 -I assets.py check "<Video Name>"       # verify every PNG in the video folder (+ any new logos in the root)
  python3 -I assets.py check-file <png> [...]     # verify specific files (logos must have real transparency)
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

LIB = pathlib.Path(common.CONFIG["paths"]["library"])
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def have(names):
    files = [p for p in LIB.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXT]
    for name in names:
        key = norm(name)
        hits = [p.name for p in files if key and key in norm(p.stem)]
        print(f"{name}: {'HAVE -> ' + ', '.join(hits) if hits else 'missing'}")


def check_png(path, need_alpha=False):
    """Return a list of problems ([] = good). Logos need genuinely transparent pixels, not just an alpha channel."""
    info = common.png_info(path)
    if not info:
        return ["not a PNG (wrong signature)"]
    w, h, depth, ctype = info
    problems = []
    if w < 400 and h < 400:
        problems.append(f"small ({w}x{h}); will look soft in a 1080p/4K edit")
    if need_alpha:
        if ctype not in (4, 6):
            problems.append("no alpha channel (logo needs a transparent background)")
        elif depth == 8 and ctype == 6:
            _, _, px = common.png_read_rgba(path)
            clear = px[3::4].count(0)
            if clear == 0:
                problems.append("has an alpha channel but no transparent pixels")
    return problems


def report(paths, logo_check):
    bad = 0
    for p in paths:
        need_alpha = logo_check(p)
        problems = check_png(p, need_alpha)
        info = common.png_info(p)
        size = f"{info[0]}x{info[1]}" if info else "?"
        print(f"{'OK  ' if not problems else 'FAIL'} {p.name} [{size}{', logo' if need_alpha else ''}] {'; '.join(problems)}")
        bad += bool(problems)
    print(f"\n{len(paths) - bad}/{len(paths)} passed")
    return bad


def main():
    if len(sys.argv) < 3:
        common.die(__doc__)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "have":
        have(args)
    elif cmd == "check":
        vdir = common.video_dir(args[0])
        pngs = sorted(vdir.rglob("*.png"))
        bad = report(pngs, lambda p: "logo" in p.name.lower() or "transparent" in p.name.lower())
        common.save_state(args[0], "assets", {"folder": str(vdir), "pngs": len(pngs), "failed": bad})
    elif cmd == "check-file":
        report([pathlib.Path(a) for a in args], lambda p: "logo" in p.name.lower() or "transparent" in p.name.lower())
    else:
        common.die(__doc__)


if __name__ == "__main__":
    main()
