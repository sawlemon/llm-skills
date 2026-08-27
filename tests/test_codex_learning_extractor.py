from __future__ import annotations

import contextlib
import io
import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import importlib.util
import sys

_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "hill-climb" / "scripts" / "codex_learning_extractor.py"
_SPEC = importlib.util.spec_from_file_location("codex_learning_extractor", _SCRIPT)
ext = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ext
_SPEC.loader.exec_module(ext)


def write_session(root: Path, name: str, cwd: str, source: str = "user", sid: str | None = None) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "type": "session_meta",
        "payload": {"id": sid or name, "cwd": cwd, "thread_source": source, "timestamp": time.time()},
    }
    user = {
        "type": "response_item",
        "timestamp": time.time(),
        "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Always verify."}]},
    }
    path.write_text(json.dumps(meta) + "\n" + json.dumps(user) + "\n")
    os.utime(path, (time.time(), time.time()))
    return path


def memory(ws: ext.Workspace) -> None:
    ws.home.mkdir(parents=True, exist_ok=True)
    (ws.home / "AGENTS.md").write_text("# Map\n- Rules -> docs/rules.md.\n<!-- nodeterm:get-linked-context:start -->\n" + "injected\n" * 150)
    (ws.memory / "rules.md").parent.mkdir(parents=True, exist_ok=True)
    (ws.memory / "rules.md").write_text("# Rules\n")
    (ws.memory / "index.md").write_text("# Index\n- rules.md\n")
    ws.ledger.write_text("## 2026-08-01 run\n- [NO-OP] none\n")


def prepare(root: Path, codex_home: Path, sessions_root: Path, **kwargs) -> dict:
    out = io.StringIO()
    prompt = codex_home / "prompt.md"
    prompt.write_text("runner")
    args = SimpleNamespace(
        codex_home=str(codex_home),
        runs_home=str(codex_home / "runs"),
        ledger=str(codex_home / "ledger.md"),
        command="prepare",
        scope_root=kwargs.get("scope_root", [str(root)]),
        sessions_root=[str(sessions_root)],
        automation_id="hillclimb-codex",
        model_id="test-model",
        prompt_file=str(prompt),
        run_id=kwargs.get("run_id"),
    )
    with contextlib.redirect_stdout(out):
        ext.cmd_prepare(args)
    return json.loads(out.getvalue())


class ExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.codex_home = self.root / "codex"
        self.sessions = self.root / "sessions"
        self.ws = ext.Workspace(self.codex_home, self.codex_home / "runs", self.codex_home / "ledger.md")
        memory(self.ws)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_prepare_filters_and_deduplicates(self) -> None:
        first = write_session(self.sessions, "a.jsonl", str(self.root / "personal"), sid="same")
        second = write_session(self.sessions, "b.jsonl", str(self.root / "personal"), sid="same")
        second.stat().st_mtime
        os.utime(second, (time.time() + 2, time.time() + 2))
        write_session(self.sessions, "sub.jsonl", str(self.root / "personal"), source="subagent")
        write_session(self.sessions, "auto.jsonl", str(self.root / "personal"), source="automation")
        write_session(self.sessions, "outside.jsonl", "/tmp/not-scope")
        result = prepare(self.root, self.codex_home, self.sessions)
        self.assertEqual(result["session_count"], 1)
        manifest = json.loads((self.codex_home / "runs" / result["run_id"] / "manifest.json").read_text())
        self.assertEqual(manifest["sessions"][0]["id"], "same")

    def test_prepare_without_scope_includes_all(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"), sid="a")
        write_session(self.sessions, "b.jsonl", "/tmp/anywhere", sid="b")
        write_session(self.sessions, "sub.jsonl", "/tmp/anywhere", source="subagent")
        result = prepare(self.root, self.codex_home, self.sessions, scope_root=[])
        self.assertEqual(result["session_count"], 2)

    def test_validate_and_apply_success(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"))
        result = prepare(self.root, self.codex_home, self.sessions)
        run_dir = self.codex_home / "runs" / result["run_id"]
        staging = run_dir / "staging"
        (staging / "docs" / "rules.md").write_text("# Rules\n- Always verify.\n")
        (staging / "AGENTS.extraction-log.md").write_text("## 2026-08-27 run\n- [WROTE-DOC] Always verify.\n")
        normalized = run_dir / "normalized_sessions.jsonl"
        event = json.loads(normalized.read_text().splitlines()[0])["events"][0]
        decision = {
            "claim": "Always verify.",
            "kind": "behavioral_rule",
            "scope": "global",
            "confidence": "confirmed",
            "confirmation_basis": "explicit_user_rule",
            "disposition": "WROTE_DOC",
            "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_timestamp": event["event_timestamp"], "event_sha256": event["event_sha256"]}],
            "reason": "user correction",
        }
        (run_dir / "decisions.jsonl").write_text(json.dumps(decision) + "\n")
        out = io.StringIO()
        args = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="validate", run_id=result["run_id"])
        with contextlib.redirect_stdout(out):
            self.assertEqual(ext.cmd_validate(args), 0)
        self.assertTrue(json.loads((run_dir / "validation.json").read_text())["passed"])
        args = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="apply", run_id=result["run_id"], apply=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ext.cmd_apply(args), 0)
        self.assertIn("Always verify.", (self.codex_home / "docs" / "rules.md").read_text())
        state = json.loads(self.ws.state.read_text())
        self.assertEqual(state["run_id"], result["run_id"])

    def test_iso_timestamp_is_parsed(self) -> None:
        path = self.sessions / "iso.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"id": "iso", "cwd": str(self.root / "personal"), "thread_source": "user"}
        path.write_text(json.dumps({"type": "session_meta", "payload": meta}) + "\n" + json.dumps({
            "type": "event_msg", "timestamp": "2026-08-27T10:00:00Z",
            "payload": {"type": "user_message", "message": "Always verify."},
        }) + "\n")
        os.utime(path, (time.time(), time.time()))
        event = ext.normalize_session(path, meta, 0, time.time())["events"][0]
        self.assertIsNotNone(event["event_epoch"])
        self.assertTrue(event["is_new"])

    def test_new_file_applies_and_staged_deletion_is_rejected(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"))
        result = prepare(self.root, self.codex_home, self.sessions)
        run_dir = self.codex_home / "runs" / result["run_id"]
        staging = run_dir / "staging"
        (staging / "docs" / "new.md").write_text("# New\n")
        event = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])["events"][0]
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "new", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/new.md",
            "evidence": [{"event_sha256": event["event_sha256"]}], "reason": "test",
        }) + "\n")
        (staging / "AGENTS.extraction-log.md").write_text("## 2026-08-27 run\n- [WROTE-DOC] new\n")
        args = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), run_id=result["run_id"])
        self.assertEqual(ext.cmd_validate(args), 0)
        apply_args = SimpleNamespace(**vars(args), apply=True)
        self.assertEqual(ext.cmd_apply(apply_args), 0)
        self.assertTrue((self.codex_home / "docs" / "new.md").exists())

    def test_validate_rejects_bad_evidence_and_project_path(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"))
        result = prepare(self.root, self.codex_home, self.sessions)
        run_dir = self.codex_home / "runs" / result["run_id"]
        staging = run_dir / "staging"
        (staging / "docs" / "rules.md").write_text("changed")
        (staging / "AGENTS.extraction-log.md").write_text("## 2026-08-27 run\n- [WROTE-DOC] x\n")
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "project", "confidence": "confirmed",
            "confirmation_basis": "explicit_user_rule", "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"event_sha256": "missing"}], "reason": "bad",
        }) + "\n")
        args = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="validate", run_id=result["run_id"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ext.cmd_validate(args), 1)
        errors = json.loads((run_dir / "validation.json").read_text())["errors"]
        self.assertTrue(any("missing evidence hash" in e for e in errors))
        self.assertTrue(any("non-project destination" in e for e in errors))

    def test_validate_rejects_secret(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"))
        result = prepare(self.root, self.codex_home, self.sessions)
        run_dir = self.codex_home / "runs" / result["run_id"]
        (run_dir / "staging" / "docs" / "rules.md").write_text("api_key = abcdefgh123456\n")
        args = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="validate", run_id=result["run_id"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ext.cmd_validate(args), 1)
        self.assertIn("secret-like value", " ".join(json.loads((run_dir / "validation.json").read_text())["errors"]))

    def test_recover_restores_backup(self) -> None:
        write_session(self.sessions, "a.jsonl", str(self.root / "personal"))
        result = prepare(self.root, self.codex_home, self.sessions)
        run_dir = self.codex_home / "runs" / result["run_id"]
        staging = run_dir / "staging"
        (staging / "docs" / "rules.md").write_text("changed")
        (staging / "AGENTS.extraction-log.md").write_text("## 2026-08-27 run\n- [WROTE-DOC] x\n")
        normalized = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])["events"][0]
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "confirmation_basis": "explicit_user_rule", "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"event_sha256": normalized["event_sha256"]}], "reason": "ok",
        }) + "\n")
        vargs = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="validate", run_id=result["run_id"])
        with contextlib.redirect_stdout(io.StringIO()):
            ext.cmd_validate(vargs)
        aargs = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="apply", run_id=result["run_id"], apply=True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ext.cmd_apply(aargs), 0)
        (self.codex_home / "docs" / "rules.md").write_text("corrupt")
        rargs = SimpleNamespace(codex_home=str(self.codex_home), runs_home=str(self.codex_home / "runs"), ledger=str(self.codex_home / "ledger.md"), command="recover", run_id=result["run_id"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ext.cmd_recover(rargs), 0)
        self.assertEqual((self.codex_home / "docs" / "rules.md").read_text(), "# Rules\n")
        self.assertFalse(self.ws.state.exists())


if __name__ == "__main__":
    unittest.main()
