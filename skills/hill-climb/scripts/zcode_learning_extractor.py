#!/usr/bin/env python3
"""Prepare, validate, and commit ZCode learning-extraction runs safely.

Unlike the Codex runner (which reads date-foldered JSONL rollouts), ZCode
stores every session's transcript in a local SQLite database
(``~/.zcode/cli/db/db.sqlite``, tables ``session``/``message``/``part``) plus
an auxiliary automation index (``~/.zcode/v2/tasks-index.sqlite``, table
``automation_runs``). Both are opened **read-only** (URI ``?mode=ro`` plus
``PRAGMA query_only``) and are never written to by this script.

This runner is a *recoverable* commit protocol, not an atomic one: a crash
between writing staged files and flipping the run's commit marker to
``completed`` can leave a run's live state briefly ambiguous. ``recover`` is
state-aware -- it requires a present, well-formed, run-matching commit marker
with a recognized status before acting at all (no filename-based backup
fallback), restores the pre-run backup only for a run whose marker is
genuinely unresolved, is idempotent (never restores a ``completed`` or
already-``recovered`` run a second time, which would silently clobber a
later run's work), and refuses outright while a *different* run owns the
extraction lock. Backup restoration itself fails closed: a missing backup,
a malformed manifest, a missing backed-up file, a hash mismatch, or an
inventory that doesn't match the trusted apply state recorded before the
backup was ever used aborts recovery and leaves the in-progress marker, the
normalized evidence, and the lock untouched rather than guessing. Evidence is
never silently skipped, and the checkpoint (``self-improve/watermark.json``)
only ever advances after every staged file has been applied.

Every security-sensitive field of a run (bounds, provenance, sessions,
baseline hashes, watermark baseline, evidence digest, authorized target
inventory) is bound at ``prepare`` time into a runner-controlled *trusted
control record* living outside the agent-editable run directory, under
``self-improve/extraction-control/<run_id>/`` (mode 0700 directory, 0600
files) -- never trust the editable ``manifest.json`` alone. ``apply`` binds
the verified pre-apply backup the same way, before touching any live file.
``validate``/``apply``/``recover`` all fail closed if this trusted state is
missing (a legacy run) or doesn't match the editable manifest/backup. Every
live target, staged source, the watermark, and every backup source/restore
destination is preflighted for a symlinked ancestor before a single one of
them is written, and every ``--run-id`` is resolved to a directory through
one central, containment- and symlink-checked resolver
(``resolve_run_dir``). The operator-only ``repair-recover`` command breaks
the deadlock where a malformed lock blocks ``recover`` and an incomplete
commit blocks ``unlock-abandoned``; it requires manual
``--confirm-no-process`` confirmation and still refuses an identifiably
alive lock owner. ``check-deployment`` is a read-only command that verifies
the deployed scheduler automation, its wrapper prompt, the deployed
extraction prompt, and the deployed runner copy against expectations.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Any

DISPOSITIONS = {"WROTE_MAP", "WROTE_DOC", "REFINED", "SUPERSEDED", "SKIPPED_DUP", "PROVISIONAL", "REJECTED"}
WRITE_DISPOSITIONS = {"WROTE_MAP", "WROTE_DOC", "REFINED", "SUPERSEDED"}
SESSION_DISPOSITION_STATUSES = {"contributed", "reviewed_no_learning"}
SECRET_RE = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|token|secret|password|credential)\s*[:=]\s*[\"']?[^\"'\s]{8,}")
POINTER_RE = re.compile(r"(?:^|\s)((?:\./)?docs/[A-Za-z0-9_./-]+)(?:\s|$|\))")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
SCHEDULED_TASK_MARK = "<scheduled-task"
NOISE_EXACT = ("[Request interrupted by user for tool use]",)
DEFAULT_BOOTSTRAP_HOURS = 48

LEDGER_KEY = "AGENTS.extraction-log.md"
WATERMARK_REL = "self-improve/watermark.json"
BACKUP_PREFIX = "extraction-backup-"
BACKUP_NAME_RE = re.compile(r"^extraction-backup-\d{8}T\d{6}-(?P<run_id>[A-Za-z0-9][A-Za-z0-9_.-]{0,63})$")
WATERMARK_FUTURE_SKEW_MS = 5 * 60 * 1000  # allowed clock skew before a checkpoint is "future"
LOCK_META_NAME = "owner.json"
CONTROL_DIR_REL = "self-improve/extraction-control"
VALID_MARKER_STATUSES = {"in_progress", "completed", "recovered"}
# Fields that must be byte-for-byte identical between the agent-editable
# manifest.json and the runner-controlled trusted control record. Anything
# else in the manifest (e.g. derived report text) is not security-relevant.
CONTROL_SENSITIVE_FIELDS = (
    "run_id", "lower_bound", "upper_bound", "bootstrap", "automation_id", "model_id",
    "prompt_sha256", "session_count", "sessions", "baseline_hashes",
    "watermark_baseline", "normalized_evidence_sha256",
)
# The real, deployed absolute paths this runner and its extraction prompt are
# expected to live at in production (``~/.zcode`` == ``/Users/sala/.zcode``
# for the account this automation runs under). `check-deployment` checks the
# scheduler's stored wrapper-prompt *text* against these fixed strings --
# independent of whatever --zcode-home a given invocation (e.g. a test) uses
# for locally reading the deployed prompt/runner files to hash them.
DEPLOYED_RUNNER_ABS_PATH = "/Users/sala/.zcode/self-improve/zcode_learning_extractor.py"
DEPLOYED_PROMPT_ABS_PATH = "/Users/sala/.zcode/self-improve/learning-extraction-v1.md"
# `supporting_destinations` may only cover structural index/map files that
# necessarily accompany a write (never arbitrary content docs): the global
# map, the docs catalog, and per-project index files.
SUPPORTING_DESTINATION_RE = re.compile(
    r"^(?:AGENTS\.md|docs/index\.md|docs/projects/index\.md|docs/projects/[^/]+/index\.md)$"
)

REQUIRED_AUTOMATION_COLUMNS = {"session_id"}
REQUIRED_SESSION_COLUMNS = {"id", "parent_id", "directory", "title", "time_created", "time_updated", "task_type"}
REQUIRED_MESSAGE_COLUMNS = {"id", "session_id", "sequence", "time_created", "data"}
REQUIRED_PART_COLUMNS = {"id", "message_id", "sequence", "data"}


class RunError(RuntimeError):
    pass


class Workspace:
    def __init__(self, home: Path, runs: Path, ledger: Path):
        self.home, self.runs, self.ledger = home, runs, ledger

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Workspace":
        home = Path(args.zcode_home).expanduser().resolve()
        runs = Path(args.runs_home).expanduser().resolve() if args.runs_home else home / "self-improve" / "extraction-runs"
        ledger = Path(args.ledger).expanduser().resolve() if args.ledger else home / "AGENTS.extraction-log.md"
        return cls(home, runs, ledger)

    @property
    def state(self) -> Path:
        return self.home / "self-improve" / "watermark.json"

    @property
    def lock(self) -> Path:
        return self.home / "self-improve" / "extraction.lock"

    @property
    def memory(self) -> Path:
        return self.home / "docs"


# --------------------------------------------------------------------------
# Small generic helpers (deliberately duplicated from codex_learning_extractor.py
# rather than imported -- the two runners have no shared module today and this
# keeps each one independently readable and safe to change without risking the
# other's tests).
# --------------------------------------------------------------------------

def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def safe_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value):
        raise RunError("invalid run_id")
    return value


def safe_relative_path(rel: Any) -> bool:
    """A path is safe to treat as a staged/backed-up relative path only if it
    is a non-empty string, not absolute, and has no ``..`` component -- used
    for decision destinations, backup inventory keys, and staged additions.
    """
    if not isinstance(rel, str) or not rel:
        return False
    p = Path(rel)
    if p.is_absolute():
        return False
    if ".." in p.parts:
        return False
    return True


def under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def redact(text: str) -> str:
    return SECRET_RE.sub(lambda m: m.group(0).split("=", 1)[0].split(":", 1)[0] + "=<REDACTED>", text)


def now_ms() -> int:
    return int(time.time() * 1000)


def iso_ms(epoch_ms: int) -> str:
    return dt.datetime.fromtimestamp(epoch_ms / 1000, dt.timezone.utc).isoformat()


def default_run_id() -> str:
    return dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(4).hex()


# --------------------------------------------------------------------------
# Watermark checkpoint: fails closed on anything but a genuinely absent file.
# --------------------------------------------------------------------------

def load_watermark(ws: Workspace) -> int | None:
    """Return the lower-bound epoch-ms watermark, or ``None`` only if the
    checkpoint file genuinely does not exist yet (bootstrap case).

    Raises ``RunError`` if the file exists but is unreadable, not valid JSON,
    has the wrong schema, or holds a non-numeric/boolean/negative/future
    value -- an existing, broken checkpoint must never be silently treated
    as "no checkpoint" (which would quietly re-bootstrap the window and
    could either re-process or, worse, skip history depending on the
    corruption).
    """
    if not ws.state.exists():
        return None
    try:
        raw = ws.state.read_text()
    except OSError as exc:
        raise RunError(f"watermark file is unreadable: {exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunError(f"watermark file is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RunError("watermark file has the wrong schema (expected a JSON object)")
    if "last_time_updated" not in value:
        raise RunError("watermark file is missing last_time_updated")
    raw_value = value["last_time_updated"]
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise RunError(f"watermark last_time_updated is not numeric: {raw_value!r}")
    ms = int(raw_value)
    if ms < 0:
        raise RunError(f"watermark last_time_updated is negative: {ms}")
    if ms > now_ms() + WATERMARK_FUTURE_SKEW_MS:
        raise RunError(f"watermark last_time_updated is in the future: {ms}")
    return ms


# --------------------------------------------------------------------------
# Extraction lock: an atomically-created directory (never a bare
# create-then-write file) with owner metadata published immediately after.
# --------------------------------------------------------------------------

def lock_meta_path(ws: Workspace) -> Path:
    return ws.lock / LOCK_META_NAME


def inspect_lock(ws: Workspace) -> tuple[str, dict[str, Any] | None]:
    """Classify the current extraction lock without raising.

    Returns ``("absent", None)`` if there is no lock, ``("valid", meta)`` if
    it is a lock directory with readable owner metadata, or
    ``("malformed", None)`` for anything else -- a bare file left by a
    pre-hardening runner, a lock directory whose metadata write never
    completed, or corrupted metadata. Callers that need to *act* on the lock
    (acquire/require/recover) must treat "malformed" as a hard failure,
    never silently as "unlocked".
    """
    if not ws.lock.exists():
        return "absent", None
    if not ws.lock.is_dir():
        return "malformed", None
    meta = read_json(lock_meta_path(ws))
    if meta is None or not isinstance(meta.get("run_id"), str):
        return "malformed", None
    return "valid", meta


def lock_owner(ws: Workspace) -> dict[str, Any] | None:
    """Best-effort, non-raising read of lock ownership for diagnostics
    (``status``). Returns ``None`` both when unlocked and when the lock is
    malformed -- callers that need to act on ownership must use
    ``inspect_lock``/``require_lock``/``acquire_lock``, which fail closed.
    """
    state, meta = inspect_lock(ws)
    return meta if state == "valid" else None


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just not ours to signal
    except OSError:
        return False
    return True


def _fsync_dir(path: Path) -> None:
    """Best-effort directory-entry fsync (not supported everywhere -- e.g.
    Windows -- so failures here are swallowed; this is defense in depth on
    top of the rename, not the only durability mechanism).
    """
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _lock_owner_error(ws: Workspace) -> RunError:
    state, meta = inspect_lock(ws)
    if state == "malformed":
        return RunError(
            f"extraction lock at {ws.lock} is malformed or abandoned (missing/invalid owner "
            "metadata, or a legacy plain-file lock from an older runner version); run "
            "`unlock-abandoned` after confirming no extraction process is alive, then retry (if an "
            "incomplete commit blocks `unlock-abandoned` too, use the operator-only "
            "`repair-recover --confirm-no-process` instead)"
        )
    return RunError(f"another extraction run owns the lock ({(meta or {}).get('run_id', 'unknown')})")


def acquire_lock(ws: Workspace, run_id: str) -> None:
    ws.lock.parent.mkdir(parents=True, exist_ok=True)
    if ws.lock.exists():
        raise _lock_owner_error(ws)
    # Publish atomically: build the *entire* lock directory -- including its
    # fsynced owner metadata -- under a private temp name first, then
    # os.rename() it into place in one step. A bare os.mkdir() followed by a
    # separate metadata write left a window where the lock directory existed
    # on disk with no metadata at all if the process died in between; here,
    # nothing ever appears at `ws.lock` until the metadata is already
    # durable, and a concurrent racer's rename can only ever fail (never
    # silently replace what's already there), since POSIX rename() refuses
    # to replace a non-empty directory.
    tmp_dir = Path(tempfile.mkdtemp(prefix=f".{ws.lock.name}.tmp-", dir=str(ws.lock.parent)))
    try:
        atomic_json(tmp_dir / LOCK_META_NAME, {"run_id": run_id, "pid": os.getpid(), "created_at": time.time()})
        _fsync_dir(tmp_dir)
        os.rename(str(tmp_dir), str(ws.lock))
    except OSError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if ws.lock.exists():
            raise _lock_owner_error(ws) from exc
        raise
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def require_lock(ws: Workspace, run_id: str) -> None:
    state, meta = inspect_lock(ws)
    if state != "valid" or meta.get("run_id") != run_id:
        raise RunError("run does not own extraction lock")


def release_lock(ws: Workspace, run_id: str) -> None:
    state, meta = inspect_lock(ws)
    if state == "valid" and meta.get("run_id") == run_id:
        shutil.rmtree(ws.lock, ignore_errors=True)


def cmd_unlock_abandoned(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    state, meta = inspect_lock(ws)
    if state == "absent":
        print(json.dumps({"unlocked": False, "reason": "no lock present"}))
        return 0
    if state == "valid":
        if args.run_id and meta.get("run_id") != args.run_id:
            raise RunError(f"lock is owned by run {meta.get('run_id')!r}, not {args.run_id!r}; refusing to remove")
        pid = meta.get("pid")
        if isinstance(pid, int) and _pid_alive(pid):
            raise RunError(
                f"refusing to remove lock: owning process (pid {pid}, run {meta.get('run_id')!r}) "
                "appears to be alive"
            )
        owner_run_id = meta.get("run_id")
        if owner_run_id:
            marker = read_json(commit_marker_path(ws.runs / owner_run_id))
            if marker and marker.get("status") not in ("completed", "recovered"):
                raise RunError(
                    f"refusing to remove lock: run {owner_run_id!r} has an unresolved commit -- run "
                    f"`recover --run-id {owner_run_id}` instead"
                )
    else:
        # Malformed lock: no metadata to identify an owning pid or run. The
        # only thing we *can* verify is that no run in this workspace still
        # claims to be mid-commit.
        if find_incomplete_commits(ws):
            raise RunError(
                "refusing to remove an unidentifiable lock while an incomplete commit exists; "
                "resolve it with `recover` first"
            )
    if ws.lock.is_dir():
        shutil.rmtree(ws.lock, ignore_errors=True)
    elif ws.lock.exists():
        ws.lock.unlink(missing_ok=True)
    print(json.dumps({"unlocked": True}))
    return 0


# --------------------------------------------------------------------------
# Read-only SQLite access
# --------------------------------------------------------------------------

def ro_uri(path: Path) -> str:
    return "file:" + urllib.parse.quote(str(path), safe="/") + "?mode=ro"


def open_ro(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(ro_uri(path), uri=True)
    con.execute("PRAGMA query_only = ON")
    return con


def require_table_schema(con: sqlite3.Connection, table: str, required_columns: set[str], db_label: str) -> None:
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as exc:
        raise RunError(f"{db_label} could not be inspected: {exc}") from exc
    if table not in tables:
        raise RunError(f"{db_label} is missing required table {table!r}")
    try:
        cols = {row[1] for row in con.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error as exc:
        raise RunError(f"{db_label} table {table!r} could not be inspected: {exc}") from exc
    missing = required_columns - cols
    if missing:
        raise RunError(f"{db_label} table {table!r} is missing required column(s): {', '.join(sorted(missing))}")


def validate_session_db_schema(con: sqlite3.Connection) -> None:
    require_table_schema(con, "session", REQUIRED_SESSION_COLUMNS, "session database")
    require_table_schema(con, "message", REQUIRED_MESSAGE_COLUMNS, "session database")
    require_table_schema(con, "part", REQUIRED_PART_COLUMNS, "session database")


def load_automation_ids(tasks_db_path: Path) -> set[str]:
    """Load the set of session ids to exclude as automation runs.

    The tasks-index database is required: a missing file, an unreadable
    database, a missing ``automation_runs`` table, or a failed query all
    raise ``RunError`` instead of silently substituting an empty set, which
    would let automation output leak into extraction undetected.
    """
    if not tasks_db_path.exists():
        raise RunError(f"automation-exclusion database not found: {tasks_db_path}")
    try:
        con = open_ro(tasks_db_path)
    except sqlite3.Error as exc:
        raise RunError(f"automation-exclusion database is unreadable: {exc}") from exc
    try:
        require_table_schema(con, "automation_runs", REQUIRED_AUTOMATION_COLUMNS, "automation-exclusion database")
        try:
            rows = con.execute("SELECT session_id FROM automation_runs WHERE session_id IS NOT NULL").fetchall()
        except sqlite3.Error as exc:
            raise RunError(f"automation-exclusion query failed: {exc}") from exc
        return {row[0] for row in rows}
    finally:
        con.close()


# --------------------------------------------------------------------------
# Transcript normalization (mirrors the parsing rules documented in
# zcode-learning-extraction.md Step 1, kept in lockstep with this script)
# --------------------------------------------------------------------------

def strip_noise(text: str) -> str | None:
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"```userselect.*?```", "", text, flags=re.S)
    text = re.sub(r"^# userselect:\s*", "", text)
    text = re.sub(r"^\[\$[^\]]+\]\([^)]*\)\s*", "", text)
    text = re.sub(r"<!--\s*attach\s*-->", "", text).strip()
    text = re.sub(r"\s*/plan\s*$", "", text).strip()
    for prefix in ("<scheduled-task", "<app-context>", "<environment_context>", "<user_instructions>"):
        if text.startswith(prefix):
            return None
    if text.startswith("You are ") and len(text) > 400:
        return None
    if text in NOISE_EXACT:
        return None
    if not text or text.startswith("The TodoWrite tool hasn't been used recently"):
        return None
    return text


def part_event(role: str, part: dict[str, Any]) -> tuple[str, str] | None:
    ptype = part.get("type")
    if ptype == "text":
        if role not in ("user", "assistant"):
            return None
        text = strip_noise(str(part.get("text") or "").strip())
        return (role, text) if text else None
    if ptype == "tool":
        state = part.get("state") or {}
        status = state.get("status")
        tool = part.get("tool") or "tool"
        text = f"{tool} {status}"
        if status == "error" and state.get("error"):
            text += f": {str(state.get('error'))[:200]}"
        return ("tool", text)
    if ptype == "file" and role == "user":
        mime = str(part.get("mime") or "")
        url = str(part.get("url") or "")
        if mime.startswith("text/") and url.startswith("/"):
            try:
                candidate = Path(url)
                if candidate.is_file():
                    content = candidate.read_text(errors="replace")[:4000]
                    return ("user", "[pasted file] " + content)
            except OSError:
                return None
        return None
    return None


def normalize_session(con: sqlite3.Connection, session: dict[str, Any], lower: int, upper: int) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int | None]] = set()
    query = (
        "SELECT m.id, m.sequence, m.time_created, json_extract(m.data,'$.role') as role, p.data "
        "FROM message m JOIN part p ON p.message_id = m.id "
        "WHERE m.session_id = ? ORDER BY m.sequence, p.sequence"
    )
    for message_id, sequence, time_created, role, part_data in con.execute(query, (session["id"],)):
        try:
            part = json.loads(part_data) if isinstance(part_data, str) else (part_data or {})
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(part, dict):
            continue
        item = part_event(str(role or ""), part)
        if item is None:
            continue
        ev_role, text = item
        if not text:
            continue
        clean = redact(text)
        epoch = int(time_created) if time_created is not None else None
        key = (ev_role, digest_bytes(clean.encode()), epoch)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "session_id": session["id"],
            "message_id": message_id,
            "sequence": sequence,
            "event_epoch_ms": epoch,
            "event_timestamp": iso_ms(epoch) if epoch is not None else "",
            "event_sha256": digest_bytes(f"{ev_role}\0{epoch}\0{clean}".encode()),
            "role": ev_role,
            "text": clean,
            # An event is decision-eligible only if it has a timestamp *and*
            # that timestamp falls inside this run's window. A message with
            # no timestamp at all is conservatively treated as context-only,
            # never as evidence that can authorize a decision -- there is no
            # defensible run-bound rule for it without a real time to check.
            "is_new": epoch is not None and (lower < epoch <= upper),
        })
    return {
        "id": session["id"],
        "directory": session.get("directory"),
        "title": session.get("title"),
        "time_created": session.get("time_created"),
        "time_updated": session.get("time_updated"),
        "events": events,
    }


def first_user_text(con: sqlite3.Connection, session_id: str) -> str:
    query = (
        "SELECT json_extract(m.data,'$.role') as role, p.data "
        "FROM message m JOIN part p ON p.message_id = m.id "
        "WHERE m.session_id = ? AND json_extract(p.data,'$.type') = 'text' "
        "ORDER BY m.sequence, p.sequence LIMIT 10"
    )
    for role, part_data in con.execute(query, (session_id,)):
        if role != "user":
            continue
        try:
            part = json.loads(part_data) if isinstance(part_data, str) else (part_data or {})
        except (json.JSONDecodeError, TypeError):
            continue
        text = str((part or {}).get("text") or "").strip()
        if text:
            return text
    return ""


def discover_sessions(db_path: Path, tasks_db_path: Path, lower: int, upper: int,
                       scope_roots: list[Path], self_session_id: str | None) -> list[dict[str, Any]]:
    # The automation-exclusion database is required (fails closed if
    # missing/broken -- see load_automation_ids); it is a separate SQLite
    # file from the session database, so it cannot share the session
    # database's read transaction below.
    auto_ids = load_automation_ids(tasks_db_path)
    con = open_ro(db_path)
    try:
        validate_session_db_schema(con)
        # Discovery and normalization run on this single connection inside
        # one explicit read transaction, so a concurrent writer to the live
        # ZCode session database cannot hand us a torn view where the
        # session list and a session's own transcript come from different
        # moments in time.
        con.execute("BEGIN")
        try:
            # A session is discovered if *either* its own time_updated row
            # falls in the window, *or* it has at least one eligible
            # user/assistant message timestamped inside the window -- a
            # session's time_updated can advance past the window's upper
            # bound (e.g. an assistant reply lands a moment after the run's
            # snapshot instant) while the user's own message that triggered
            # it was still safely inside the window; relying on time_updated
            # alone would silently drop that message's evidence for good.
            # Both queries run on the same connection inside the single read
            # transaction already open here.
            rows_by_row = con.execute(
                "SELECT id, directory, title, time_updated, time_created, task_type "
                "FROM session WHERE parent_id IS NULL AND time_updated > ? AND time_updated <= ? "
                "ORDER BY time_updated",
                (lower, upper),
            ).fetchall()
            rows_by_message = con.execute(
                "SELECT DISTINCT s.id, s.directory, s.title, s.time_updated, s.time_created, s.task_type "
                "FROM session s JOIN message m ON m.session_id = s.id "
                "WHERE s.parent_id IS NULL AND m.time_created > ? AND m.time_created <= ? "
                "AND json_extract(m.data, '$.role') IN ('user', 'assistant')",
                (lower, upper),
            ).fetchall()
            combined: dict[str, tuple] = {}
            for row in rows_by_row + rows_by_message:
                combined.setdefault(row[0], row)
            rows = sorted(combined.values(), key=lambda row: row[3])
            scopes = [root.expanduser().resolve() for root in scope_roots]
            sessions: list[dict[str, Any]] = []
            for sid, directory, title, updated, created, task_type in rows:
                if task_type == "subagent_child":
                    continue
                if self_session_id and sid == self_session_id:
                    continue
                if sid in auto_ids:
                    continue
                if title and SCHEDULED_TASK_MARK in title:
                    continue
                if not directory:
                    continue
                try:
                    dpath = Path(directory).expanduser().resolve()
                except OSError:
                    continue
                if scopes and not any(under(dpath, scope) for scope in scopes):
                    continue
                if SCHEDULED_TASK_MARK in first_user_text(con, sid):
                    continue
                session = {"id": sid, "directory": directory, "title": title, "time_updated": updated, "time_created": created}
                sessions.append(normalize_session(con, session, lower, upper))
            return sessions
        finally:
            con.execute("COMMIT")
    finally:
        con.close()


# --------------------------------------------------------------------------
# Live memory targets, snapshotting, staging
# --------------------------------------------------------------------------

def live_target_path(ws: Workspace, rel: str) -> Path:
    """Resolve a manifest/backup/control relative key to its live absolute
    path -- a single, central mapping used everywhere a relative key must be
    turned back into a path to read, write, or check (backup, restore,
    preflight, apply). This is deliberately independent of directory
    enumeration (``targets()``/``snapshot()``), so it still resolves
    correctly even when the live ``docs`` tree has been replaced by a
    symlink (enumeration would then see nothing to iterate).
    """
    if rel == WATERMARK_REL:
        return ws.state
    if rel == LEDGER_KEY:
        return ws.ledger
    return ws.home / rel


def targets(ws: Workspace) -> dict[str, Path]:
    """Enumerate every live memory target.

    A symlink standing in for a live target -- whether a dangling one or one
    that points at a real file -- is never silently omitted from the
    baseline: that would let an attacker (or a bug) hide a file from
    `snapshot`/`backup_live` entirely. It is treated as a hard failure
    instead.
    """
    result = {"AGENTS.md": ws.home / "AGENTS.md", LEDGER_KEY: ws.ledger}
    if ws.memory.is_symlink():
        raise RunError(f"refusing to treat symlinked directory as the live memory root: {ws.memory}")
    if ws.memory.is_dir():
        for path in ws.memory.rglob("*"):
            if path.is_symlink():
                raise RunError(f"refusing to treat symlinked live memory path as a target: {path}")
            if path.is_file():
                result[str(path.relative_to(ws.home))] = path
    return result


def snapshot(ws: Workspace, destination: Path | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for rel, source in targets(ws).items():
        if not source.exists():
            continue
        values[rel] = digest_file(source)
        if destination is not None:
            dest = destination / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest, follow_symlinks=False)
    return values


def resolve_run_dir(ws: Workspace, run_id: str) -> Path:
    """Central, safe resolver from a run id to its run directory.

    Every command and metadata access that needs a run directory from a
    caller-supplied run id must go through this function: it validates the
    run id's shape, refuses a run-directory *entry* that is itself a
    symlink (never traversing it to find out where it points), and confirms
    the resolved path is still contained within ``ws.runs``. On success it
    returns the plain, unresolved ``ws.runs / run_id`` path -- callers that
    need the canonical (symlink-free) path for a subsequent read/write
    should resolve components themselves as needed, but every containment
    and symlink check has already happened here.
    """
    run_id = safe_run_id(run_id)
    candidate = ws.runs / run_id
    if candidate.is_symlink():
        raise RunError(f"refusing to use symlinked run directory: {candidate}")
    resolved = candidate.resolve()
    if not under(resolved, ws.runs):
        raise RunError(f"run directory escapes runs root: {run_id}")
    return candidate


def load_manifest(ws: Workspace, run_id: str) -> tuple[Path, dict[str, Any]]:
    run_dir = resolve_run_dir(ws, run_id)
    manifest = read_json(run_dir / "manifest.json")
    if not manifest:
        raise RunError("manifest is missing or invalid")
    return run_dir, manifest


# --------------------------------------------------------------------------
# Trusted control state: runner-controlled records living outside the
# agent-editable run directory, under
# ``<zcode-home>/self-improve/extraction-control/<run_id>/``. The editable
# manifest.json (and, later, the backup manifest) must match this state for
# every security-sensitive field; a run with no trusted control state at all
# (e.g. one prepared by a version of this script predating this feature) is
# refused outright rather than trusted on the strength of its editable
# manifest alone.
# --------------------------------------------------------------------------

def control_dir_for(ws: Workspace, run_id: str) -> Path:
    return ws.home / CONTROL_DIR_REL / run_id


def ensure_control_dir(control_dir: Path) -> None:
    control_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(control_dir, 0o700)


def write_control_json(path: Path, value: dict[str, Any]) -> None:
    atomic_json(path, value)
    os.chmod(path, 0o600)


def build_authorized_targets(baseline_hashes: dict[str, str], watermark_baseline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    authorized: dict[str, dict[str, Any]] = {
        rel: {"present": True, "sha256": sha} for rel, sha in baseline_hashes.items()
    }
    existed = bool((watermark_baseline or {}).get("existed"))
    authorized[WATERMARK_REL] = {"present": existed, "sha256": (watermark_baseline or {}).get("hash") if existed else None}
    return authorized


def write_control_record(ws: Workspace, run_id: str, manifest_data: dict[str, Any]) -> None:
    record = {field: manifest_data[field] for field in CONTROL_SENSITIVE_FIELDS}
    record["version"] = 1
    record["authorized_targets"] = build_authorized_targets(manifest_data["baseline_hashes"], manifest_data["watermark_baseline"])
    control_dir = control_dir_for(ws, run_id)
    ensure_control_dir(control_dir)
    write_control_json(control_dir / "control.json", record)


def load_control_record(ws: Workspace, run_id: str) -> dict[str, Any]:
    path = control_dir_for(ws, run_id) / "control.json"
    if path.is_symlink():
        raise RunError(f"refusing to read symlinked trusted control record: {path}")
    record = read_json(path)
    if record is None:
        raise RunError(
            f"trusted control state is missing or malformed for run {run_id!r} (a legacy run "
            "prepared before this state existed, or its control state was removed) -- refusing to "
            "guess about validation or recovery"
        )
    return record


def load_control_apply_state(ws: Workspace, run_id: str) -> dict[str, Any] | None:
    path = control_dir_for(ws, run_id) / "apply.json"
    if path.is_symlink():
        raise RunError(f"refusing to read symlinked trusted apply state: {path}")
    return read_json(path)


def write_control_apply_state(ws: Workspace, run_id: str, staged: set[str], backup: Path) -> None:
    """Record the trusted, runner-controlled apply state: the exact backup
    path, a digest binding the backup manifest's bytes, and independent
    copies of the backup's own inventory/presence/hashes. This is written
    *after* the backup is fully created (and, by construction from its own
    ``presence.json``, already verified consistent with itself) and *before*
    any live file is touched -- `recover` cross-checks a candidate backup
    against this record before trusting a single byte of it.
    """
    backup_manifest = read_json(backup / "presence.json") or {}
    state = {
        "version": 1,
        "run_id": run_id,
        "staged": sorted(staged),
        "backup_path": str(backup),
        "backup_manifest_sha256": digest_file(backup / "presence.json"),
        "authorized_inventory": sorted(backup_manifest.get("inventory", [])),
        "expected_presence": backup_manifest.get("presence", {}),
        "expected_hashes": backup_manifest.get("hashes", {}),
    }
    control_dir = control_dir_for(ws, run_id)
    ensure_control_dir(control_dir)
    write_control_json(control_dir / "apply.json", state)


def verify_manifest_matches_control(manifest: dict[str, Any], control: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in CONTROL_SENSITIVE_FIELDS:
        if manifest.get(field) != control.get(field):
            errors.append(f"manifest field {field!r} does not match the trusted control record (possible tampering)")
    return errors


def preflight_write_targets(ws: Workspace, rels: Any) -> None:
    """Check every relative key in ``rels`` for a symlinked ancestor before
    any of them is written or unlinked -- called once, up front, so a
    hostile symlink discovered partway through a set never leaves some
    targets already written and others not.
    """
    for rel in sorted(set(rels)):
        assert_safe_write_ancestors(ws, live_target_path(ws, rel))


def read_valid_commit_marker(run_dir: Path, run_id: str) -> dict[str, Any]:
    """Read and strictly validate a run's commit marker before recovery acts
    on it in any way. There is no filename-based fallback anywhere in this
    path: a missing run directory, a missing or malformed marker file, a
    marker whose ``run_id`` does not match, or a marker with an unrecognized
    ``status`` all fail closed here, before a single byte of any backup is
    read.
    """
    if not run_dir.exists():
        raise RunError(f"no run directory found for {run_id!r}; refusing to guess about recovery")
    marker_path = commit_marker_path(run_dir)
    if marker_path.is_symlink():
        raise RunError(f"refusing to read symlinked commit marker: {marker_path}")
    marker = read_json(marker_path)
    if marker is None:
        raise RunError(
            f"commit marker is missing or malformed for run {run_id!r}; refusing to recover without "
            "a valid, durable marker (there is no filename-based backup fallback)"
        )
    if marker.get("run_id") != run_id:
        raise RunError(f"commit marker run_id mismatch: expected {run_id!r}, found {marker.get('run_id')!r}")
    status = marker.get("status")
    if status not in VALID_MARKER_STATUSES:
        raise RunError(f"commit marker has an unrecognized status {status!r} for run {run_id!r}")
    return marker


def staged_files(staging: Path) -> set[str]:
    files: set[str] = set()
    if not staging.exists():
        return files
    for path in staging.rglob("*"):
        if path.is_symlink():
            raise RunError(f"staging contains symlink: {path.relative_to(staging)}")
        if path.is_file():
            files.add(str(path.relative_to(staging)))
    return files


def read_decisions(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "decisions.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("decision is not an object")
                records.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RunError(f"invalid decisions.jsonl: {exc}") from exc
    return records


def read_session_dispositions(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "session_dispositions.jsonl"
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("session_disposition is not an object")
                records.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RunError(f"invalid session_dispositions.jsonl: {exc}") from exc
    return records


# --------------------------------------------------------------------------
# Commit journal (durable marker) helpers
# --------------------------------------------------------------------------

def commit_marker_path(run_dir: Path) -> Path:
    return run_dir / "commit.json"


def write_commit_marker(run_dir: Path, run_id: str, status: str, backup: Path | None = None) -> None:
    atomic_json(commit_marker_path(run_dir), {
        "run_id": run_id,
        "status": status,
        "backup": str(backup) if backup else None,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    })


def _run_dirs(ws: Workspace) -> list[Path]:
    if not ws.runs.is_dir():
        return []
    return [d for d in ws.runs.iterdir() if d.is_dir() and not d.is_symlink()]


def find_incomplete_commits(ws: Workspace) -> list[str]:
    incomplete: list[str] = []
    for run_dir in _run_dirs(ws):
        data = read_json(run_dir / "commit.json")
        if data and data.get("status") == "in_progress":
            incomplete.append(str(data.get("run_id") or run_dir.name))
    return sorted(set(incomplete))


def protected_backup_paths(ws: Workspace) -> set[str]:
    """Backups that `recover` still needs -- referenced by an in-progress commit
    marker. `prune` must never delete the only backup an interrupted commit can
    be recovered from, no matter how old it is or how many newer backups exist.
    """
    protected: set[str] = set()
    for run_dir in _run_dirs(ws):
        data = read_json(run_dir / "commit.json")
        if data and data.get("status") == "in_progress" and data.get("backup"):
            protected.add(str(Path(data["backup"]).resolve()))
    return protected


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_run(ws: Workspace, run_dir: Path) -> tuple[bool, list[str], list[str]]:
    manifest = read_json(run_dir / "manifest.json")
    if not manifest:
        return False, ["manifest is missing or invalid"], []
    errors: list[str] = []

    # The editable manifest is only ever trusted after it is confirmed to
    # match the runner-controlled trusted control state recorded outside the
    # agent-editable run directory at prepare time. A run with no trusted
    # control state at all (legacy run, or state removed) fails closed here
    # rather than falling back to trusting the manifest alone.
    try:
        control = load_control_record(ws, run_dir.name)
    except RunError as exc:
        errors.append(str(exc))
    else:
        errors.extend(verify_manifest_matches_control(manifest, control))

    staging = run_dir / "staging"
    baseline: dict[str, str] = manifest.get("baseline_hashes") or {}
    if snapshot(ws) != baseline:
        errors.append("live memory changed after prepare")
    staged = staged_files(staging)
    baseline_files = set(baseline)
    additions, deletions = staged - baseline_files, baseline_files - staged
    if deletions:
        errors.append("staged deletions are not allowed: " + ", ".join(sorted(deletions)))
    for rel in additions:
        if not rel.startswith("docs/") or not safe_relative_path(rel):
            errors.append(f"new file outside docs/: {rel}")
    changed = sorted(rel for rel in staged if rel not in baseline or digest_file(staging / rel) != baseline[rel])

    decisions = read_decisions(run_dir)
    lower_bound = manifest.get("lower_bound")
    upper_bound = manifest.get("upper_bound")
    # A run's window bounds must themselves be sane numbers before any
    # evidence eligibility can be re-derived from them below.
    bounds_valid = (
        isinstance(lower_bound, (int, float)) and not isinstance(lower_bound, bool)
        and isinstance(upper_bound, (int, float)) and not isinstance(upper_bound, bool)
        and lower_bound < upper_bound
    )
    if not bounds_valid:
        errors.append("manifest has invalid or missing lower_bound/upper_bound; cannot validate evidence eligibility")

    # Index every normalized event by (session_id, event_sha256) so each
    # evidence citation can be checked against one *actual* event rather
    # than just against a bag of known hashes -- a citation that names the
    # wrong session for a real hash must not validate. The evidence file's
    # own bytes are also pinned to the hash `prepare` recorded in the
    # manifest, so nothing can fabricate or edit an event after the fact and
    # have it trusted here.
    events_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    evidence_path = run_dir / "normalized_sessions.jsonl"
    try:
        evidence_bytes = evidence_path.read_bytes()
    except OSError as exc:
        errors.append(f"invalid normalized evidence: {exc}")
        evidence_bytes = None
    if evidence_bytes is not None:
        expected_evidence_hash = manifest.get("normalized_evidence_sha256")
        if not isinstance(expected_evidence_hash, str) or not expected_evidence_hash:
            errors.append("manifest is missing normalized_evidence_sha256; evidence integrity cannot be verified")
        elif digest_bytes(evidence_bytes) != expected_evidence_hash:
            errors.append(
                "normalized_sessions.jsonl does not match the manifest's recorded hash "
                "(tampered or corrupted since prepare)"
            )
        try:
            evidence_text = evidence_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"invalid normalized evidence: {exc}")
            evidence_text = ""
        try:
            for line in evidence_text.splitlines():
                if not line.strip():
                    continue
                session = json.loads(line)
                for event in session.get("events", []):
                    events_by_key[(session.get("id"), event.get("event_sha256"))] = event
        except (json.JSONDecodeError, KeyError) as exc:
            errors.append(f"invalid normalized evidence: {exc}")

    decision_destinations: set[str] = set()
    supporting_destinations: set[str] = set()
    has_primary_write = False
    for record in decisions:
        for key in ("claim", "kind", "scope", "confidence", "disposition", "evidence"):
            if key not in record:
                errors.append(f"decision missing {key}")
        disposition = record.get("disposition")
        confidence = record.get("confidence")
        if disposition not in DISPOSITIONS:
            errors.append(f"invalid disposition: {disposition}")
        if record.get("kind") not in {"behavioral_rule", "technical_fact"}:
            errors.append(f"invalid kind: {record.get('kind')}")
        if record.get("scope") not in {"global", "project"}:
            errors.append(f"invalid scope: {record.get('scope')}")
        if confidence not in {"confirmed", "provisional"}:
            errors.append(f"invalid confidence: {confidence}")

        # Only a *write* disposition's `destination` may ever authorize a
        # changed memory file -- a PROVISIONAL/REJECTED/SKIPPED_DUP decision
        # can reference a destination for informational purposes (e.g. "see
        # docs/rules.md"), but that reference must never itself count toward
        # authorizing a live edit to that file.
        dest = record.get("destination")
        if dest is not None:
            if not isinstance(dest, str) or not safe_relative_path(dest) or dest not in staged:
                errors.append(f"invalid decision destination: {dest}")
            elif disposition not in WRITE_DISPOSITIONS:
                errors.append(f"destination may only be declared on a write disposition, not {disposition}")
            else:
                decision_destinations.add(dest)
                has_primary_write = True
        if record.get("scope") == "project" and dest and not dest.startswith("docs/projects/"):
            errors.append(f"project fact has non-project destination: {dest}")
        if disposition in WRITE_DISPOSITIONS and not dest:
            errors.append("write disposition lacks destination")

        # `supporting_destinations` lets a single write decision also cover
        # the *structural* index/map updates that necessarily accompany it
        # (e.g. a new docs file needs a docs/index.md entry and an AGENTS.md
        # pointer, or a new project needs its docs/projects/<name>/index.md
        # and the docs/projects/index.md catalog) -- never an arbitrary
        # content doc, which must instead be its own primary write decision.
        # It never authorizes anything by itself: it requires at least one
        # *primary* write decision to exist anywhere in the run.
        sup_list = record.get("supporting_destinations")
        if sup_list is not None:
            if disposition not in WRITE_DISPOSITIONS:
                errors.append("supporting_destinations may only be declared on a write decision")
            if not isinstance(sup_list, list):
                errors.append("supporting_destinations must be a list")
            else:
                for sup in sup_list:
                    if not isinstance(sup, str) or not safe_relative_path(sup) or sup not in staged:
                        errors.append(f"invalid supporting destination: {sup}")
                    elif not SUPPORTING_DESTINATION_RE.match(sup):
                        errors.append(
                            "supporting destination must be a structural index/map file (AGENTS.md, "
                            f"docs/index.md, or a docs/projects index): {sup}"
                        )
                    else:
                        supporting_destinations.add(sup)

        evidence_list = record.get("evidence")
        if not isinstance(evidence_list, list) or not evidence_list:
            errors.append("decision has no evidence")
            evidence_list = []
        resolved_events: list[dict[str, Any]] = []
        for item in evidence_list:
            if not isinstance(item, dict):
                errors.append(f"invalid evidence entry: {item!r}")
                continue
            sha = item.get("event_sha256")
            event = events_by_key.get((item.get("session_id"), sha))
            if event is None:
                errors.append(f"missing evidence hash: {sha}")
                continue
            if "event_timestamp" in item and item["event_timestamp"] != event.get("event_timestamp"):
                errors.append(f"evidence event_timestamp mismatch: {sha}")
                continue
            epoch = event.get("event_epoch_ms")
            epoch_numeric = isinstance(epoch, (int, float)) and not isinstance(epoch, bool)
            # Eligibility is independently re-derived from the manifest's own
            # lower_bound/upper_bound here, not just trusted from the
            # event's `is_new` flag -- an event whose epoch is not a real
            # numeric timestamp strictly inside (lower_bound, upper_bound]
            # is never eligible, even if `is_new` claims otherwise.
            epoch_in_bounds = bounds_valid and epoch_numeric and (lower_bound < epoch <= upper_bound)
            eligible = bool(event.get("is_new")) and epoch_in_bounds
            if not eligible:
                errors.append(f"evidence event is not eligible under the run's evidence policy: {sha}")
                continue
            resolved_events.append(event)

        if disposition == "PROVISIONAL" and confidence != "provisional":
            errors.append(f"PROVISIONAL disposition requires provisional confidence, got {confidence}")
        if confidence == "provisional" and disposition != "PROVISIONAL":
            errors.append(f"provisional confidence may only pair with PROVISIONAL disposition, not {disposition}")
        if disposition in WRITE_DISPOSITIONS:
            if confidence != "confirmed":
                errors.append(f"write disposition {disposition} requires confirmed confidence, got {confidence}")
            if not any(ev.get("role") == "user" for ev in resolved_events):
                errors.append("write disposition lacks a qualifying user-role evidence event")

        if SECRET_RE.search(str(record.get("claim", ""))) or SECRET_RE.search(str(record.get("reason", ""))):
            errors.append("secret-like value in decision metadata")

    if supporting_destinations and not has_primary_write:
        errors.append("supporting_destinations present without any primary write decision")
    authorized = decision_destinations | (supporting_destinations if has_primary_write else set())

    changed_memory = set(changed) - {LEDGER_KEY}
    if changed_memory and LEDGER_KEY not in changed:
        errors.append("memory changes must include an updated extraction ledger")
    for rel in sorted(changed_memory - authorized):
        errors.append(f"memory change not authorized by any decision destination: {rel}")
    for rel in changed:
        if SECRET_RE.search((staging / rel).read_text(errors="replace")):
            errors.append(f"secret-like value in changed file: {rel}")

    if LEDGER_KEY in changed:
        # The ledger is append-only bookkeeping: the staged copy must start
        # with the exact bytes of the live ledger (or be entirely new if the
        # ledger didn't exist yet). Anything else -- truncation, wholesale
        # replacement, or an in-place edit of an earlier entry -- is
        # rejected outright, no matter how plausible the new content looks.
        baseline_ledger_bytes = ws.ledger.read_bytes() if ws.ledger.exists() else b""
        staged_ledger_bytes = (staging / LEDGER_KEY).read_bytes()
        if not staged_ledger_bytes.startswith(baseline_ledger_bytes):
            errors.append("staged extraction ledger must start with the exact baseline ledger bytes (append-only)")

    map_path = staging / "AGENTS.md"
    if map_path.exists():
        map_text = map_path.read_text()
        if len(map_text.splitlines()) > 100:
            errors.append("AGENTS.md exceeds the 100-line limit")
        pointers = {match.rstrip(".,;:").lstrip("./") for match in POINTER_RE.findall(map_text)}
        for pointer in pointers:
            if not (staging / pointer).exists():
                errors.append(f"broken map pointer: {pointer}")

    # Complete discovered-session accounting: every session the runner
    # discovered at prepare time must be explicitly accounted for -- either
    # it contributed evidence to a decision or the operator recorded that it
    # was reviewed and yielded nothing. This closes the gap where a session
    # could be silently dropped between discovery and the summary.
    manifest_session_ids = {s["id"] for s in manifest.get("sessions", [])}
    decision_evidence_session_ids: set[str] = set()
    for record in decisions:
        for item in record.get("evidence") or []:
            if isinstance(item, dict) and isinstance(item.get("session_id"), str):
                decision_evidence_session_ids.add(item["session_id"])
    dispositions = read_session_dispositions(run_dir)
    recorded_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    contributed_ids: set[str] = set()
    for record in dispositions:
        sid = record.get("session_id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"session_disposition missing session_id: {record}")
            continue
        if sid in recorded_ids:
            duplicate_ids.add(sid)
        recorded_ids.add(sid)
        status = record.get("status")
        if status not in SESSION_DISPOSITION_STATUSES:
            errors.append(f"invalid session_disposition status for {sid}: {status!r} (must be one of {sorted(SESSION_DISPOSITION_STATUSES)})")
        elif status == "contributed":
            contributed_ids.add(sid)
    for sid in sorted(duplicate_ids):
        errors.append(f"session_dispositions.jsonl has a duplicate session_id: {sid}")
    missing = manifest_session_ids - recorded_ids
    for sid in sorted(missing):
        errors.append(f"discovered session not accounted for in session_dispositions.jsonl: {sid}")
    unknown = recorded_ids - manifest_session_ids
    for sid in sorted(unknown):
        errors.append(f"session_dispositions.jsonl references a session outside this run: {sid}")
    unevidenced = contributed_ids - decision_evidence_session_ids
    for sid in sorted(unevidenced):
        errors.append(f"session marked contributed but no decision cites its evidence: {sid}")

    diff_parts: list[str] = []
    for rel in sorted(set(baseline) | staged):
        old, new = ws.home / rel, staging / rel
        old_text = old.read_text(errors="replace") if old.exists() else ""
        new_text = new.read_text(errors="replace") if new.exists() else ""
        if old_text != new_text:
            diff_parts.append("".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), fromfile=f"a/{rel}", tofile=f"b/{rel}")))
    (run_dir / "diff.patch").write_text("\n".join(diff_parts))

    report = [
        "# ZCode extraction run report", "",
        f"- run_id: {manifest['run_id']}",
        f"- sessions discovered: {manifest.get('session_count', 0)}",
        f"- changed files: {', '.join(changed) or 'none'}", "",
        "## Dispositions", "",
    ]
    report.extend(f"- {item.get('disposition')}: {item.get('claim')} -> {item.get('destination') or 'n/a'}" for item in decisions)
    (run_dir / "report.md").write_text("\n".join(report) + "\n")

    passed = not errors
    atomic_json(run_dir / "validation.json", {"passed": passed, "errors": errors, "changed_files": changed})
    return passed, errors, changed


# --------------------------------------------------------------------------
# Backup / restore of live targets (used by apply + recover)
# --------------------------------------------------------------------------

def backup_live(ws: Workspace, manifest: dict[str, Any], staged: set[str]) -> Path:
    backup = ws.home / f"{BACKUP_PREFIX}{dt.datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')}-{manifest['run_id']}"
    backup.mkdir(parents=True)
    presence: dict[str, bool] = {}
    hashes: dict[str, str] = {}
    for rel in sorted(set(manifest.get("baseline_hashes", {})) | staged | {WATERMARK_REL}):
        if not safe_relative_path(rel):
            raise RunError(f"refusing to back up unsafe path: {rel}")
        source = live_target_path(ws, rel)
        if source.is_symlink():
            raise RunError(f"refusing to back up symlinked live source: {rel}")
        exists = source.exists()
        presence[rel] = exists
        if exists:
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest, follow_symlinks=False)
            hashes[rel] = digest_file(dest)
    # The backup manifest stores the full inventory considered, which paths
    # actually existed pre-run, and a hash of each backed-up file's content
    # -- enough for `recover` to verify the backup before trusting it and to
    # verify each restored file afterward.
    atomic_json(backup / "presence.json", {
        "run_id": manifest["run_id"],
        "inventory": sorted(presence),
        "presence": presence,
        "hashes": hashes,
    })
    return backup


def resolve_backup_for_recovery(ws: Workspace, run_id: str, candidate: Path) -> Path:
    """Resolve and validate a backup directory path before any recovery read
    or write. A marker (or a hand-edited one) that does not prove the backup
    both belongs to this run and lives where backups are supposed to live is
    never trusted -- this is checked before ``verify_backup_for_restore``
    reads anything inside it.
    """
    if candidate.is_symlink():
        raise RunError(f"refusing to use symlinked backup path: {candidate}")
    home = ws.home.resolve()
    resolved = candidate.resolve()
    if not under(resolved, home):
        raise RunError(f"backup path escapes zcode home: {candidate}")
    if resolved.parent != home:
        raise RunError(f"backup directory must be a direct child of zcode home: {candidate}")
    match = BACKUP_NAME_RE.match(resolved.name)
    if not match or match.group("run_id") != run_id:
        raise RunError(
            f"backup directory name does not match the expected extraction-backup naming for run "
            f"{run_id}: {resolved.name}"
        )
    if not resolved.is_dir():
        raise RunError(f"backup directory does not exist: {resolved}")
    return resolved


def read_backup_manifest(backup: Path) -> dict[str, Any]:
    """Read and strictly validate a backup manifest before anything in it is
    trusted. The inventory must be unique, safe relative paths; presence
    must map every inventory entry to a real boolean; and hashes must cover
    *exactly* the present paths -- no more (a hash for a path marked absent
    is just as suspicious as one missing for a path marked present).
    """
    manifest_path = backup / "presence.json"
    if manifest_path.is_symlink():
        raise RunError(f"refusing to read symlinked backup manifest: {manifest_path}")
    data = read_json(manifest_path)
    if data is None:
        raise RunError(f"backup manifest missing or malformed: {manifest_path}")
    presence = data.get("presence")
    hashes = data.get("hashes")
    inventory = data.get("inventory")
    if not isinstance(presence, dict) or not isinstance(hashes, dict) or not isinstance(inventory, list):
        raise RunError(f"backup manifest has the wrong schema: {manifest_path}")
    if len(set(inventory)) != len(inventory) or not all(safe_relative_path(item) for item in inventory):
        raise RunError(f"backup manifest inventory must be unique, safe relative paths: {manifest_path}")
    if set(inventory) != set(presence):
        raise RunError(f"backup manifest inventory does not match its presence map: {manifest_path}")
    if not all(isinstance(v, bool) for v in presence.values()):
        raise RunError(f"backup manifest presence values must all be boolean: {manifest_path}")
    present_paths = {rel for rel, existed in presence.items() if existed}
    if set(hashes) != present_paths:
        raise RunError(f"backup manifest hashes must exactly match the present paths: {manifest_path}")
    if not all(isinstance(v, str) and v for v in hashes.values()):
        raise RunError(f"backup manifest hashes must all be non-empty strings: {manifest_path}")
    return data


def validate_target_path(ws: Workspace, target: Path) -> None:
    if not under(target, ws.home):
        raise RunError(f"refusing to write outside zcode home: {target}")


def assert_safe_write_ancestors(ws: Workspace, target: Path) -> None:
    """Refuse to write/unlink through a symlinked path component. Containment
    to ``ws.home`` alone is not enough: an existing symlink somewhere between
    ``ws.home`` and the target could redirect the write outside it even
    though the *lexical* path looks safe.

    Every ancestor's symlink-ness is checked first, using the *unresolved*
    path (never following a symlink to see where it points) -- this must
    happen before any resolve()-based containment check, otherwise a
    symlinked ancestor that happens to point outside ``ws.home`` would be
    reported as a generic "outside zcode home" containment failure instead
    of being identified as the symlink it is.
    """
    home = ws.home.resolve()
    current = target
    for _ in range(1000):
        if current.exists() and current.is_symlink():
            raise RunError(f"refusing to write through a symlinked path component: {current}")
        if current.resolve() == home:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    validate_target_path(ws, target)


def verify_backup_for_restore(ws: Workspace, run_id: str, candidate: Path) -> tuple[Path, dict[str, Any]]:
    """Fully validate a backup before trusting it for restoration.

    Every check here is read-only -- nothing is written or unlinked. Any
    failure raises ``RunError`` before the caller has touched a single live
    file, the in-progress commit marker, the normalized evidence, or the
    lock: a missing backup, a malformed manifest, a missing backed-up file,
    or a hash mismatch all fail recovery closed rather than guessing.
    """
    backup = resolve_backup_for_recovery(ws, run_id, candidate)
    data = read_backup_manifest(backup)
    if data.get("run_id") != run_id:
        raise RunError(f"backup manifest run_id does not match: expected {run_id}, found {data.get('run_id')!r}")

    # The backup manifest's *own* internal structure was already validated by
    # read_backup_manifest above. Now bind it to the runner-controlled
    # trusted apply state recorded before this backup was ever used for a
    # live write: the backup manifest's bytes must match the digest the
    # runner recorded, and its inventory/presence/hashes must be *exactly*
    # what the runner authorized -- not just internally self-consistent. A
    # backup manifest that was swapped for an empty (but internally valid)
    # one, or one with an extra "absent" entry naming a path the runner never
    # touched, is rejected here even though `read_backup_manifest` alone
    # would have accepted it.
    apply_state = load_control_apply_state(ws, run_id)
    if apply_state is None:
        raise RunError(
            f"trusted apply state is missing for run {run_id!r}; a backup exists but its binding "
            "record does not -- refusing to guess about recovery"
        )
    if digest_file(backup / "presence.json") != apply_state.get("backup_manifest_sha256"):
        raise RunError(f"backup manifest does not match the trusted apply-state digest for run {run_id!r}")
    authorized_inventory = apply_state.get("authorized_inventory")
    if not isinstance(authorized_inventory, list) or set(authorized_inventory) != set(data["inventory"]):
        raise RunError(f"backup inventory does not match the trusted authorized inventory for run {run_id!r}")
    if data["presence"] != apply_state.get("expected_presence"):
        raise RunError(f"backup presence map does not match the trusted apply state for run {run_id!r}")
    if data["hashes"] != apply_state.get("expected_hashes"):
        raise RunError(f"backup hashes do not match the trusted apply state for run {run_id!r}")

    presence: dict[str, Any] = data["presence"]
    hashes: dict[str, Any] = data["hashes"]

    # Full preflight: every restore destination is checked for a symlinked
    # ancestor before a single one of them is written or unlinked, so
    # discovering an unsafe destination partway through never leaves some
    # targets already restored and others not.
    for rel in presence:
        if not safe_relative_path(rel):
            raise RunError(f"backup manifest has an unsafe inventory path: {rel!r}")
        assert_safe_write_ancestors(ws, live_target_path(ws, rel))

    contents: dict[str, bytes] = {}
    for rel, existed in presence.items():
        if not existed:
            continue
        source = backup / rel
        if source.is_symlink():
            raise RunError(f"refusing to restore from symlinked backup source: {source}")
        if not under(source, backup):
            raise RunError(f"backup source escapes backup directory: {source}")
        if not source.is_file():
            raise RunError(f"backup is missing required file: {rel}")
        raw = source.read_bytes()
        expected = hashes.get(rel)
        if not isinstance(expected, str) or digest_bytes(raw) != expected:
            raise RunError(f"backup hash mismatch for {rel}")
        contents[rel] = raw
    return backup, {"presence": presence, "hashes": hashes, "contents": contents}


def apply_verified_restore(ws: Workspace, verified: dict[str, Any]) -> None:
    """Perform the writes/unlinks for an already-verified restore, and
    re-verify each restored file's on-disk hash immediately afterward.
    """
    presence = verified["presence"]
    hashes = verified["hashes"]
    contents = verified["contents"]
    for rel, existed in presence.items():
        target = live_target_path(ws, rel)
        assert_safe_write_ancestors(ws, target)
        if existed:
            atomic_write(target, contents[rel])
            if digest_file(target) != hashes[rel]:
                raise RunError(f"restoration verification failed for {rel}")
        elif target.exists() or target.is_symlink():
            target.unlink()


def prune_runs(ws: Workspace, keep: int) -> dict[str, list[str]]:
    keep = max(int(keep), 1)
    removed: dict[str, list[str]] = {"runs": [], "backups": []}
    locked = (lock_owner(ws) or {}).get("run_id")
    incomplete = set(find_incomplete_commits(ws))
    protected_backups = protected_backup_paths(ws)
    if ws.runs.is_dir():
        run_dirs = sorted((d for d in ws.runs.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
        for d in run_dirs[keep:]:
            if d.name == locked or d.name in incomplete:
                continue
            shutil.rmtree(d, ignore_errors=True)
            removed["runs"].append(d.name)
    backups = sorted(ws.home.glob(f"{BACKUP_PREFIX}*"), key=lambda d: d.stat().st_mtime, reverse=True)
    for d in backups[keep:]:
        if not d.is_dir():
            continue
        if str(d.resolve()) in protected_backups:
            continue
        shutil.rmtree(d, ignore_errors=True)
        removed["backups"].append(d.name)
    return removed


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def cmd_prepare(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    incomplete = find_incomplete_commits(ws)
    if incomplete:
        raise RunError("incomplete commit(s) detected; run `recover --run-id <id>` first: " + ", ".join(incomplete))
    run_id = safe_run_id(args.run_id or default_run_id())
    acquire_lock(ws, run_id)
    try:
        lower = load_watermark(ws)
        # Record the watermark's pre-run presence/hash the same way live
        # memory's baseline_hashes is recorded, so a crash between the first
        # commit marker and the durable backup can be told apart from a real
        # divergence instead of only ever being safe when no watermark file
        # exists at all (see cmd_recover).
        watermark_existed = ws.state.exists()
        watermark_hash = digest_file(ws.state) if watermark_existed else None
        started = now_ms()
        bootstrap = False
        if lower is None:
            lower = started - args.bootstrap_hours * 3600 * 1000
            bootstrap = True
        db_path = Path(args.db_path).expanduser() if args.db_path else ws.home / "cli" / "db" / "db.sqlite"
        tasks_db_path = Path(args.tasks_db_path).expanduser() if args.tasks_db_path else ws.home / "v2" / "tasks-index.sqlite"
        if not db_path.exists():
            raise RunError(f"session database not found: {db_path}")
        default_scope = [str(Path.home() / "Downloads" / "Personal"), str(Path.home() / "Downloads" / "Work")]
        scope_roots = [Path(item).expanduser() for item in (args.scope_root if args.scope_root is not None else default_scope)]
        sessions = discover_sessions(db_path, tasks_db_path, lower, started, scope_roots, args.self_session_id)
        run_dir = resolve_run_dir(ws, run_id)
        run_dir.mkdir(parents=True)
        staging = run_dir / "staging"
        staging.mkdir()
        evidence = run_dir / "normalized_sessions.jsonl"
        with evidence.open("w", encoding="utf-8") as fh:
            for session in sessions:
                fh.write(json.dumps(session, sort_keys=True) + "\n")
        os.chmod(evidence, 0o600)
        # Pin the normalized evidence file's content with a hash recorded in
        # the manifest -- validate_run requires an exact match, so nothing
        # can fabricate or edit an evidence event after prepare and have it
        # trusted.
        evidence_sha256 = digest_file(evidence)
        prompt_path = Path(args.prompt_file).expanduser() if args.prompt_file else None
        manifest_data = {
            "version": 1,
            "run_id": run_id,
            "automation_id": args.automation_id or "",
            "model_id": args.model_id or "",
            "prompt_sha256": digest_file(prompt_path) if prompt_path and prompt_path.exists() else "",
            "lower_bound": lower,
            "upper_bound": started,
            "bootstrap": bootstrap,
            "session_count": len(sessions),
            "sessions": [{key: session[key] for key in ("id", "directory", "title", "time_updated", "time_created")} for session in sessions],
            "baseline_hashes": snapshot(ws, staging),
            "watermark_baseline": {"existed": watermark_existed, "hash": watermark_hash},
            "normalized_evidence_sha256": evidence_sha256,
        }
        atomic_json(run_dir / "manifest.json", manifest_data)
        # Bind every security-sensitive field of this run into runner-
        # controlled trusted state, outside the agent-editable run
        # directory, *before* reporting success -- validate/apply/recover
        # all refuse to trust the editable manifest unless it matches this
        # record exactly.
        write_control_record(ws, run_id, manifest_data)
        print(json.dumps({
            "run_id": run_id, "run_dir": str(run_dir), "session_count": len(sessions),
            "lower_bound": lower, "upper_bound": started, "bootstrap": bootstrap,
        }))
        return 0
    except Exception:
        release_lock(ws, run_id)
        raise


def cmd_validate(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    require_lock(ws, args.run_id)
    run_dir, _ = load_manifest(ws, args.run_id)
    passed, errors, changed = validate_run(ws, run_dir)
    print(json.dumps({"passed": passed, "errors": errors, "changed_files": changed}))
    return 0 if passed else 1


def cmd_apply(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    if not args.apply:
        raise RunError("refusing to apply without --apply")
    require_lock(ws, args.run_id)
    run_id = safe_run_id(args.run_id)
    run_dir, manifest = load_manifest(ws, run_id)
    staged = staged_files(run_dir / "staging")

    # Full symlink preflight over every path this apply might touch -- run
    # first, before even re-validation, so a hostile symlink swap (e.g. the
    # whole docs/ tree replaced by a symlink after prepare) is reported as
    # exactly that instead of being masked by a generic staleness error
    # further down, and so nothing is written before every destination is
    # confirmed safe.
    preflight_rels = sorted(set(manifest.get("baseline_hashes", {})) | staged | {WATERMARK_REL})
    preflight_write_targets(ws, preflight_rels)

    # A validation.json on disk only proves staging passed at some point in the
    # past -- staging, decisions.jsonl, or session_dispositions.jsonl could have
    # been edited since (by hand, or by a second `validate` call that then
    # failed). Trusting that stale file would let unreviewed changes through,
    # so apply always recomputes validation against the current on-disk state
    # immediately before writing anything live. This also re-checks the live
    # baseline (and, via validate_run, the trusted control record), so those
    # checks are intentionally not duplicated here.
    passed, errors, _ = validate_run(ws, run_dir)
    if not passed:
        raise RunError("run does not pass validation: " + "; ".join(errors))

    # Backup-then-trust-then-commit, in that order, and only once each:
    # fully create the pre-run backup, bind it into runner-controlled trusted
    # apply state, and only then publish the single durable commit marker --
    # before any of this, no live target has been touched, so an
    # interruption anywhere up to and including this point needs no
    # recovery at all.
    backup = backup_live(ws, manifest, staged)
    write_control_apply_state(ws, run_id, staged, backup)
    write_commit_marker(run_dir, run_id, "in_progress", backup=backup)

    # Deliberately not wrapped in try/except: an interruption here (including
    # a hard kill) leaves the marker at "in_progress" and some staged files
    # possibly applied and some not -- recoverable via `recover`, not atomic.
    for rel in sorted(staged):
        target = live_target_path(ws, rel)
        validate_target_path(ws, target)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, (run_dir / "staging" / rel).read_bytes())

    # Watermark advances only after every staged memory file has been
    # written -- a failed run always re-processes the same sessions.
    watermark = {"last_time_updated": manifest["upper_bound"]}
    atomic_json(ws.state, watermark)

    write_commit_marker(run_dir, run_id, "completed", backup=backup)
    release_lock(ws, run_id)
    (run_dir / "normalized_sessions.jsonl").unlink(missing_ok=True)
    print(json.dumps({"applied": True, "backup": str(backup), "watermark": watermark}))
    return 0


def _recover_in_progress(ws: Workspace, run_dir: Path, run_id: str, marker: dict[str, Any]) -> dict[str, Any]:
    """Perform recovery for a run whose marker has already been confirmed
    valid and ``in_progress``. Shared by `recover` (which additionally
    enforces normal lock ownership) and `repair-recover` (which claims
    ownership of a malformed/abandoned lock first) so the actual
    verify-then-restore logic is not duplicated between them.
    """
    marker_backup = marker.get("backup")

    if not marker_backup:
        # The marker was published *before* backup_live() made the backup
        # durable (see cmd_apply's write order) -- by construction, no live
        # target has been written yet in that window. It is only safe to
        # abort without restoring anything if that invariant still holds:
        # live memory *and* the watermark must still exactly match this
        # run's own recorded baseline. A missing watermark is not the only
        # safe baseline -- a run prepared against an already-existing,
        # unchanged watermark must abort just as safely. If either baseline
        # is missing from the manifest (a run prepared by an older version
        # of this script) or either has diverged, we must fail closed rather
        # than guess.
        run_manifest = read_json(run_dir / "manifest.json") or {}
        baseline = run_manifest.get("baseline_hashes") or {}
        watermark_baseline = run_manifest.get("watermark_baseline")
        if not isinstance(watermark_baseline, dict) or "existed" not in watermark_baseline:
            raise RunError(
                "manifest predates watermark-baseline tracking (prepared by an older runner version); "
                "cannot safely determine whether a live write occurred before the crash -- refusing to "
                "guess; marker, evidence, and lock are preserved"
            )
        watermark_existed = bool(watermark_baseline.get("existed"))
        watermark_hash = watermark_baseline.get("hash")
        current_watermark_existed = ws.state.exists()
        current_watermark_hash = digest_file(ws.state) if current_watermark_existed else None
        watermark_matches = (
            current_watermark_existed == watermark_existed and current_watermark_hash == watermark_hash
        )
        if snapshot(ws) == baseline and watermark_matches:
            write_commit_marker(run_dir, run_id, "recovered", backup=None)
            (run_dir / "normalized_sessions.jsonl").unlink(missing_ok=True)
            release_lock(ws, run_id)
            return {"recovered": True, "backup": None, "reason": "aborted before any live write"}
        raise RunError(
            "commit marker predates the pre-run backup and live state no longer matches the run's "
            "baseline -- refusing to guess; marker, evidence, and lock are preserved"
        )

    # verify_backup_for_restore is entirely read-only and raises on any
    # containment, trusted-state-binding, or integrity problem *before*
    # apply_verified_restore writes or unlinks a single live path -- fail
    # closed, not partial.
    resolved_backup, verified = verify_backup_for_restore(ws, run_id, Path(marker_backup))
    apply_verified_restore(ws, verified)

    write_commit_marker(run_dir, run_id, "recovered", backup=resolved_backup)
    (run_dir / "normalized_sessions.jsonl").unlink(missing_ok=True)
    release_lock(ws, run_id)
    return {"recovered": True, "backup": str(resolved_backup)}


def cmd_recover(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    run_id = safe_run_id(args.run_id)
    run_dir = resolve_run_dir(ws, run_id)

    # Lock-ownership gate: recovery must never act while a *different* run
    # holds the extraction lock -- that run is either legitimately in
    # flight or itself mid-recovery, and touching live files/the lock out
    # from under it would corrupt its state. A malformed lock also blocks
    # recovery (use `unlock-abandoned`, or the operator-only
    # `repair-recover` if that itself is deadlocked); a missing lock, or one
    # owned by this exact run, is fine.
    lock_state, lock_meta = inspect_lock(ws)
    if lock_state == "malformed":
        raise RunError(
            "extraction lock is malformed or abandoned; run `unlock-abandoned` after confirming no "
            "extraction process is alive, then retry recover (or, if that itself is blocked by an "
            "incomplete commit, `repair-recover --confirm-no-process`)"
        )
    if lock_state == "valid" and lock_meta.get("run_id") != run_id:
        raise RunError(f"recovery refused: extraction lock is owned by a different run ({lock_meta.get('run_id')})")
    same_run_lock = lock_state == "valid" and lock_meta.get("run_id") == run_id

    # No filename-based fallback anywhere below: recovery only ever acts on
    # a run whose marker is present, well-formed, and names this exact run.
    marker = read_valid_commit_marker(run_dir, run_id)

    # The editable manifest/backup manifest are never trusted for a run with
    # no trusted control state at all -- refuse outright rather than guess.
    load_control_record(ws, run_id)

    status = marker["status"]
    if status == "completed":
        # Nothing to roll back -- restoring here would silently clobber any
        # later run's work. Only a leftover same-run lock is cleaned up.
        if same_run_lock:
            release_lock(ws, run_id)
        print(json.dumps({"recovered": False, "backup": marker.get("backup"), "reason": "already completed"}))
        return 0

    if status == "recovered":
        # Idempotent: recovering an already-recovered run must never
        # restore a second time (a later run could have started since).
        if same_run_lock:
            release_lock(ws, run_id)
        print(json.dumps({"recovered": False, "backup": marker.get("backup"), "reason": "already recovered"}))
        return 0

    result = _recover_in_progress(ws, run_dir, run_id, marker)
    print(json.dumps(result))
    return 0


def cmd_repair_recover(args: argparse.Namespace) -> int:
    """Operator-only escape hatch for the deadlock where a malformed lock
    blocks `recover` and an incomplete commit blocks `unlock-abandoned`.
    Unlike either of those, this command deliberately breaks lock ownership
    -- it must never run unattended: `--confirm-no-process` records that an
    operator has manually confirmed no extraction process for this run is
    still alive. Even with that flag, a lock that *does* identify a live
    process is never overridden. On any failure, evidence and state are left
    exactly as `recover` would leave them (nothing is deleted or marked
    resolved).
    """
    ws = Workspace.from_args(args)
    run_id = safe_run_id(args.run_id)
    if not getattr(args, "confirm_no_process", False):
        raise RunError(
            "repair-recover requires --confirm-no-process: an operator must first confirm, by hand, "
            "that no extraction process for this run is still alive"
        )
    run_dir = resolve_run_dir(ws, run_id)
    load_control_record(ws, run_id)
    marker = read_valid_commit_marker(run_dir, run_id)
    if marker["status"] != "in_progress":
        raise RunError(f"run {run_id!r} has no incomplete commit to repair (status={marker['status']!r})")

    lock_state, lock_meta = inspect_lock(ws)
    if lock_state == "valid":
        pid = (lock_meta or {}).get("pid")
        if isinstance(pid, int) and _pid_alive(pid):
            raise RunError(
                f"refusing to repair-recover: the extraction lock is held by an apparently alive "
                f"process (pid {pid}, run {lock_meta.get('run_id')!r}) -- --confirm-no-process cannot "
                "override an identifiable, alive owner"
            )

    # Atomically claim recovery ownership: drop whatever lock is present
    # (malformed, or valid but confirmed dead/unidentifiable-and-operator-
    # confirmed) and re-acquire it for the run being repaired, so the
    # verified recovery below runs under this run's own lock exactly like a
    # normal `recover` would.
    if ws.lock.exists():
        shutil.rmtree(ws.lock, ignore_errors=True)
    acquire_lock(ws, run_id)

    result = _recover_in_progress(ws, run_dir, run_id, marker)
    print(json.dumps(result))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    latest = None
    if ws.runs.is_dir():
        manifests = sorted(ws.runs.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if manifests:
            latest = read_json(manifests[0])
    lock_state, lock_meta = inspect_lock(ws)
    print(json.dumps({
        "lock": lock_meta,
        "lock_state": lock_state,
        "watermark": read_json(ws.state),
        "latest_run": latest,
        "incomplete_commits": find_incomplete_commits(ws),
    }))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    require_lock(ws, args.run_id)
    run_dir, _ = load_manifest(ws, args.run_id)
    passed, errors, changed = validate_run(ws, run_dir)
    if not passed:
        print(json.dumps({"committed": False, "stage": "validate", "errors": errors, "changed_files": changed}))
        return 2
    args.apply = True
    rc = cmd_apply(args)
    if rc != 0:
        return rc
    pruned = prune_runs(ws, args.keep)
    print(json.dumps({"committed": True, "changed_files": changed, "pruned": pruned}))
    return 0


def cmd_prune(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    print(json.dumps({"pruned": prune_runs(ws, args.keep)}))
    return 0


# --------------------------------------------------------------------------
# Deployment checking: a read-only command that compares the *deployed*
# scheduler automation, wrapper prompt, extraction prompt, and runner copy
# against what they are supposed to be -- catching scheduler drift (wrong
# cron/schedule, disabled/paused automation, wrong model) and file drift
# (edited/missing deployed prompt or runner) before it silently breaks the
# next scheduled run. Nothing here writes to anything; the scheduler
# database is opened read-only like every other database this runner reads.
# --------------------------------------------------------------------------

def cmd_check_deployment(args: argparse.Namespace) -> int:
    # This is a read-only, standalone check: it deliberately does not build a
    # full Workspace (which also needs a runs/ledger location that this
    # command has no use for) -- only the zcode home root is needed, to
    # compute the same defaults `prepare` would use for the scheduler
    # database, deployed prompt, and deployed runner.
    home = Path(getattr(args, "zcode_home", None) or (Path.home() / ".zcode")).expanduser()
    errors: list[str] = []

    tasks_db_path = Path(args.tasks_db_path).expanduser() if getattr(args, "tasks_db_path", None) else home / "v2" / "tasks-index.sqlite"
    prompt_path = Path(args.prompt_path).expanduser() if getattr(args, "prompt_path", None) else home / "self-improve" / "learning-extraction-v1.md"
    runner_path = Path(args.runner_path).expanduser() if getattr(args, "runner_path", None) else home / "self-improve" / "zcode_learning_extractor.py"

    if not tasks_db_path.exists():
        errors.append(f"scheduler database not found: {tasks_db_path}")
    else:
        try:
            con = open_ro(tasks_db_path)
        except sqlite3.Error as exc:
            con = None
            errors.append(f"scheduler database is unreadable: {exc}")
        if con is not None:
            row = None
            try:
                row = con.execute(
                    "SELECT cron_expr, prompt, model, schedule_rule, recurring, enabled, lifecycle_status "
                    "FROM automations WHERE automation_id = ?",
                    (args.automation_id,),
                ).fetchone()
            except sqlite3.Error as exc:
                errors.append(f"scheduler query failed: {exc}")
            finally:
                con.close()
            if row is None:
                errors.append(f"automation {args.automation_id!r} not found in scheduler database")
            else:
                cron_expr, prompt, model, schedule_rule_raw, recurring, enabled, lifecycle_status = row
                prompt_text = str(prompt or "")
                if cron_expr != args.cron:
                    errors.append(f"scheduler cron mismatch: expected {args.cron!r}, found {cron_expr!r}")
                try:
                    schedule_rule = json.loads(schedule_rule_raw) if schedule_rule_raw else {}
                    if not isinstance(schedule_rule, dict):
                        raise ValueError("schedule_rule is not an object")
                except (json.JSONDecodeError, ValueError):
                    schedule_rule = {}
                    errors.append("scheduler schedule_rule is not valid JSON")
                if schedule_rule.get("unit") != "daily":
                    errors.append(f"scheduler schedule unit is not daily: {schedule_rule.get('unit')!r}")
                if schedule_rule.get("interval") != args.expected_interval:
                    errors.append(
                        f"scheduler schedule interval mismatch: expected {args.expected_interval}, "
                        f"found {schedule_rule.get('interval')!r}"
                    )
                if schedule_rule.get("hour") != args.expected_hour:
                    errors.append(
                        f"scheduler schedule hour mismatch: expected {args.expected_hour}, "
                        f"found {schedule_rule.get('hour')!r}"
                    )
                if not (isinstance(model, str) and model.endswith(":" + args.model_id)):
                    errors.append(f"scheduler model mismatch: expected suffix {args.model_id!r}, found {model!r}")
                if not isinstance(recurring, int) or recurring != 1:
                    errors.append("automation is not marked recurring")
                if not isinstance(enabled, int) or enabled != 1:
                    errors.append("automation is not enabled")
                if lifecycle_status != "active":
                    errors.append(f"automation lifecycle_status is not active: {lifecycle_status!r}")
                if f"--automation-id {args.automation_id}" not in prompt_text:
                    errors.append("wrapper prompt is missing its --automation-id flag")
                if f"--model-id {args.model_id}" not in prompt_text:
                    errors.append("wrapper prompt is missing its --model-id flag")
                if DEPLOYED_PROMPT_ABS_PATH not in prompt_text:
                    errors.append("wrapper prompt is missing the deployed extraction-prompt path")
                if DEPLOYED_RUNNER_ABS_PATH not in prompt_text:
                    errors.append("wrapper prompt is missing the deployed runner path")
                if "without AGENTS.md injection" not in prompt_text:
                    errors.append("wrapper prompt lost its no-AGENTS.md-injection declaration")
                if "file tools are explicitly allowed inside the printed run directory" not in prompt_text:
                    errors.append("wrapper prompt is missing the explicit run-directory file-tool permission")

    deployed_prompt_sha256 = ""
    if not prompt_path.exists():
        errors.append(f"deployed extraction prompt not found: {prompt_path}")
    else:
        deployed_prompt_sha256 = digest_file(prompt_path)
        prompt_body = prompt_path.read_text(errors="replace")
        if "injectAgentsMd: false" not in prompt_body:
            errors.append("deployed extraction prompt lost its injectAgentsMd: false declaration")
        expected_prompt_sha256 = getattr(args, "expected_prompt_sha256", None)
        if expected_prompt_sha256 and deployed_prompt_sha256 != expected_prompt_sha256:
            errors.append(
                f"deployed extraction prompt hash mismatch: expected {expected_prompt_sha256}, "
                f"found {deployed_prompt_sha256}"
            )

    deployed_runner_sha256 = ""
    if not runner_path.exists():
        errors.append(f"deployed runner not found: {runner_path}")
    else:
        deployed_runner_sha256 = digest_file(runner_path)
        own_sha256 = digest_file(Path(__file__).resolve())
        if deployed_runner_sha256 != own_sha256:
            errors.append("deployed runner hash does not match this runner's own source (drift or tampering)")

    ok = not errors
    result = {
        "ok": ok,
        "errors": errors,
        "deployed_prompt_path": str(prompt_path),
        "deployed_prompt_sha256": deployed_prompt_sha256,
        "deployed_runner_path": str(runner_path),
        "deployed_runner_sha256": deployed_runner_sha256,
    }
    print(json.dumps(result))
    return 0 if ok else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zcode-home", default=str(Path.home() / ".zcode"))
    p.add_argument("--runs-home")
    p.add_argument("--ledger")
    sub = p.add_subparsers(dest="command", required=True)

    prep = sub.add_parser("prepare")
    prep.add_argument("--db-path")
    prep.add_argument("--tasks-db-path")
    prep.add_argument("--scope-root", action="append")
    prep.add_argument("--self-session-id")
    prep.add_argument("--bootstrap-hours", type=int, default=DEFAULT_BOOTSTRAP_HOURS)
    prep.add_argument("--automation-id")
    prep.add_argument("--model-id")
    prep.add_argument("--prompt-file")
    prep.add_argument("--run-id")
    prep.set_defaults(func=cmd_prepare)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    for name, func in (("validate", cmd_validate), ("recover", cmd_recover)):
        item = sub.add_parser(name)
        item.add_argument("--run-id", required=True)
        item.set_defaults(func=func)

    apply = sub.add_parser("apply")
    apply.add_argument("--run-id", required=True)
    apply.add_argument("--apply", action="store_true")
    apply.set_defaults(func=cmd_apply)

    commit = sub.add_parser("commit")
    commit.add_argument("--run-id", required=True)
    commit.add_argument("--keep", type=int, default=5)
    commit.set_defaults(func=cmd_commit)

    prune = sub.add_parser("prune")
    prune.add_argument("--keep", type=int, default=5)
    prune.set_defaults(func=cmd_prune)

    unlock = sub.add_parser("unlock-abandoned")
    unlock.add_argument("--run-id")
    unlock.set_defaults(func=cmd_unlock_abandoned)

    repair = sub.add_parser(
        "repair-recover",
        description=(
            "Operator-only escape hatch for the deadlock where a malformed lock blocks `recover` "
            "and an incomplete commit blocks `unlock-abandoned`. Requires manual confirmation via "
            "--confirm-no-process; never run this unattended."
        ),
    )
    repair.add_argument("--run-id", required=True)
    repair.add_argument("--confirm-no-process", dest="confirm_no_process", action="store_true")
    repair.set_defaults(func=cmd_repair_recover)

    checkdep = sub.add_parser("check-deployment", description="Read-only check of the deployed scheduler automation, wrapper prompt, extraction prompt, and runner copy.")
    checkdep.add_argument("--tasks-db-path")
    checkdep.add_argument("--automation-id", required=True)
    checkdep.add_argument("--model-id", required=True)
    checkdep.add_argument("--cron", required=True)
    checkdep.add_argument("--prompt-path")
    checkdep.add_argument("--runner-path")
    checkdep.add_argument("--expected-prompt-sha256")
    checkdep.add_argument("--expected-interval", type=int, default=2)
    checkdep.add_argument("--expected-hour", type=int, default=20)
    checkdep.set_defaults(func=cmd_check_deployment)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except RunError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
