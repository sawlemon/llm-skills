"""Stage 3: generate a transparent cartoon-character PNG for the thumbnail (composed by the user in Canva).

Usage: python3 -I thumbnail.py "<Video Name>" "<slug>" "<pose/expression description>" [--quality medium|high] [--ref PATH]
Example: thumbnail.py "OpenAI Hacktron" angry-fist-palm "furious, out for revenge, punching his fist into his palm"
Writes <thumbnail_dir>/<slug>-transparent.png (never overwrites) and the raw output next to it.
"""
import argparse
import base64
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

PROMPT = (common.SKILL_DIR / "prompts" / "character.md").read_text()


def multipart(fields, files):
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, path in files.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{path.name}"\r\n'
                f"Content-Type: image/png\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    return out + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("slug")
    ap.add_argument("pose")
    ap.add_argument("--quality", default=common.CONFIG["image"]["quality"], choices=["low", "medium", "high"])
    ap.add_argument("--ref", default=common.CONFIG["image"]["default_reference"])
    a = ap.parse_args()
    ref = pathlib.Path(a.ref).expanduser()
    info = common.png_info(ref)
    if not info:
        common.die(f"reference {ref} must be a PNG")

    model = common.CONFIG["models"]["image"]
    body, ctype = multipart({"model": model, "prompt": PROMPT.replace("{POSE}", a.pose), "size": common.CONFIG["image"]["size"],
                             "quality": a.quality, "background": "transparent", "output_format": "png", "n": "1"},
                            {"image[]": ref})
    print(f"generating with {model} ({a.quality}) ...")
    status, d = common.http("/v1/images/edits", body, {"Content-Type": ctype}, timeout=600)
    if status != 200 or "data" not in d:
        common.die(f"HTTP {status}: {json.dumps(d)[:600] if not isinstance(d, str) else d[:600]}")

    out_dir = pathlib.Path(common.CONFIG["paths"]["thumbnail_dir"])
    raw = common.fresh_path(out_dir / "angry-avatar-originals" / f"{a.slug}-raw.png")
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(base64.b64decode(d["data"][0]["b64_json"]))

    # gpt-image returns the character at alpha 250-254; make it fully solid, keep soft edges.
    w, h, px = common.png_read_rgba(raw)
    alpha = px[3::4]
    clear = alpha.count(0)
    for i in range(3, len(px), 4):
        if px[i] >= 240:
            px[i] = 255
    dest = common.fresh_path(out_dir / f"{a.slug}-transparent.png")
    common.png_write_rgba(dest, w, h, px)

    # Report which frame edges the character touches (bottom is expected; sides/top mean cropping).
    touching = {side: sum(px[(y * w + x) * 4 + 3] > 128 for x, y in pts) for side, pts in {
        "top": [(x, 0) for x in range(w)], "bottom": [(x, h - 1) for x in range(w)],
        "left": [(0, y) for y in range(h)], "right": [(w - 1, y) for y in range(h)]}.items()}
    usage = d.get("usage", {})
    print(f"SAVED {dest}\n  {w}x{h}, transparent background {100 * clear / (w * h):.0f}% of pixels, "
          f"edge pixels touching: {touching}\n  raw: {raw}\n  tokens: {usage.get('total_tokens')}")
    if touching["top"] or touching["left"] or touching["right"]:
        print("WARNING: character is cut off at", [s for s in ("top", "left", "right") if touching[s]])
    common.save_state(a.video, f"thumbnail:{a.slug}", {"png": str(dest), "raw": str(raw), "pose": a.pose,
                                                       "quality": a.quality, "model": model, "tokens": usage.get("total_tokens")})


if __name__ == "__main__":
    main()
