#!/usr/bin/env bash
# Back up the Downloads media folder to the external SSD, then eject it.
# Runs ON the HP laptop. Invoke from the Mac with:
#   ssh hplaptop bash -s -- [options] < scripts/ssd-backup.sh
#
# Guarantees: never formats, repairs, deletes, or overwrites. Copy is additive
# only (rsync --ignore-existing, no --delete). SSD reads/writes are kept to the
# minimum the copy needs, because every access wears the drive.

set -euo pipefail

SSD_UUID="683C-A757"
SOURCE_DIR="$HOME/Downloads"
DEST_NAME="Movies Backup"
DRY_RUN=0
POWER_OFF=1
VERIFY=0

usage() {
	cat <<'USAGE'
Usage: ssd-backup.sh [options]

  --uuid UUID        Filesystem UUID of the SSD        (default: 683C-A757)
  --source DIR       Source directory                  (default: ~/Downloads)
  --dest-name NAME   Destination folder on the SSD     (default: "Movies Backup")
  --dry-run          Simulate the copy, write nothing
  --no-power-off     Unmount but leave the drive powered
  --verify           SHA-256 compare after copy (heavy reads, off by default)
  -h, --help         Show this help
USAGE
}

while [ $# -gt 0 ]; do
	case "$1" in
		--uuid) SSD_UUID="$2"; shift 2 ;;
		--source) SOURCE_DIR="$2"; shift 2 ;;
		--dest-name) DEST_NAME="$2"; shift 2 ;;
		--dry-run) DRY_RUN=1; shift ;;
		--no-power-off) POWER_OFF=0; shift ;;
		--verify) VERIFY=1; shift ;;
		-h|--help) usage; exit 0 ;;
		*) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
	esac
done

log() { printf '%s %s\n' "[$(date +%H:%M:%S)]" "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

BY_UUID="/dev/disk/by-uuid/$SSD_UUID"
MOUNTED_BY_SCRIPT=0

# Unmount on any exit path so a failure never leaves the SSD mounted and dirty.
cleanup() {
	local status=$?
	if [ "$MOUNTED_BY_SCRIPT" -eq 1 ] && findmnt -rn -S "UUID=$SSD_UUID" >/dev/null 2>&1; then
		log "Unmounting after unexpected exit"
		sync || true
		udisksctl unmount --block-device "$BY_UUID" >/dev/null 2>&1 || true
	fi
	exit "$status"
}
trap cleanup EXIT

# --- 1. Is the SSD connected? -------------------------------------------------
[ -e "$BY_UUID" ] || fail "SSD with UUID $SSD_UUID is not connected."
DEVICE="$(readlink -f "$BY_UUID")"
DISK="/dev/$(lsblk -no pkname "$DEVICE")"
log "Found SSD: $DEVICE on $DISK ($(lsblk -dno MODEL "$DISK" | sed 's/ *$//'))"

# --- 2. Mount read-write (or reuse an existing mount) -------------------------
MOUNT_POINT="$(findmnt -rn -S "UUID=$SSD_UUID" -o TARGET | head -n1 || true)"
if [ -n "$MOUNT_POINT" ]; then
	log "Already mounted at $MOUNT_POINT"
else
	log "Mounting"
	udisksctl mount --block-device "$BY_UUID" >/dev/null \
		|| fail "Mount failed. If this says 'Not authorized', install the polkit rule from SKILL.md."
	MOUNTED_BY_SCRIPT=1
	MOUNT_POINT="$(findmnt -rn -S "UUID=$SSD_UUID" -o TARGET | head -n1)"
	log "Mounted at $MOUNT_POINT"
fi
[ -n "$MOUNT_POINT" ] || fail "Could not determine the SSD mount point."

# --- 3. Refuse to write unless the target really is this SSD, mounted rw ------
MOUNT_OPTS="$(findmnt -rn -S "UUID=$SSD_UUID" -o OPTIONS | head -n1)"
case ",$MOUNT_OPTS," in
	*,rw,*) ;;
	*) fail "SSD is mounted read-only. Remount without 'ro' before copying." ;;
esac

DEST="$MOUNT_POINT/$DEST_NAME"
if [ ! -d "$DEST" ]; then
	if [ "$DRY_RUN" -eq 1 ]; then
		log "Would create destination: $DEST"
	else
		log "Creating destination: $DEST"
		mkdir -p "$DEST"
	fi
fi

# --- 4. Pick the media items to copy -----------------------------------------
# A top-level file or folder is included when it is, or contains, a video file.
mapfile -t ITEMS < <(
	SOURCE_DIR="$SOURCE_DIR" python3 - <<'PY'
import os
from pathlib import Path

source = Path(os.environ["SOURCE_DIR"])
video_exts = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv",
              ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".flv"}

for item in sorted(source.iterdir(), key=lambda p: p.name.casefold()):
    files = [item] if item.is_file() else (p for p in item.rglob("*") if p.is_file())
    if any(p.suffix.casefold() in video_exts for p in files):
        print(item)
PY
)

[ "${#ITEMS[@]}" -gt 0 ] || { log "No media found in $SOURCE_DIR. Nothing to do."; exit 0; }
log "Media items to back up: ${#ITEMS[@]}"

# --- 5. Copy: additive, never deleting or overwriting -------------------------
RSYNC_OPTS=(-rt --ignore-existing --partial --human-readable
            --info=progress2,stats2 --protect-args)
[ "$DRY_RUN" -eq 1 ] && RSYNC_OPTS+=(--dry-run)

log "Copying to $DEST"
rsync "${RSYNC_OPTS[@]}" "${ITEMS[@]}" "$DEST/"

if [ "$DRY_RUN" -eq 1 ]; then
	log "Dry run complete. Nothing was written."
	exit 0
fi

log "Flushing writes"
sync

# --- 6. Optional verification (off by default: heavy reads wear the SSD) ------
if [ "$VERIFY" -eq 1 ]; then
	log "Verifying with SHA-256"
	SOURCE_DIR="$SOURCE_DIR" DEST="$DEST" python3 - <<'PY'
import hashlib, os, sys
from pathlib import Path

source, dest = Path(os.environ["SOURCE_DIR"]), Path(os.environ["DEST"])
video_exts = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv",
              ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".flv"}

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.digest()

pairs, bad = [], []
for item in sorted(source.iterdir(), key=lambda p: p.name.casefold()):
    files = [item] if item.is_file() else [p for p in item.rglob("*") if p.is_file()]
    if not any(p.suffix.casefold() in video_exts for p in files):
        continue
    if item.is_file():
        pairs.append((item, dest / item.name))
    else:
        for src in files:
            pairs.append((src, dest / item.name / src.relative_to(item)))

for src, dst in pairs:
    if not dst.is_file():
        bad.append(f"missing: {dst}")
    elif src.stat().st_size != dst.stat().st_size:
        bad.append(f"size differs: {dst}")
    elif digest(src) != digest(dst):
        bad.append(f"checksum differs: {dst}")

print(f"VERIFIED {len(pairs) - len(bad)}/{len(pairs)} files")
for line in bad:
    print(line)
sys.exit(1 if bad else 0)
PY
fi

# --- 7. Eject ----------------------------------------------------------------
log "Unmounting"
udisksctl unmount --block-device "$BY_UUID" >/dev/null
MOUNTED_BY_SCRIPT=0
findmnt -rn -S "UUID=$SSD_UUID" >/dev/null 2>&1 && fail "SSD is still mounted."

if [ "$POWER_OFF" -eq 1 ]; then
	if udisksctl power-off --block-device "$DISK" >/dev/null 2>&1; then
		log "Powered off. Safe to unplug."
	else
		log "Unmounted safely, but power-off needs local authorization."
		log "Run on the HP laptop, then unplug: udisksctl power-off --block-device $DISK"
	fi
else
	log "Unmounted. Drive left powered as requested."
fi

log "Backup complete."
