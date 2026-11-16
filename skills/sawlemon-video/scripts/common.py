"""Shared helpers for the sawlemon-video scripts. Standard library only."""
import json
import pathlib
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
CONFIG = json.loads((SKILL_DIR / "config.json").read_text())


def die(msg):
    sys.exit(f"ERROR: {msg}")


# ---------------------------------------------------------------- proxy

def proxy_key():
    """Client key from cliproxyapi's access.api-keys. Never print or log it."""
    lines = pathlib.Path(CONFIG["proxy"]["config_file"]).read_text().splitlines()
    for n, line in enumerate(lines):
        if line.strip() == "api-keys:" and n and lines[n - 1].strip() == "access:":
            for cand in lines[n + 1:n + 6]:
                m = re.match(r'\s*-\s*["\']?([^"\'\s#]+)', cand)
                if m:
                    return m.group(1)
    die("no access.api-keys entry in " + CONFIG["proxy"]["config_file"])


def http(path, data, headers, timeout=600):
    """POST to the proxy. Returns (status, parsed JSON or raw text)."""
    req = urllib.request.Request(CONFIG["proxy"]["base_url"] + path, data=data, method="POST",
                                 headers={"Authorization": f"Bearer {proxy_key()}", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            body = json.loads(body)
        except ValueError:
            pass
        return e.code, body
    except urllib.error.URLError as e:
        die(f"cliproxyapi not reachable at {CONFIG['proxy']['base_url']} ({e.reason}). Is it running?")


def gemini(model, parts, generation_config=None, timeout=600):
    """Gemini native generateContent. Returns (text, usageMetadata, finishReasons)."""
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": generation_config or {}}
    t0 = time.time()
    status, d = http(f"/v1beta/models/{model}:generateContent", json.dumps(body).encode(),
                     {"Content-Type": "application/json"}, timeout)
    if status != 200:
        die(f"{model} HTTP {status}: {json.dumps(d)[:500] if not isinstance(d, str) else d[:500]}")
    text = "".join(p.get("text", "") for c in d.get("candidates", [])
                   for p in c.get("content", {}).get("parts", []) if not p.get("thought"))
    usage = d.get("usageMetadata", {})
    usage["seconds"] = round(time.time() - t0)
    return text.strip(), usage, [c.get("finishReason") for c in d.get("candidates", [])]


# ---------------------------------------------------------------- video folder + state

def video_dir(name):
    d = pathlib.Path(CONFIG["paths"]["library"]) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(name):
    f = video_dir(name) / "video.json"
    return json.loads(f.read_text()) if f.exists() else {"video": name, "stages": {}}


def save_state(name, stage, info):
    state = load_state(name)
    state["stages"][stage] = {**info, "updated": time.strftime("%Y-%m-%d %H:%M")}
    (video_dir(name) / "video.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def set_terms(name, terms):
    """Key names/terms for the video (exact spellings), shared by subtitles and metadata."""
    state = load_state(name)
    state["terms"] = terms
    (video_dir(name) / "video.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def fresh_path(path):
    """Never overwrite: return path, or path with -2, -3 ... appended to the stem."""
    path = pathlib.Path(path)
    n = 2
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


# ---------------------------------------------------------------- minimal PNG (8-bit RGBA / RGB, non-interlaced)

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_info(path):
    """(width, height, bit_depth, color_type) from IHDR, or None if not a PNG."""
    b = pathlib.Path(path).read_bytes()[:33]
    if b[:8] != PNG_SIG or b[12:16] != b"IHDR":
        return None
    w, h, depth, ctype = struct.unpack(">IIBB", b[16:26])
    return w, h, depth, ctype


def png_read_rgba(path):
    """Decode an 8-bit RGBA or RGB PNG into (w, h, bytearray RGBA)."""
    data = pathlib.Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        die(f"{path} is not a PNG")
    pos, idat, ihdr = 8, b"", None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + length
    w, h, depth, ctype, _, _, interlace = ihdr
    if depth != 8 or ctype not in (2, 6) or interlace:
        die(f"{path}: only 8-bit non-interlaced RGB/RGBA PNGs are supported (got depth {depth}, type {ctype})")
    bpp = 4 if ctype == 6 else 3
    raw = zlib.decompress(idat)
    stride = w * bpp
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        if bpp == 4:
            out[y * w * 4:(y + 1) * w * 4] = line
        else:
            o = y * w * 4
            for x in range(w):
                out[o + x * 4:o + x * 4 + 3] = line[x * 3:x * 3 + 3]
                out[o + x * 4 + 3] = 255
        prev = line
    return w, h, out


def png_write_rgba(path, w, h, rgba):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    pathlib.Path(path).write_bytes(PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                                   + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
