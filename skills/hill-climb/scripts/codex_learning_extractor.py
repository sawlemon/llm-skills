#!/usr/bin/env python3
"""Prepare, validate, and apply Codex learning-extraction runs safely."""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

DISPOSITIONS = {"WROTE_MAP", "WROTE_DOC", "REFINED", "SUPERSEDED", "SKIPPED_DUP", "PROVISIONAL", "REJECTED"}
WRAPPER_PREFIXES = ("<app-context>", "<environment_context>", "<user_instructions>", "<heartbeat>", "# AGENTS.md instructions")
SECRET_RE = re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|token|secret|password|credential)\s*[:=]\s*[\"']?[^\"'\s]{8,}")
POINTER_RE = re.compile(r"(?:^|\s)((?:\./)?docs/[A-Za-z0-9_./-]+)(?:\s|$|\))")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

class RunError(RuntimeError):
    pass

class Workspace:
    def __init__(self, home: Path, runs: Path, ledger: Path):
        self.home, self.runs, self.ledger = home, runs, ledger
    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Workspace":
        home = Path(args.codex_home).expanduser().resolve()
        runs = Path(args.runs_home).expanduser().resolve() if args.runs_home else home / "extraction-runs"
        ledger = Path(args.ledger).expanduser().resolve() if args.ledger else home / "AGENTS.extraction-log.md"
        return cls(home, runs, ledger)
    @property
    def state(self) -> Path: return self.home / "AGENTS.extraction-state.json"
    @property
    def lock(self) -> Path: return self.home / "AGENTS.extraction.lock"
    @property
    def memory(self) -> Path: return self.home / "docs"

def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""): h.update(chunk)
    return h.hexdigest()

def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data); fh.flush(); os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise

def atomic_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())

def read_json(path: Path) -> dict[str, Any] | None:
    try: value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError): return None
    return value if isinstance(value, dict) else None

def parse_epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool): return float(value)
    if not isinstance(value, str) or not value.strip(): return None
    try: return float(value)
    except ValueError: pass
    try: parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError: return None
    if parsed.tzinfo is None: parsed = parsed.astimezone()
    return parsed.timestamp()

def iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat()

def ledger_lower_bound(path: Path) -> float | None:
    try: dates = re.findall(r"^## (\d{4}-\d{2}-\d{2}) run\b", path.read_text(), re.M)
    except OSError: return None
    if not dates: return None
    latest = max(dt.date.fromisoformat(item) for item in dates)
    return dt.datetime.combine(latest, dt.time()).astimezone().timestamp()

def safe_run_id(value: str) -> str:
    if not RUN_ID_RE.fullmatch(value): raise RunError("invalid run_id")
    return value

def under(path: Path, root: Path) -> bool:
    try: path.resolve().relative_to(root.resolve()); return True
    except ValueError: return False

def acquire_lock(ws: Workspace, run_id: str) -> None:
    ws.home.mkdir(parents=True, exist_ok=True)
    try: fd = os.open(ws.lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        current = read_json(ws.lock)
        raise RunError(f"another extraction run owns the lock ({current.get('run_id') if current else 'unknown'})") from exc
    with os.fdopen(fd, "w") as fh: json.dump({"run_id": run_id, "pid": os.getpid(), "created_at": time.time()}, fh)

def require_lock(ws: Workspace, run_id: str) -> None:
    current = read_json(ws.lock)
    if not current or current.get("run_id") != run_id: raise RunError("run does not own extraction lock")

def release_lock(ws: Workspace, run_id: str) -> None:
    current = read_json(ws.lock)
    if current and current.get("run_id") == run_id: ws.lock.unlink(missing_ok=True)

def parse_meta(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(errors="replace") as fh: obj = json.loads(fh.readline())
    except (OSError, json.JSONDecodeError): return None
    if obj.get("type") != "session_meta": return None
    payload = obj.get("payload") or {}
    if not isinstance(payload, dict): return None
    payload = dict(payload)
    if isinstance(payload.get("cwd"), dict): payload["cwd"] = payload["cwd"].get("path")
    return payload

def redact(text: str) -> str:
    return SECRET_RE.sub(lambda m: m.group(0).split("=", 1)[0].split(":", 1)[0] + "=<REDACTED>", text)

def message_text(payload: dict[str, Any]) -> tuple[str, str]:
    role = str(payload.get("role", ""))
    content = payload.get("content", [])
    text = "".join(block.get("text", "") for block in content if isinstance(block, dict)) if isinstance(content, list) else str(payload.get("message", ""))
    return role, text.strip()

def normalize_session(path: Path, meta: dict[str, Any], lower: float, upper: float) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, float | None]] = set()
    try:
        with path.open(errors="replace") as fh:
            for line_no, line in enumerate(fh, 1):
                try: obj = json.loads(line)
                except json.JSONDecodeError: continue
                typ, payload = obj.get("type"), obj.get("payload") or {}
                if typ == "response_item" and payload.get("type") == "message":
                    role, text = message_text(payload)
                elif typ == "event_msg" and payload.get("type") in {"user_message", "agent_message"}:
                    role, text = ("user" if payload["type"] == "user_message" else "assistant"), str(payload.get("message", "")).strip()
                else: continue
                if not text or role in {"developer", "system"} or text.startswith(WRAPPER_PREFIXES): continue
                epoch = parse_epoch(obj.get("timestamp") or payload.get("timestamp"))
                clean = redact(text)
                key = (role, digest_bytes(clean.encode()), epoch)
                if key in seen: continue
                seen.add(key)
                events.append({
                    "session_id": meta.get("id"), "path": str(path), "line": line_no,
                    "event_timestamp": iso(epoch) if epoch is not None else "",
                    "event_epoch": epoch,
                    "event_sha256": digest_bytes(f"{role}\0{epoch}\0{text}".encode()),
                    "role": role, "text": clean,
                    "is_new": epoch is None or lower < epoch <= upper,
                })
    except OSError:
        pass
    return {"id": meta.get("id"), "cwd": meta.get("cwd"), "mtime": path.stat().st_mtime, "source_path": str(path), "events": events}

def discover_sessions(session_roots: list[Path], lower: float, upper: float, scope_roots: list[Path], automation_id: str) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    scopes = [root.resolve() for root in scope_roots]
    for root in session_roots:
        if not root.is_dir(): continue
        for path in root.rglob("*.jsonl"):
            try: mtime = path.stat().st_mtime
            except OSError: continue
            if not lower < mtime <= upper: continue
            meta = parse_meta(path)
            if not meta or meta.get("thread_source") in {"subagent", "automation"}: continue
            if scopes:
                cwd = Path(str(meta.get("cwd") or "")).expanduser().resolve()
                if not any(under(cwd, scope) for scope in scopes): continue
            try:
                with path.open("rb") as fh: head = fh.read(20000).decode(errors="ignore")
            except OSError: continue
            if automation_id in head: continue
            session = normalize_session(path, meta, lower, upper)
            sid = str(session.get("id") or path)
            if sid not in selected or session["mtime"] > selected[sid]["mtime"]: selected[sid] = session
    return sorted(selected.values(), key=lambda item: item["mtime"], reverse=True)

def targets(ws: Workspace) -> dict[str, Path]:
    result = {"AGENTS.md": ws.home / "AGENTS.md", "AGENTS.extraction-log.md": ws.ledger}
    if ws.memory.is_dir():
        for path in ws.memory.rglob("*"):
            if path.is_file() and not path.is_symlink(): result[str(path.relative_to(ws.home))] = path
    return result

def snapshot(ws: Workspace, destination: Path | None = None) -> dict[str, str]:
    values: dict[str, str] = {}
    for rel, source in targets(ws).items():
        if not source.exists(): continue
        values[rel] = digest_file(source)
        if destination is not None:
            dest = destination / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest, follow_symlinks=False)
    return values

def load_manifest(ws: Workspace, run_id: str) -> tuple[Path, dict[str, Any]]:
    run_id = safe_run_id(run_id)
    run_dir = (ws.runs / run_id).resolve()
    if not under(run_dir, ws.runs): raise RunError("run directory escapes runs root")
    manifest = read_json(run_dir / "manifest.json")
    if not manifest: raise RunError("manifest is missing or invalid")
    return run_dir, manifest

def cmd_prepare(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    run_id = safe_run_id(args.run_id or dt.datetime.now().astimezone().strftime("%Y%m%dT%H%M%S") + "-" + os.urandom(4).hex())
    acquire_lock(ws, run_id)
    try:
        state = read_json(ws.state) or {}
        lower = parse_epoch(state.get("last_successful_run_epoch"))
        started, bootstrap = time.time(), False
        if lower is None or lower > started:
            lower = ledger_lower_bound(ws.ledger)
            if lower is None or lower > started: lower, bootstrap = started - 7 * 86400, True
        prompt = Path(args.prompt_file).expanduser()
        session_roots = [Path(item).expanduser().resolve() for item in (args.sessions_root or [str(ws.home / "sessions"), str(ws.home / "archived_sessions")])]
        sessions = discover_sessions(session_roots, lower, started, [Path(item).expanduser().resolve() for item in args.scope_root], args.automation_id)
        run_dir = ws.runs / run_id
        run_dir.mkdir(parents=True)
        staging = run_dir / "staging"
        staging.mkdir()
        evidence = run_dir / "normalized_sessions.jsonl"
        with evidence.open("w", encoding="utf-8") as fh:
            for session in sessions: fh.write(json.dumps(session, sort_keys=True) + "\n")
        os.chmod(evidence, 0o600)
        atomic_json(run_dir / "manifest.json", {
            "version": 1, "run_id": run_id, "automation_id": args.automation_id,
            "model_id": args.model_id, "prompt_sha256": digest_file(prompt) if prompt.exists() else "",
            "lower_bound": lower, "upper_bound": started, "bootstrap": bootstrap,
            "session_count": len(sessions),
            "sessions": [{key: session[key] for key in ("id", "cwd", "mtime", "source_path")} for session in sessions],
            "baseline_hashes": snapshot(ws, staging),
        })
        print(json.dumps({"run_id": run_id, "run_dir": str(run_dir), "session_count": len(sessions), "lower_bound": lower, "upper_bound": started, "bootstrap": bootstrap}))
        return 0
    except Exception:
        release_lock(ws, run_id)
        raise

def read_decisions(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "decisions.jsonl"
    if not path.exists(): return []
    records: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict): raise ValueError("decision is not an object")
                records.append(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RunError(f"invalid decisions.jsonl: {exc}") from exc
    return records

def staged_files(staging: Path) -> set[str]:
    files: set[str] = set()
    if not staging.exists(): return files
    for path in staging.rglob("*"):
        if path.is_symlink(): raise RunError(f"staging contains symlink: {path.relative_to(staging)}")
        if path.is_file(): files.add(str(path.relative_to(staging)))
    return files

def validate_run(ws: Workspace, run_dir: Path) -> tuple[bool, list[str], list[str]]:
    manifest = read_json(run_dir / "manifest.json")
    if not manifest: return False, ["manifest is missing or invalid"], []
    errors: list[str] = []
    staging = run_dir / "staging"
    baseline: dict[str, str] = manifest.get("baseline_hashes") or {}
    if snapshot(ws) != baseline: errors.append("live memory changed after prepare")
    staged = staged_files(staging)
    baseline_files = set(baseline)
    additions, deletions = staged - baseline_files, baseline_files - staged
    if deletions: errors.append("staged deletions are not allowed: " + ", ".join(sorted(deletions)))
    for rel in additions:
        if not rel.startswith("docs/") or Path(rel).is_absolute() or ".." in Path(rel).parts:
            errors.append(f"new file outside docs/: {rel}")
    changed = sorted(rel for rel in staged if rel not in baseline or digest_file(staging / rel) != baseline[rel])
    decisions = read_decisions(run_dir)
    evidence_hashes: set[str] = set()
    try:
        for line in (run_dir / "normalized_sessions.jsonl").read_text().splitlines():
            session = json.loads(line)
            evidence_hashes.update(event["event_sha256"] for event in session.get("events", []))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        errors.append(f"invalid normalized evidence: {exc}")
    decision_destinations: set[str] = set()
    for record in decisions:
        for key in ("claim", "kind", "scope", "confidence", "disposition", "evidence"):
            if key not in record: errors.append(f"decision missing {key}")
        if record.get("disposition") not in DISPOSITIONS: errors.append(f"invalid disposition: {record.get('disposition')}")
        if record.get("kind") not in {"behavioral_rule", "technical_fact"}: errors.append(f"invalid kind: {record.get('kind')}")
        if record.get("scope") not in {"global", "project"}: errors.append(f"invalid scope: {record.get('scope')}")
        if record.get("confidence") not in {"confirmed", "provisional"}: errors.append(f"invalid confidence: {record.get('confidence')}")
        dest = record.get("destination")
        if dest is not None:
            if not isinstance(dest, str) or Path(dest).is_absolute() or ".." in Path(dest).parts or dest not in staged:
                errors.append(f"invalid decision destination: {dest}")
            else: decision_destinations.add(dest)
        if record.get("scope") == "project" and dest and not dest.startswith("docs/projects/"):
            errors.append(f"project fact has non-project destination: {dest}")
        if record.get("disposition") in {"WROTE_MAP", "WROTE_DOC", "REFINED", "SUPERSEDED"} and not dest:
            errors.append("write disposition lacks destination")
        for item in record.get("evidence") or []:
            if not isinstance(item, dict) or item.get("event_sha256") not in evidence_hashes:
                errors.append(f"missing evidence hash: {item.get('event_sha256') if isinstance(item, dict) else item}")
        if SECRET_RE.search(str(record.get("claim", ""))) or SECRET_RE.search(str(record.get("reason", ""))):
            errors.append("secret-like value in decision metadata")
    changed_memory = set(changed) - {"AGENTS.extraction-log.md"}
    if changed_memory and "AGENTS.extraction-log.md" not in changed:
        errors.append("memory changes must include an updated extraction ledger")
    if changed_memory and not decision_destinations.intersection(changed_memory):
        errors.append("every memory change must be referenced by a write decision")
    for rel in changed:
        if SECRET_RE.search((staging / rel).read_text(errors="replace")):
            errors.append(f"secret-like value in changed file: {rel}")
    map_path = staging / "AGENTS.md"
    if map_path.exists():
        map_text = map_path.read_text()
        editable_map = map_text.split("<!-- nodeterm:", 1)[0]
        if len(editable_map.splitlines()) > 100: errors.append("AGENTS.md exceeds the 100-line limit")
        pointers = {match.rstrip(".,;:").lstrip("./") for match in POINTER_RE.findall(map_text)}
        for pointer in pointers:
            if not (staging / pointer).exists(): errors.append(f"broken map pointer: {pointer}")
    diff_parts: list[str] = []
    for rel in sorted(set(baseline) | staged):
        old, new = ws.home / rel, staging / rel
        old_text = old.read_text(errors="replace") if old.exists() else ""
        new_text = new.read_text(errors="replace") if new.exists() else ""
        if old_text != new_text:
            diff_parts.append("".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), fromfile=f"a/{rel}", tofile=f"b/{rel}")))
    (run_dir / "diff.patch").write_text("\n".join(diff_parts))
    report = ["# Extraction run report", "", f"- run_id: {manifest['run_id']}", f"- sessions: {manifest.get('session_count', 0)}", f"- changed files: {', '.join(changed) or 'none'}", "", "## Dispositions", ""]
    report.extend(f"- {item.get('disposition')}: {item.get('claim')} -> {item.get('destination') or 'n/a'}" for item in decisions)
    (run_dir / "report.md").write_text("\n".join(report) + "\n")
    passed = not errors
    atomic_json(run_dir / "validation.json", {"passed": passed, "errors": errors, "changed_files": changed})
    return passed, errors, changed

def cmd_validate(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    require_lock(ws, args.run_id)
    run_dir, _ = load_manifest(ws, args.run_id)
    passed, errors, changed = validate_run(ws, run_dir)
    print(json.dumps({"passed": passed, "errors": errors, "changed_files": changed}))
    return 0 if passed else 1

def backup_live(ws: Workspace, manifest: dict[str, Any], staged: set[str]) -> Path:
    backup = ws.home / f"backup-{dt.datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')}-{manifest['run_id']}"
    backup.mkdir()
    presence: dict[str, bool] = {}
    for rel in set(manifest.get("baseline_hashes", {})) | staged | {"AGENTS.extraction-state.json"}:
        source = ws.state if rel == "AGENTS.extraction-state.json" else targets(ws).get(rel, ws.home / rel)
        presence[rel] = source.exists()
        if source.exists():
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest, follow_symlinks=False)
    atomic_json(backup / "presence.json", presence)
    return backup

def restore_backup(ws: Workspace, backup: Path) -> None:
    presence = read_json(backup / "presence.json") or {}
    for rel, existed in presence.items():
        target = ws.state if rel == "AGENTS.extraction-state.json" else targets(ws).get(rel, ws.home / rel)
        source = backup / rel
        if existed and source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target, follow_symlinks=False)
        elif not existed:
            target.unlink(missing_ok=True)

def cmd_apply(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    if not args.apply: raise RunError("refusing to apply without --apply")
    require_lock(ws, args.run_id)
    run_dir, manifest = load_manifest(ws, args.run_id)
    validation = read_json(run_dir / "validation.json")
    if not validation or not validation.get("passed"): raise RunError("run has not passed validation")
    if snapshot(ws) != manifest.get("baseline_hashes", {}): raise RunError("live memory changed after validation")
    staged = staged_files(run_dir / "staging")
    backup = backup_live(ws, manifest, staged)
    try:
        for rel in sorted(staged):
            target = targets(ws).get(rel, ws.home / rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(target, (run_dir / "staging" / rel).read_bytes())
        state = {
            "version": 1, "run_id": args.run_id,
            "last_successful_run_epoch": manifest["upper_bound"],
            "last_successful_run_iso": iso(manifest["upper_bound"]),
            "completed_at_iso": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model_id": manifest.get("model_id", ""), "prompt_sha256": manifest.get("prompt_sha256", ""),
        }
        atomic_json(ws.state, state)
    except Exception:
        restore_backup(ws, backup)
        raise
    release_lock(ws, args.run_id)
    (run_dir / "normalized_sessions.jsonl").unlink(missing_ok=True)
    print(json.dumps({"applied": True, "backup": str(backup), "checkpoint": state}))
    return 0

def cmd_recover(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    safe_run_id(args.run_id)
    backups = sorted(ws.home.glob(f"backup-*-{args.run_id}"), key=lambda path: path.stat().st_mtime)
    if backups: restore_backup(ws, backups[-1])
    run_dir = ws.runs / args.run_id
    if run_dir.exists(): (run_dir / "normalized_sessions.jsonl").unlink(missing_ok=True)
    release_lock(ws, args.run_id)
    print(json.dumps({"recovered": bool(backups), "backup": str(backups[-1]) if backups else None}))
    return 0

def cmd_status(args: argparse.Namespace) -> int:
    ws = Workspace.from_args(args)
    latest = None
    if ws.runs.is_dir():
        manifests = sorted(ws.runs.glob("*/manifest.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        if manifests: latest = read_json(manifests[0])
    print(json.dumps({"lock": read_json(ws.lock), "state": read_json(ws.state), "latest_run": latest}))
    return 0

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--codex-home", default=str(Path.home() / ".codex"))
    p.add_argument("--runs-home")
    p.add_argument("--ledger")
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--sessions-root", action="append")
    prep.add_argument("--scope-root", action="append", default=[])
    prep.add_argument("--automation-id", required=True)
    prep.add_argument("--model-id", required=True)
    prep.add_argument("--prompt-file", required=True)
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
