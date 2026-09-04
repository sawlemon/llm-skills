---
name: ssd-backup
description: Back up the HP laptop's Downloads media to the external SSD and eject it. Use when the user says they connected the external SSD, or asks to back up, copy, or archive downloads or movies to it.
---

# SSD backup

One command backs up `~/Downloads` media on `hplaptop` to `Movies Backup` on the
external SSD, then ejects the drive.

```bash
ssh hplaptop bash -s < ~/.zcode/skills/ssd-backup/scripts/ssd-backup.sh
```

The script runs on the laptop but is never installed there: `bash -s` streams it
over SSH, so editing the local copy is enough. To install this skill elsewhere,
copy the directory to the agent's skills path and adjust the `ssh` host.

Report the result to the user when it finishes: items copied, data written, and
whether the drive is safe to unplug.

## The drive

WD_BLACK SN770 1TB over USB, exFAT, label `ext-ssd`, filesystem UUID
`683C-A757`. Always address it by UUID. Linux device names shift between
plug-ins, so `/dev/sdb` is not a stable identifier.

## Rules

This SSD holds the user's only backups, and every read and write wears it.

- Never format, partition, `fsck`, repair, delete, or overwrite. The copy is
  additive: `rsync --ignore-existing`, never `--delete`.
- Never remove source files. This is a copy, not a move.
- No exploratory access. Skip listings, `du`, checksums, and health scans unless
  the user asks. The script already keeps access to what the copy needs.
- Verification is opt-in via `--verify`, because it re-reads every byte on both
  sides. The user declined it by default.
- Anything destructive needs explicit approval first, every time.

## Options

| Flag | Effect |
| --- | --- |
| `--dry-run` | Simulate the copy, write nothing |
| `--verify` | SHA-256 compare after copying (heavy reads) |
| `--no-power-off` | Unmount but leave the drive powered |
| `--source DIR` | Copy from somewhere other than `~/Downloads` |
| `--dest-name NAME` | Destination folder other than `Movies Backup` |
| `--uuid UUID` | Target a different drive |

Use `--dry-run` first when the user seems unsure about what would be copied.

## What the script does

1. Confirms the SSD is connected, by UUID.
2. Mounts it, or reuses an existing mount.
3. Refuses to write unless the target is that UUID, mounted read-write.
4. Selects top-level items in `~/Downloads` that are or contain video files.
   Ebooks and other non-media folders are skipped.
5. Copies with `rsync -rt --ignore-existing --partial`, then `sync`.
6. Unmounts, powers off the USB device, and reports.

An unexpected exit unmounts the drive rather than leaving it mounted and dirty.

## One-time setup: unattended mounting

`udisksctl` asks polkit for authorization. An SSH session is not a local login
session, so the request fails with `Not authorized to perform operation` and the
user has to run the mount by hand at the laptop.

To let this run unattended, create the rule on the HP laptop once:

```bash
sudo tee /etc/polkit-1/rules.d/50-alfred-udisks.rules >/dev/null <<'EOF'
// Let alfred mount and eject removable drives from an SSH session.
polkit.addRule(function(action, subject) {
    if (subject.user !== "alfred") return;
    var allowed = [
        "org.freedesktop.udisks2.filesystem-mount",
        "org.freedesktop.udisks2.filesystem-unmount-others",
        "org.freedesktop.udisks2.power-off-drive"
    ];
    if (allowed.indexOf(action.id) !== -1) return polkit.Result.YES;
});
EOF
sudo systemctl restart polkit
```

This grants mount and eject rights only, to one user. It does not grant
formatting or any other disk modification.

Until that rule exists, the script still works, but the user runs two commands
locally:

```bash
udisksctl mount --block-device /dev/disk/by-uuid/683C-A757
udisksctl power-off --block-device /dev/sdb
```

## Failure modes

The laptop shows as offline in Tailscale and SSH times out. The node lost its
connection to the coordination server; that is a network problem, not a disk
problem. Check internet access, DNS, and `tailscaled` before touching storage.

Mount fails with `Not authorized`. Install the polkit rule above, or have the
user mount at the laptop.

Power-off fails after a clean unmount. The data is already safe. Give the user
the `udisksctl power-off` line and tell them to wait for it before unplugging.
