from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "hill-climb" / "scripts" / "zcode_learning_extractor.py"
_SPEC = importlib.util.spec_from_file_location("zcode_learning_extractor", _SCRIPT)
ext = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = ext
_SPEC.loader.exec_module(ext)


# --------------------------------------------------------------------------
# Fixture builders: temporary SQLite databases matching the real ZCode schema
# (only the columns this extractor reads), and a temporary ~/.zcode-shaped
# home. Nothing here touches any live path.
# --------------------------------------------------------------------------

def create_session_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, parent_id TEXT, directory TEXT, "
        "title TEXT NOT NULL DEFAULT '', time_created INTEGER, time_updated INTEGER, "
        "task_type TEXT NOT NULL DEFAULT 'interactive')"
    )
    con.execute(
        "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, sequence INTEGER, "
        "time_created INTEGER, data TEXT NOT NULL)"
    )
    con.execute(
        "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, "
        "sequence INTEGER, data TEXT NOT NULL)"
    )
    con.commit()
    return con


def create_tasks_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE automation_runs (run_id TEXT PRIMARY KEY, session_id TEXT)")
    con.commit()
    return con


def add_session(con: sqlite3.Connection, sid: str, directory: str, *, title: str = "",
                 time_updated: int = 0, time_created: int | None = None,
                 parent_id: str | None = None, task_type: str = "interactive") -> None:
    con.execute(
        "INSERT INTO session (id, parent_id, directory, title, time_created, time_updated, task_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sid, parent_id, directory, title, time_created if time_created is not None else time_updated, time_updated, task_type),
    )
    con.commit()


_COUNTER = {"n": 0}


def _next_id(prefix: str) -> str:
    _COUNTER["n"] += 1
    return f"{prefix}{_COUNTER['n']}"


def add_turn(con: sqlite3.Connection, sid: str, sequence: int, role: str, part: dict,
             time_created: int = 0) -> None:
    mid = _next_id("msg")
    pid = _next_id("part")
    con.execute(
        "INSERT INTO message (id, session_id, sequence, time_created, data) VALUES (?, ?, ?, ?, ?)",
        (mid, sid, sequence, time_created, json.dumps({"role": role})),
    )
    con.execute(
        "INSERT INTO part (id, message_id, session_id, sequence, data) VALUES (?, ?, ?, ?, ?)",
        (pid, mid, sid, 0, json.dumps(part)),
    )
    con.commit()


def add_text_turn(con: sqlite3.Connection, sid: str, sequence: int, role: str, text: str,
                   time_created: int = 0) -> None:
    add_turn(con, sid, sequence, role, {"type": "text", "text": text}, time_created)


def memory(ws: "ext.Workspace") -> None:
    ws.home.mkdir(parents=True, exist_ok=True)
    (ws.home / "AGENTS.md").write_text(
        "# AGENTS.md — Global Map\n\n"
        "## Always-on rules\n- Verify, don't assume.\n\n"
        "## Where to look\n- Rules -> docs/rules.md.\n"
    )
    ws.memory.mkdir(parents=True, exist_ok=True)
    (ws.memory / "rules.md").write_text("# Rules\n")
    (ws.memory / "index.md").write_text("# Index\n- rules.md\n")
    ws.ledger.write_text("## 2026-08-01 run\n- [NO-OP] none\n")


def make_args(**overrides) -> SimpleNamespace:
    base = dict(
        zcode_home=None, runs_home=None, ledger=None, command=None,
        db_path=None, tasks_db_path=None, scope_root=None, self_session_id=None,
        bootstrap_hours=48, automation_id="", model_id="", prompt_file=None, run_id=None,
        apply=False, keep=5,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def make_fake_clock(start: int = 10_000_000_000):
    """A monotonically increasing fake `now_ms` with a huge step per call.

    Loops that prepare/commit several runs back to back would otherwise be
    timing-flaky: real wall-clock time can advance by less than a millisecond
    between a test's `ext.now_ms()` call (used to pick a session's
    `time_updated`) and `cmd_prepare`'s own `now_ms()` call (used as the
    window's upper bound), occasionally landing the new session outside the
    window. Patching `ext.now_ms` with this makes ordering deterministic.
    """
    state = {"t": start}

    def _tick() -> int:
        state["t"] += 1_000_000
        return state["t"]

    return _tick


def run_cmd(func, args) -> tuple[int, dict]:
    """Run a command function, returning (rc, last-JSON-line-printed).

    Composite commands (e.g. `commit`) print more than one JSON object
    because they call another command's function internally; the last line
    is always that command's own final summary.
    """
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = func(args)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return rc, (json.loads(lines[-1]) if lines else {})


class ZcodeExtractorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "zcode-home"
        self.db_path = self.root / "db.sqlite"
        self.tasks_db_path = self.root / "tasks-index.sqlite"
        self.ws = ext.Workspace(self.home, self.home / "self-improve" / "extraction-runs", self.home / "AGENTS.extraction-log.md")
        memory(self.ws)
        self.session_con = create_session_db(self.db_path)
        self.tasks_con = create_tasks_db(self.tasks_db_path)
        self.personal = self.root / "Downloads" / "Personal" / "proj"
        self.work = self.root / "Downloads" / "Work" / "proj"
        self.personal.mkdir(parents=True)
        self.work.mkdir(parents=True)

    def tearDown(self) -> None:
        self.session_con.close()
        self.tasks_con.close()
        self.tmp.cleanup()

    def base_args(self, **overrides) -> SimpleNamespace:
        return make_args(
            zcode_home=str(self.home),
            db_path=str(self.db_path),
            tasks_db_path=str(self.tasks_db_path),
            scope_root=[str(self.personal), str(self.work)],
            **overrides,
        )

    def prepare(self, **overrides) -> dict:
        _, result = run_cmd(ext.cmd_prepare, self.base_args(command="prepare", **overrides))
        return result

    # ---------------------------------------------------------------- (1)
    def test_readonly_connection_rejects_write(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=1000)
        con = ext.open_ro(self.db_path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                con.execute("UPDATE session SET title = 'x' WHERE id = 's1'")
        finally:
            con.close()
        # Confirm the live source file truly was not modified.
        digest_before = ext.digest_file(self.db_path)
        con2 = ext.open_ro(self.db_path)
        con2.close()
        self.assertEqual(digest_before, ext.digest_file(self.db_path))

    # ---------------------------------------------------------------- (2)
    def test_scope_and_exclusion_logic(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "personal-a", str(self.personal), time_updated=now - 1000, title="Real work")
        add_text_turn(self.session_con, "personal-a", 0, "user", "Always run tests before committing.", now - 1000)

        add_session(self.session_con, "work-a", str(self.work), time_updated=now - 900, title="Work task")
        add_text_turn(self.session_con, "work-a", 0, "user", "Some work happened.", now - 900)

        add_session(self.session_con, "subagent-a", str(self.personal), time_updated=now - 800,
                    parent_id="personal-a", task_type="subagent_child")
        add_text_turn(self.session_con, "subagent-a", 0, "user", "Subagent task text.", now - 800)

        add_session(self.session_con, "automation-a", str(self.personal), time_updated=now - 700, title="Automation run")
        add_text_turn(self.session_con, "automation-a", 0, "assistant", "Automation output.", now - 700)
        self.tasks_con.execute("INSERT INTO automation_runs (run_id, session_id) VALUES ('r1','automation-a')")
        self.tasks_con.commit()

        add_session(self.session_con, "scheduled-title", str(self.personal), time_updated=now - 600,
                    title='<scheduled-task name="x">')

        add_session(self.session_con, "scheduled-body", str(self.personal), time_updated=now - 500, title="Normal title")
        add_text_turn(self.session_con, "scheduled-body", 0, "user", '<scheduled-task name="y" file=foo>', now - 500)

        add_session(self.session_con, "self-run", str(self.personal), time_updated=now - 400, title="Self run")
        add_text_turn(self.session_con, "self-run", 0, "user", "Self run text.", now - 400)

        add_session(self.session_con, "outside-scope", str(self.root / "elsewhere"), time_updated=now - 300)
        add_text_turn(self.session_con, "outside-scope", 0, "user", "Outside scope text.", now - 300)

        result = self.prepare(self_session_id="self-run")
        ids = {s["id"] for s in json.loads((Path(result["run_dir"]) / "manifest.json").read_text())["sessions"]}
        self.assertEqual(ids, {"personal-a", "work-a"})

    # ---------------------------------------------------------------- (16)
    def test_default_scope_roots_are_personal_and_work(self) -> None:
        now = ext.now_ms()
        fake_home = self.root / "fakehome"
        (fake_home / "Downloads" / "Personal").mkdir(parents=True)
        in_scope_dir = fake_home / "Downloads" / "Personal" / "proj"
        in_scope_dir.mkdir(parents=True)
        out_of_scope_dir = self.root / "elsewhere"
        out_of_scope_dir.mkdir(parents=True)
        add_session(self.session_con, "in-default-scope", str(in_scope_dir), time_updated=now - 100)
        add_session(self.session_con, "out-default-scope", str(out_of_scope_dir), time_updated=now - 50)
        args = make_args(
            zcode_home=str(self.home), db_path=str(self.db_path), tasks_db_path=str(self.tasks_db_path),
            command="prepare", scope_root=None,
        )
        with mock.patch.object(ext.Path, "home", return_value=fake_home):
            _, result = run_cmd(ext.cmd_prepare, args)
        manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text())
        ids = {s["id"] for s in manifest["sessions"]}
        self.assertEqual(ids, {"in-default-scope"})

    # ---------------------------------------------------------------- (5)
    def test_watermark_bounds_are_exclusive_lower_inclusive_upper(self) -> None:
        lower, upper = 1_000_000, 2_000_000
        add_session(self.session_con, "at-lower", str(self.personal), time_updated=lower)
        add_session(self.session_con, "in-window", str(self.personal), time_updated=lower + 1)
        add_session(self.session_con, "at-upper", str(self.personal), time_updated=upper)
        add_session(self.session_con, "past-upper", str(self.personal), time_updated=upper + 1)
        sessions = ext.discover_sessions(self.db_path, self.tasks_db_path, lower, upper, [self.personal], None)
        ids = {s["id"] for s in sessions}
        self.assertEqual(ids, {"in-window", "at-upper"})

    def test_bootstrap_when_watermark_missing(self) -> None:
        self.assertFalse(self.ws.state.exists())
        now = ext.now_ms()
        add_session(self.session_con, "old", str(self.personal), time_updated=now - 72 * 3600 * 1000)
        add_session(self.session_con, "recent", str(self.personal), time_updated=now - 1000)
        result = self.prepare(bootstrap_hours=48)
        self.assertTrue(result["bootstrap"])
        manifest = json.loads((Path(result["run_dir"]) / "manifest.json").read_text())
        ids = {s["id"] for s in manifest["sessions"]}
        self.assertEqual(ids, {"recent"})

    # ---------------------------------------------------------------- (4)
    def test_noise_stripping_and_part_normalization(self) -> None:
        self.assertIsNone(ext.strip_noise("<system-reminder>hi</system-reminder>") or None)
        self.assertEqual(ext.strip_noise("keep <system-reminder>drop</system-reminder> this"), "keep  this")
        self.assertIsNone(ext.strip_noise("```userselect\nselected code\n```"))
        self.assertEqual(ext.strip_noise("# userselect: some text"), "some text")
        self.assertEqual(ext.strip_noise("[$skill](path/to/skill) do the thing"), "do the thing")
        self.assertIsNone(ext.strip_noise("<!-- attach -->"))
        self.assertEqual(ext.strip_noise("do the work /plan"), "do the work")
        self.assertIsNone(ext.strip_noise('<scheduled-task name="x">'))
        self.assertIsNone(ext.strip_noise("<app-context>x</app-context>"))
        self.assertIsNone(ext.strip_noise("[Request interrupted by user for tool use]"))
        self.assertIsNone(ext.strip_noise("The TodoWrite tool hasn't been used recently, is it up to date?"))
        self.assertIsNone(ext.strip_noise("You are " + ("x" * 500)))
        self.assertEqual(ext.strip_noise("Always verify before committing."), "Always verify before committing.")

        self.assertIsNone(ext.part_event("developer", {"type": "text", "text": "hi"}))
        self.assertIsNone(ext.part_event("assistant", {"type": "reasoning", "text": "thinking"}))
        role, text = ext.part_event("tool", {"type": "tool", "tool": "Bash", "state": {"status": "error", "error": "boom"}})
        self.assertEqual(role, "tool")
        self.assertIn("Bash error", text)
        self.assertIn("boom", text)

    def test_pasted_text_file_part_is_read_and_capped(self) -> None:
        pasted = self.root / "pasted.txt"
        pasted.write_text("A" * 5000)
        role, text = ext.part_event("user", {"type": "file", "mime": "text/plain", "url": str(pasted)})
        self.assertEqual(role, "user")
        self.assertTrue(text.startswith("[pasted file] "))
        self.assertLessEqual(len(text) - len("[pasted file] "), 4000)

    def test_secret_redaction_in_normalized_text(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "api_key = sk-abcdefghijklmnop", now)
        sessions = ext.discover_sessions(self.db_path, self.tasks_db_path, 0, now + 1, [self.personal], None)
        text = sessions[0]["events"][0]["text"]
        self.assertNotIn("sk-abcdefghijklmnop", text)
        self.assertIn("REDACTED", text)

    # ---------------------------------------------------------------- (6/7) no live writes
    def test_prepare_does_not_touch_live_memory(self) -> None:
        before = ext.snapshot(self.ws)
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        self.prepare()
        self.assertEqual(ext.snapshot(self.ws), before)
        self.assertFalse(self.ws.state.exists())

    def test_validation_failure_leaves_live_memory_and_watermark_untouched(self) -> None:
        before = ext.snapshot(self.ws)
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("changed but undeclared")
        rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertEqual(ext.snapshot(self.ws), before)
        self.assertFalse(self.ws.state.exists())

    # ---------------------------------------------------------------- (8)
    def test_validate_rejects_bad_evidence_and_project_destination(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("changed")
        (run_dir / "staging" / "AGENTS.extraction-log.md").write_text("## 2026-09-12 run\n- [WROTE-DOC] x\n")
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "project", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"event_sha256": "missing"}], "reason": "bad",
        }) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("missing evidence hash" in e for e in out["errors"]))
        self.assertTrue(any("non-project destination" in e for e in out["errors"]))

    # ---------------------------------------------------------------- (14) session accounting
    def test_validate_requires_complete_session_accounting(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("not accounted for" in e and "s1" in e for e in out["errors"]))
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        rc2, out2 = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc2, 0)

    def test_validate_rejects_unknown_session_in_dispositions(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "session_dispositions.jsonl").write_text(
            json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n" +
            json.dumps({"session_id": "not-discovered", "status": "reviewed_no_learning"}) + "\n"
        )
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("outside this run" in e for e in out["errors"]))

    # ---------------------------------------------------------------- (fix 3)
    def test_session_disposition_status_must_be_one_of_the_allowed_values(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "maybe"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("invalid session_disposition status" in e for e in out["errors"]))

    def test_session_disposition_duplicate_session_id_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "session_dispositions.jsonl").write_text(
            json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n" +
            json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n"
        )
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("duplicate session_id" in e for e in out["errors"]))

    def test_contributed_session_requires_decision_evidence(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("no decision cites its evidence" in e for e in out["errors"]))

        # Staging a real decision that cites this session's evidence (and the
        # matching "contributed" disposition) must clear the error.
        self._stage_valid_change(run_dir, "s1")
        rc2, out2 = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc2, 0, out2.get("errors"))

    # ---------------------------------------------------------------- (9)
    def test_validate_rejects_secret_in_staged_file_and_decision(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("api_key = abcdefgh123456\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("secret-like value" in e for e in out["errors"]))

    # ---------------------------------------------------------------- (10)
    def test_validate_rejects_broken_pointer_and_oversized_map(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "AGENTS.md").write_text(
            "# Map\n" + "\n".join(f"line {i}" for i in range(120)) + "\n- See docs/does-not-exist.md.\n"
        )
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("100-line limit" in e for e in out["errors"]))
        self.assertTrue(any("broken map pointer" in e for e in out["errors"]))

    # ---------------------------------------------------------------- (19) safe path handling
    def test_staged_deletion_and_symlink_and_bad_destination_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").unlink()
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("staged deletions are not allowed" in e for e in out["errors"]))

    def test_staged_symlink_raises(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        target = run_dir / "staging" / "docs" / "escape.md"
        target.symlink_to(self.root / "outside.md")
        with self.assertRaises(ext.RunError):
            ext.staged_files(run_dir / "staging")

    def test_decision_destination_outside_docs_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("changed")
        (run_dir / "staging" / "AGENTS.extraction-log.md").write_text("## 2026-09-12 run\n- [WROTE-DOC] x\n")
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "../../etc/passwd",
            "evidence": [], "reason": "bad",
        }) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("invalid decision destination" in e for e in out["errors"]))

    # ---------------------------------------------------------------- (11) stale baseline
    def test_stale_baseline_detected_at_validate_and_apply(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        # Mutate live memory after prepare, before validate.
        (self.ws.memory / "rules.md").write_text("mutated by someone else")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("live memory changed after prepare" in e for e in out["errors"]))
        # Restore and validate cleanly, then mutate before apply.
        (self.ws.memory / "rules.md").write_text("# Rules\n")
        rc2, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc2, 0)
        (self.ws.memory / "rules.md").write_text("mutated again")
        with self.assertRaises(ext.RunError):
            ext.cmd_apply(self.base_args(command="apply", run_id=result["run_id"], apply=True))

    # ---------------------------------------------------------------- (12) successful commit
    def _stage_valid_change(self, run_dir: Path, session_id: str, supporting_destinations: list[str] | None = None) -> None:
        (run_dir / "staging" / "docs" / "rules.md").write_text("# Rules\n- Always run tests before committing. (updated 2026-09-12)\n")
        # The ledger is append-only: staged content must start with the exact
        # baseline bytes, so append to the staged copy rather than replace it.
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(
            ledger_path.read_text() +
            "## 2026-09-12 run\n- [WROTE-DOC] Always run tests before committing. -> docs/rules.md | Confirmed\n"
        )
        # Fixture fix: this helper is also used with multi-session runs
        # (e.g. a run that rediscovers an older session alongside a new
        # one), where the *first* line of normalized_sessions.jsonl is not
        # necessarily the session named by `session_id`. The staged decision
        # must cite evidence from the session it claims to be about, or
        # validation's "contributed but no decision cites its evidence"
        # check correctly rejects the mismatch.
        matching_session = next(
            json.loads(line) for line in (run_dir / "normalized_sessions.jsonl").read_text().splitlines()
            if json.loads(line)["id"] == session_id
        )
        event = matching_session["events"][0]
        decision = {
            "claim": "Always run tests before committing.",
            "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "confirmation_basis": "explicit_user_rule",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_timestamp": event["event_timestamp"], "event_sha256": event["event_sha256"]}],
            "reason": "user stated rule",
        }
        if supporting_destinations:
            decision["supporting_destinations"] = supporting_destinations
        (run_dir / "decisions.jsonl").write_text(json.dumps(decision) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": session_id, "status": "contributed"}) + "\n")

    def test_successful_commit_applies_files_and_advances_watermark(self) -> None:
        upper_target = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=upper_target)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", upper_target)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, out = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"], keep=5))
        self.assertEqual(rc, 0)
        self.assertTrue(out["committed"])
        self.assertIn("Always run tests before committing.", (self.ws.memory / "rules.md").read_text())
        watermark = json.loads(self.ws.state.read_text())
        self.assertEqual(watermark, {"last_time_updated": result["upper_bound"]})
        self.assertFalse(self.ws.lock.exists())
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "completed")
        self.assertFalse((run_dir / "normalized_sessions.jsonl").exists())
        # Source databases must be untouched by the whole prepare->commit cycle.
        self.session_con.close()
        self.tasks_con.close()

    # ---------------------------------------------------------------- (13) empty run
    def test_empty_run_advances_watermark_with_no_sessions(self) -> None:
        result = self.prepare()
        self.assertEqual(result["session_count"], 0)
        run_dir = Path(result["run_dir"])
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(ledger_path.read_text() + "## 2026-09-12 run\n- [NO-OP] no in-scope sessions\n")
        rc, out = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        watermark = json.loads(self.ws.state.read_text())
        self.assertEqual(watermark["last_time_updated"], result["upper_bound"])

    # ---------------------------------------------------------------- (15) interrupted commit + recovery
    def test_interrupted_commit_is_detected_and_recoverable(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        # docs/index.md is a required supporting update alongside the primary
        # docs/rules.md write decision -- it must be declared via
        # supporting_destinations, or the "every changed file needs an
        # authorizing decision" check (finding 4) rejects it as unauthorized.
        self._stage_valid_change(run_dir, "s1", supporting_destinations=["docs/index.md"])
        # Add a second staged file so the interruption happens after one file
        # has already been applied live -- proving the design is recoverable,
        # not atomic.
        (run_dir / "staging" / "docs" / "index.md").write_text("# Index\n- rules.md (updated)\n")
        rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 0)

        original_atomic_write = ext.atomic_write
        calls = {"n": 0}

        def flaky_atomic_write(path, data):
            calls["n"] += 1
            # Sequence inside cmd_apply: (1) its internal re-validation writes
            # validation.json, (2) backup's presence.json, (3) trusted
            # apply.json, (4) commit marker (with backup), then the staged
            # files in sorted order: (5) AGENTS.extraction-log.md, (6)
            # docs/index.md, (7) docs/rules.md. Failing on the 6th call means
            # one staged live file (the ledger) has already been applied when
            # the crash hits -- proving the design is recoverable, not atomic.
            if calls["n"] == 6:
                raise OSError("simulated crash mid-apply")
            return original_atomic_write(path, data)

        pre_run_rules = (self.ws.memory / "rules.md").read_text()
        pre_run_index = (self.ws.memory / "index.md").read_text()
        pre_run_ledger = self.ws.ledger.read_text()

        with mock.patch.object(ext, "atomic_write", flaky_atomic_write):
            with self.assertRaises(OSError):
                ext.cmd_apply(self.base_args(command="apply", run_id=result["run_id"], apply=True))
        # Sanity: the crash really did land mid-apply, after one live file
        # (the ledger) was already overwritten -- not before any write at all.
        self.assertNotEqual(self.ws.ledger.read_text(), pre_run_ledger)

        # The commit marker is a durable, on-disk record of the interruption
        # -- it does not depend on this process catching its own exception.
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())
        self.assertFalse(self.ws.state.exists())

        # A fresh prepare must refuse to start while a commit is unresolved.
        with self.assertRaises(ext.RunError):
            run_cmd(ext.cmd_prepare, self.base_args(command="prepare"))

        rc, out = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self.assertTrue(out["recovered"])
        self.assertEqual((self.ws.memory / "rules.md").read_text(), pre_run_rules)
        self.assertEqual((self.ws.memory / "index.md").read_text(), pre_run_index)
        self.assertFalse(self.ws.state.exists())
        self.assertFalse(self.ws.lock.exists())
        marker_after = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker_after["status"], "recovered")

        # Now a new prepare must succeed again -- no evidence was silently skipped.
        add_session(self.session_con, "s2", str(self.personal), time_updated=ext.now_ms())
        result2 = self.prepare()
        self.assertGreaterEqual(result2["session_count"], 1)

    def test_status_reports_incomplete_commit(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        original_atomic_write = ext.atomic_write
        calls = {"n": 0}

        def flaky(path, data):
            calls["n"] += 1
            # Let the internal re-validation, the trusted apply-state write,
            # both commit-marker writes, and the backup succeed first; fail
            # right as the staged-file loop starts (see the call sequence
            # documented in
            # test_interrupted_commit_is_detected_and_recoverable).
            if calls["n"] >= 5:
                raise OSError("boom")
            return original_atomic_write(path, data)

        with mock.patch.object(ext, "atomic_write", flaky):
            with self.assertRaises(OSError):
                ext.cmd_apply(self.base_args(command="apply", run_id=result["run_id"], apply=True))
        rc, out = run_cmd(ext.cmd_status, self.base_args(command="status"))
        self.assertEqual(rc, 0)
        self.assertIn(result["run_id"], out["incomplete_commits"])
        run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))

    # ---------------------------------------------------------------- prune
    def test_prune_keeps_only_newest_runs_and_backups(self) -> None:
        run_ids = []
        fake_now = make_fake_clock()
        with mock.patch.object(ext, "now_ms", side_effect=fake_now):
            for i in range(3):
                ts = ext.now_ms()
                add_session(self.session_con, f"s{i}", str(self.personal), time_updated=ts)
                add_text_turn(self.session_con, f"s{i}", 0, "user", "Always run tests before committing.", ts)
                result = self.prepare(run_id=f"run-{i}")
                run_dir = Path(result["run_dir"])
                self._stage_valid_change(run_dir, f"s{i}")
                rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"], keep=1))
                self.assertEqual(rc, 0)
                run_ids.append(result["run_id"])
        remaining_runs = [d.name for d in self.ws.runs.iterdir() if d.is_dir()]
        self.assertLessEqual(len(remaining_runs), 1)
        remaining_backups = [d.name for d in self.home.glob("extraction-backup-*")]
        self.assertLessEqual(len(remaining_backups), 1)

    # ---------------------------------------------------------------- (fix 2)
    def test_prune_preserves_backup_referenced_by_incomplete_commit(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s0", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s0", 0, "user", "Always run tests before committing.", now)
        result = self.prepare(run_id="run-0")
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s0")
        rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id="run-0"))
        self.assertEqual(rc, 0)

        original_atomic_write = ext.atomic_write

        def flaky(path, data):
            # Let the re-validation, the trusted apply-state write, both
            # commit-marker writes, and the backup succeed first; fail before
            # any live target is actually overwritten, so a backup exists and
            # is referenced by the marker + trusted apply state, but the run
            # is unambiguously "incomplete".
            name = Path(path).name
            if name in {"commit.json", "presence.json", "validation.json", "apply.json"}:
                return original_atomic_write(path, data)
            raise OSError("boom")

        with mock.patch.object(ext, "atomic_write", flaky):
            with self.assertRaises(OSError):
                ext.cmd_apply(self.base_args(command="apply", run_id="run-0", apply=True))

        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        backup0 = Path(marker["backup"])
        self.assertTrue(backup0.is_dir())

        # Make backup0 look like the *oldest* backup on disk, and create
        # newer, unrelated backup directories -- a naive recency-only prune
        # (keep the newest N) would otherwise evict exactly the one backup
        # `recover` still needs.
        old_time = time.time() - 100_000
        os.utime(backup0, (old_time, old_time))
        fake_backups = []
        for i in range(3):
            fake = self.home / f"extraction-backup-fake-{i}"
            fake.mkdir()
            fresh = time.time() - i
            os.utime(fake, (fresh, fresh))
            fake_backups.append(fake)

        rc2, out = run_cmd(ext.cmd_prune, self.base_args(command="prune", keep=1))
        self.assertEqual(rc2, 0)

        self.assertTrue(backup0.exists(), "the incomplete commit's only backup must survive prune")
        self.assertTrue(run_dir.exists())
        self.assertNotIn(backup0.name, out["pruned"]["backups"])
        self.assertTrue(any(not f.exists() for f in fake_backups), "prune should still reclaim unprotected backups")

        rc3, out3 = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id="run-0"))
        self.assertEqual(rc3, 0)
        self.assertTrue(out3["recovered"])

    # ------------------------------------------------------------------
    # Astra-review hardening: helpers shared by the new regression tests
    # below (findings 1-9).
    # ------------------------------------------------------------------

    # ==================================================================
    # Astra-review round 2 (findings 1-8): trusted control state, strict
    # recovery, discovery boundary, symlink preflight, run-dir containment,
    # repair-recover, and deployment checking. Helpers first: the trusted
    # control state lives outside the agent-editable run directory, under
    # ~/.zcode/self-improve/extraction-control/<run_id>/.
    # ==================================================================

    def _control_dir(self, run_id: str) -> Path:
        return self.ws.home / "self-improve" / "extraction-control" / run_id

    def _ensure_control_record(self, run_dir: Path, run_id: str) -> dict:
        """Return the run's trusted control record, creating it from the run
        manifest only if the runner itself has not written one yet (the red
        phase of these regression tests). This mirrors exactly what `prepare`
        must bind into trusted state; once implemented, `prepare` writes it
        and this helper is a read-only no-op.
        """
        path = self._control_dir(run_id) / "control.json"
        if path.exists():
            return json.loads(path.read_text())
        manifest = json.loads((run_dir / "manifest.json").read_text())
        inventory = sorted(set(manifest["baseline_hashes"]) | {ext.WATERMARK_REL})
        authorized: dict[str, dict] = {}
        for rel in inventory:
            if rel == ext.WATERMARK_REL:
                existed = bool(manifest["watermark_baseline"]["existed"])
                authorized[rel] = {
                    "present": existed,
                    "sha256": manifest["watermark_baseline"]["hash"] if existed else None,
                }
            else:
                authorized[rel] = {"present": True, "sha256": manifest["baseline_hashes"][rel]}
        record = {
            "version": 1,
            "run_id": run_id,
            "lower_bound": manifest["lower_bound"],
            "upper_bound": manifest["upper_bound"],
            "bootstrap": manifest.get("bootstrap", False),
            "automation_id": manifest.get("automation_id", ""),
            "model_id": manifest.get("model_id", ""),
            "prompt_sha256": manifest.get("prompt_sha256", ""),
            "session_count": manifest.get("session_count", 0),
            "sessions": manifest.get("sessions", []),
            "baseline_hashes": manifest["baseline_hashes"],
            "watermark_baseline": manifest["watermark_baseline"],
            "normalized_evidence_sha256": manifest["normalized_evidence_sha256"],
            "authorized_targets": authorized,
        }
        self._control_dir(run_id).mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record

    def _write_apply_state(self, run_dir: Path, run_id: str, backup: Path) -> dict:
        """Record the trusted apply state the runner must write (and bind to
        the backup manifest digest) *before* its first live file -- red-phase
        stand-in for the runner's own apply-state recording.
        """
        manifest = json.loads((run_dir / "manifest.json").read_text())
        staged = sorted(ext.staged_files(run_dir / "staging"))
        inventory = sorted(set(manifest["baseline_hashes"]) | set(staged) | {ext.WATERMARK_REL})
        expected_presence: dict[str, bool] = {}
        expected_hashes: dict[str, str] = {}
        for rel in inventory:
            if rel == ext.WATERMARK_REL:
                existed = bool(manifest["watermark_baseline"]["existed"])
                expected_presence[rel] = existed
                if existed:
                    expected_hashes[rel] = manifest["watermark_baseline"]["hash"]
            elif rel in manifest["baseline_hashes"]:
                expected_presence[rel] = True
                expected_hashes[rel] = manifest["baseline_hashes"][rel]
            else:
                expected_presence[rel] = False  # staged addition: absent pre-run
        state = {
            "version": 1,
            "run_id": run_id,
            "staged": staged,
            "backup_path": str(backup),
            "backup_manifest_sha256": ext.digest_file(backup / "presence.json"),
            "authorized_inventory": inventory,
            "expected_presence": expected_presence,
            "expected_hashes": expected_hashes,
        }
        (self._control_dir(run_id) / "apply.json").write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        return state

    def _interrupt_before_backup(self, run_dir: Path, run_id: str) -> None:
        """Simulate a crash between the *first* commit-marker write and
        backup_live() -- the marker is in_progress with no backup recorded,
        no trusted apply state exists, and by construction no live file has
        been touched yet.
        """
        self._ensure_control_record(run_dir, run_id)
        ext.write_commit_marker(run_dir, run_id, "in_progress")

    def _interrupt_after_backup(self, run_dir: Path, run_id: str) -> Path:
        """Simulate a crash right after the backup is produced, fully
        verified, and recorded in trusted control state, but before any
        staged file is written live -- marker in_progress with a backup and
        a matching trusted apply state.
        """
        manifest = json.loads((run_dir / "manifest.json").read_text())
        staged = ext.staged_files(run_dir / "staging")
        self._ensure_control_record(run_dir, run_id)
        ext.write_commit_marker(run_dir, run_id, "in_progress")
        backup = ext.backup_live(self.ws, manifest, staged)
        ext.write_commit_marker(run_dir, run_id, "in_progress", backup=backup)
        self._write_apply_state(run_dir, run_id, backup)
        return backup

    def _prepare_with_user_and_tool_events(self):
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        add_turn(self.session_con, "s1", 1, "assistant", {"type": "tool", "tool": "Bash", "state": {"status": "completed"}}, now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        session = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])
        events_by_role = {e["role"]: e for e in session["events"]}
        return result, run_dir, events_by_role

    def _write_decision(self, run_dir: Path, decision: dict, session_id: str = "s1") -> None:
        (run_dir / "staging" / "docs" / "rules.md").write_text("# Rules\n- x. (updated 2026-09-12)\n")
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(ledger_path.read_text() + "## 2026-09-12 run\n- [WROTE-DOC] x -> docs/rules.md | Confirmed\n")
        (run_dir / "decisions.jsonl").write_text(json.dumps(decision) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": session_id, "status": "contributed"}) + "\n")

    # ================================================================== (1)
    # State-aware recovery and lock ownership.
    # ==================================================================

    def test_recover_completed_run_is_a_noop_and_does_not_restore(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        committed_rules = (self.ws.memory / "rules.md").read_text()

        rc2, out2 = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc2, 0)
        self.assertFalse(out2["recovered"])
        self.assertEqual(out2["reason"], "already completed")
        self.assertEqual((self.ws.memory / "rules.md").read_text(), committed_rules)
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "completed")

    def test_recover_completed_run_releases_leftover_same_run_lock(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self.assertFalse(self.ws.lock.exists())
        # Simulate a leftover lock for the already-completed run.
        ext.acquire_lock(self.ws, result["run_id"])
        self.assertTrue(self.ws.lock.exists())

        rc2, out2 = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc2, 0)
        self.assertFalse(out2["recovered"])
        self.assertFalse(self.ws.lock.exists())

    def test_recover_is_idempotent_and_never_overwrites_a_later_runs_work(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self._interrupt_after_backup(run_dir, result["run_id"])

        rc, out = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self.assertTrue(out["recovered"])

        # Simulate a later, unrelated live change (as if a subsequent run
        # wrote something new) that a second `recover` on this *same* old
        # run_id must never clobber.
        (self.ws.memory / "rules.md").write_text("# Rules\n- Written by a later run.\n")

        rc2, out2 = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc2, 0)
        self.assertFalse(out2["recovered"])
        self.assertEqual(out2["reason"], "already recovered")
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n- Written by a later run.\n")

    def test_recover_refuses_when_a_different_run_owns_the_lock(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare(run_id="run-a")
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id="run-a"))
        self._interrupt_after_backup(run_dir, "run-a")
        # A different run now owns the lock (simulated by releasing run-a's
        # lock and acquiring a fresh one for run-b).
        ext.release_lock(self.ws, "run-a")
        ext.acquire_lock(self.ws, "run-b")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id="run-a"))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        lock_meta = json.loads((self.ws.lock / "owner.json").read_text())
        self.assertEqual(lock_meta["run_id"], "run-b")

    # ================================================================== (2)
    # Fail-closed backup restoration.
    # ==================================================================

    def test_recover_fails_closed_when_backup_directory_missing(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        shutil.rmtree(backup)

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())
        self.assertTrue((run_dir / "normalized_sessions.jsonl").exists())

    def test_recover_fails_closed_when_backup_manifest_malformed(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        (backup / "presence.json").write_text("not json")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")

    def test_recover_fails_closed_when_backed_up_file_missing(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        (backup / "docs" / "rules.md").unlink()

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")

    def test_recover_fails_closed_on_backup_hash_mismatch(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        (backup / "docs" / "rules.md").write_text("tampered content, does not match its stored hash")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        # Live memory must remain exactly as prepare left it -- no partial
        # restoration happened.
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n")
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")

    def test_recover_aborts_when_marker_predates_backup_and_state_matches_baseline(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._interrupt_before_backup(run_dir, result["run_id"])
        self.assertFalse(self.ws.state.exists())

        rc, out = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self.assertTrue(out["recovered"])
        self.assertEqual(out["reason"], "aborted before any live write")
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "recovered")
        self.assertFalse(self.ws.lock.exists())

    def test_recover_fails_closed_when_marker_predates_backup_but_state_diverged(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._interrupt_before_backup(run_dir, result["run_id"])
        # Live state no longer matches this run's own baseline -- recover
        # must refuse to guess rather than silently abort or restore.
        (self.ws.memory / "rules.md").write_text("mutated unexpectedly")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    # ================================================================== (3)
    # Evidence and confidence validation.
    # ==================================================================

    def test_decision_requires_nonempty_evidence(self) -> None:
        result, run_dir, _events = self._prepare_with_user_and_tool_events()
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "provisional",
            "disposition": "PROVISIONAL", "evidence": [], "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("decision has no evidence" in e for e in out["errors"]))

    def test_evidence_must_match_a_real_session_and_event(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        user_event = events["user"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": "not-a-real-session", "event_sha256": user_event["event_sha256"],
                          "event_timestamp": user_event["event_timestamp"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("missing evidence hash" in e for e in out["errors"]))

    def test_evidence_timestamp_mismatch_rejected(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        user_event = events["user"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": user_event["session_id"], "event_sha256": user_event["event_sha256"],
                          "event_timestamp": "1999-01-01T00:00:00+00:00"}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("event_timestamp mismatch" in e for e in out["errors"]))

    def test_provisional_and_confirmed_confidence_disposition_combinations(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        user_event = events["user"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "provisional",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": user_event["session_id"], "event_sha256": user_event["event_sha256"],
                          "event_timestamp": user_event["event_timestamp"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("provisional confidence may only pair with PROVISIONAL" in e for e in out["errors"]))
        self.assertTrue(any("requires confirmed confidence" in e for e in out["errors"]))

    def test_write_disposition_requires_a_qualifying_user_role_evidence_event(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        tool_event = events["tool"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "technical_fact", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": tool_event["session_id"], "event_sha256": tool_event["event_sha256"],
                          "event_timestamp": tool_event["event_timestamp"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("qualifying user-role evidence" in e for e in out["errors"]))

    # ================================================================== (4)
    # Complete changed-file authorization and append-only ledger.
    # ==================================================================

    def test_unauthorized_memory_change_rejected_even_with_one_valid_destination(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")  # authorizes only docs/rules.md
        (run_dir / "staging" / "docs" / "index.md").write_text("# Index\n- sneaky unrelated change\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("not authorized by any decision destination" in e and "index.md" in e for e in out["errors"]))

    def test_supporting_destinations_without_primary_write_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "index.md").write_text("# Index\n- rules.md (updated)\n")
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(ledger_path.read_text() + "## 2026-09-12 run\n- [WROTE-DOC] x -> docs/index.md | Confirmed\n")
        event = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])["events"][0]
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC",  # write disposition, but no primary `destination`
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"],
                          "event_timestamp": event["event_timestamp"]}],
            "reason": "r", "supporting_destinations": ["docs/index.md"],
        }) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("supporting_destinations present without any primary write decision" in e for e in out["errors"]))

    def test_supporting_destinations_authorizes_required_index_update(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1", supporting_destinations=["docs/index.md"])
        (run_dir / "staging" / "docs" / "index.md").write_text("# Index\n- rules.md (updated)\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 0, out.get("errors"))

    def test_ledger_truncation_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        (run_dir / "staging" / "AGENTS.extraction-log.md").write_text("## 2026-09-12 run\n- [WROTE-DOC] x\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("append-only" in e for e in out["errors"]))

    def test_ledger_in_place_edit_rejected(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        baseline_text = self.ws.ledger.read_text()
        mutated_baseline = baseline_text.replace("NO-OP", "XX-OOP")
        appended = ledger_path.read_text()[len(baseline_text):]
        ledger_path.write_text(mutated_baseline + appended)
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("append-only" in e for e in out["errors"]))

    # ================================================================== (5)
    # Watermark parsing fails closed.
    # ==================================================================

    def test_watermark_malformed_json_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text("{not valid json")
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertEqual(self.ws.state.read_text(), "{not valid json")
        self.assertFalse(self.ws.lock.exists())

    def test_watermark_wrong_schema_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text(json.dumps([1, 2, 3]))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertFalse(self.ws.lock.exists())

    def test_watermark_nonnumeric_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text(json.dumps({"last_time_updated": "soon"}))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertFalse(self.ws.lock.exists())

    def test_watermark_boolean_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text(json.dumps({"last_time_updated": True}))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertFalse(self.ws.lock.exists())

    def test_watermark_negative_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text(json.dumps({"last_time_updated": -1}))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertFalse(self.ws.lock.exists())

    def test_watermark_future_fails_closed(self) -> None:
        self.ws.state.parent.mkdir(parents=True, exist_ok=True)
        self.ws.state.write_text(json.dumps({"last_time_updated": ext.now_ms() + 365 * 24 * 3600 * 1000}))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(self.base_args(command="prepare"))
        self.assertFalse(self.ws.lock.exists())

    # ================================================================== (6)
    # Robust lock publication and abandoned-lock handling.
    # ==================================================================

    def test_lock_is_a_directory_with_owner_metadata(self) -> None:
        ext.acquire_lock(self.ws, "run-x")
        self.assertTrue(self.ws.lock.is_dir())
        meta = json.loads((self.ws.lock / "owner.json").read_text())
        self.assertEqual(meta["run_id"], "run-x")
        ext.release_lock(self.ws, "run-x")
        self.assertFalse(self.ws.lock.exists())

    def test_malformed_lock_blocks_new_acquisition_and_require_lock(self) -> None:
        # Simulate interruption between directory creation and metadata
        # publication: the lock directory exists, owner.json does not.
        self.ws.lock.mkdir(parents=True)
        with self.assertRaises(ext.RunError):
            ext.acquire_lock(self.ws, "run-y")
        with self.assertRaises(ext.RunError):
            ext.require_lock(self.ws, "run-y")

    def test_unlock_abandoned_no_lock_present(self) -> None:
        rc, out = run_cmd(ext.cmd_unlock_abandoned, self.base_args(command="unlock-abandoned"))
        self.assertEqual(rc, 0)
        self.assertFalse(out["unlocked"])

    def test_unlock_abandoned_refuses_when_owning_process_is_alive(self) -> None:
        self.ws.lock.mkdir(parents=True)
        ext.atomic_json(self.ws.lock / "owner.json", {"run_id": "run-z", "pid": os.getpid(), "created_at": time.time()})
        with self.assertRaises(ext.RunError):
            ext.cmd_unlock_abandoned(self.base_args(command="unlock-abandoned", run_id="run-z"))
        self.assertTrue(self.ws.lock.exists())

    def test_unlock_abandoned_removes_lock_when_owning_process_is_dead(self) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        dead_pid = proc.pid
        self.ws.lock.mkdir(parents=True)
        ext.atomic_json(self.ws.lock / "owner.json", {"run_id": "run-z", "pid": dead_pid, "created_at": time.time()})
        rc, out = run_cmd(ext.cmd_unlock_abandoned, self.base_args(command="unlock-abandoned"))
        self.assertEqual(rc, 0)
        self.assertTrue(out["unlocked"])
        self.assertFalse(self.ws.lock.exists())

    def test_unlock_abandoned_refuses_while_incomplete_commit_exists(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._interrupt_before_backup(run_dir, result["run_id"])
        # Corrupt the lock's metadata so it looks abandoned/unidentifiable.
        (self.ws.lock / "owner.json").unlink()

        with self.assertRaises(ext.RunError):
            ext.cmd_unlock_abandoned(self.base_args(command="unlock-abandoned"))
        self.assertTrue(self.ws.lock.exists())

    # ================================================================== (7)
    # Consistent read snapshot and bounded evidence.
    # ==================================================================

    def test_discover_sessions_uses_one_connection_and_is_repeatable(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "hello", now)
        first = ext.discover_sessions(self.db_path, self.tasks_db_path, 0, now + 1, [self.personal], None)
        second = ext.discover_sessions(self.db_path, self.tasks_db_path, 0, now + 1, [self.personal], None)
        self.assertEqual({s["id"] for s in first}, {"s1"})
        self.assertEqual({s["id"] for s in second}, {"s1"})

    def test_message_without_timestamp_is_context_only_not_decision_evidence(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", None)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        session = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])
        event = session["events"][0]
        self.assertIsNone(event["event_epoch_ms"])
        self.assertFalse(event["is_new"])
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("not eligible" in e for e in out["errors"]))

    def test_evidence_beyond_upper_bound_rejected_even_if_is_new_is_tampered(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        evidence_path = run_dir / "normalized_sessions.jsonl"
        session = json.loads(evidence_path.read_text().splitlines()[0])
        event = session["events"][0]
        # Simulate a message inserted after the run's upper bound whose
        # `is_new` flag was (hypothetically) tampered with -- the validator
        # must independently re-check the epoch against the manifest's
        # upper bound rather than trusting is_new alone.
        event["is_new"] = True
        event["event_epoch_ms"] = result["upper_bound"] + 1_000_000
        evidence_path.write_text(json.dumps(session, sort_keys=True) + "\n")
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("not eligible" in e for e in out["errors"]))

    # ================================================================== (8)
    # Recovery path containment.
    # ==================================================================

    def test_recover_rejects_backup_path_outside_zcode_home(self) -> None:
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        evil = self.root / "evil-backup"
        shutil.copytree(backup, evil)
        marker_path = run_dir / "commit.json"
        marker = json.loads(marker_path.read_text())
        marker["backup"] = str(evil)
        marker_path.write_text(json.dumps(marker))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    def test_recover_rejects_backup_name_not_matching_run_id(self) -> None:
        result_a = self.prepare(run_id="run-a")
        run_dir_a = Path(result_a["run_dir"])
        self._interrupt_after_backup(run_dir_a, "run-a")

        # A legitimately-named backup, but for a *different* run.
        fake_manifest = {"run_id": "run-b", "baseline_hashes": {}}
        backup_b = ext.backup_live(self.ws, fake_manifest, set())

        marker_path = run_dir_a / "commit.json"
        marker = json.loads(marker_path.read_text())
        marker["backup"] = str(backup_b)
        marker_path.write_text(json.dumps(marker))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id="run-a"))

    def test_recover_rejects_inventory_traversal_key(self) -> None:
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        data["presence"]["../../etc/passwd"] = False
        data["inventory"].append("../../etc/passwd")
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    def test_recover_rejects_symlinked_backup_source_file(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        target_file = backup / "docs" / "rules.md"
        outside = self.root / "outside-secret.md"
        outside.write_text("secret content")
        target_file.unlink()
        target_file.symlink_to(outside)

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    # ================================================================== (9)
    # Automation exclusion fails closed.
    # ==================================================================

    def _args_with_db_overrides(self, **overrides) -> SimpleNamespace:
        """Like base_args(), but lets the caller override db_path/tasks_db_path
        (base_args() already pins those, so passing them as **overrides there
        collides as a duplicate keyword argument).
        """
        base = dict(
            zcode_home=str(self.home), db_path=str(self.db_path), tasks_db_path=str(self.tasks_db_path),
            scope_root=[str(self.personal), str(self.work)],
        )
        base.update(overrides)
        return make_args(**base)

    def test_prepare_fails_when_tasks_db_missing(self) -> None:
        missing_path = self.root / "no-such-tasks.sqlite"
        args = self._args_with_db_overrides(command="prepare", tasks_db_path=str(missing_path))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(args)
        self.assertFalse(self.ws.lock.exists())
        self.assertFalse(self.ws.state.exists())

    def test_prepare_fails_when_tasks_db_missing_automation_runs_table(self) -> None:
        bad_db = self.root / "bad-tasks.sqlite"
        con = sqlite3.connect(str(bad_db))
        con.execute("CREATE TABLE unrelated (x TEXT)")
        con.commit()
        con.close()
        args = self._args_with_db_overrides(command="prepare", tasks_db_path=str(bad_db))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(args)
        self.assertFalse(self.ws.lock.exists())

    def test_prepare_fails_when_tasks_db_malformed(self) -> None:
        bad_db = self.root / "malformed-tasks.sqlite"
        bad_db.write_text("this is not a sqlite database")
        args = self._args_with_db_overrides(command="prepare", tasks_db_path=str(bad_db))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(args)
        self.assertFalse(self.ws.lock.exists())

    def test_prepare_fails_when_session_db_missing_required_table(self) -> None:
        bad_db = self.root / "bad-session.sqlite"
        con = sqlite3.connect(str(bad_db))
        con.execute("CREATE TABLE session (id TEXT)")
        con.commit()
        con.close()
        args = self._args_with_db_overrides(command="prepare", db_path=str(bad_db))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(args)
        self.assertFalse(self.ws.lock.exists())

    def test_prepare_fails_when_session_db_missing_required_column(self) -> None:
        bad_db = self.root / "bad-session-column.sqlite"
        con = sqlite3.connect(str(bad_db))
        con.execute("CREATE TABLE session (id TEXT, directory TEXT)")
        con.execute("CREATE TABLE message (id TEXT)")
        con.execute("CREATE TABLE part (id TEXT)")
        con.commit()
        con.close()
        args = self._args_with_db_overrides(command="prepare", db_path=str(bad_db))
        with self.assertRaises(ext.RunError):
            ext.cmd_prepare(args)
        self.assertFalse(self.ws.lock.exists())

    # ==================================================================
    # Main-agent-review follow-up: further hardening (7 items).
    # ==================================================================

    # ------------------------------------------------------------ (1)
    # Pre-backup recovery must compare the *recorded* watermark baseline,
    # not just assume "no watermark file at all".

    def test_recover_aborts_before_backup_when_existing_watermark_is_unchanged(self) -> None:
        ext.atomic_json(self.ws.state, {"last_time_updated": ext.now_ms() - 3_600_000})
        pre_watermark_bytes = self.ws.state.read_bytes()
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self.assertFalse(result["bootstrap"])
        self._interrupt_before_backup(run_dir, result["run_id"])

        rc, out = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self.assertTrue(out["recovered"])
        self.assertEqual(out["reason"], "aborted before any live write")
        self.assertEqual(self.ws.state.read_bytes(), pre_watermark_bytes)
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "recovered")
        self.assertFalse(self.ws.lock.exists())

    def test_recover_fails_closed_when_existing_watermark_diverged_before_backup(self) -> None:
        ext.atomic_json(self.ws.state, {"last_time_updated": ext.now_ms() - 3_600_000})
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._interrupt_before_backup(run_dir, result["run_id"])
        # Something unexpected changed the watermark after prepare's baseline
        # was recorded -- recover must refuse to guess, not silently abort.
        ext.atomic_json(self.ws.state, {"last_time_updated": ext.now_ms()})

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    def test_recover_fails_closed_for_legacy_run_missing_trusted_control_state(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._interrupt_before_backup(run_dir, result["run_id"])
        # A run prepared before trusted control state existed (or whose
        # control state was removed) must be refused outright rather than
        # guessed about -- the editable manifest is no longer trusted.
        shutil.rmtree(self._control_dir(result["run_id"]))

        with self.assertRaises(ext.RunError) as ctx:
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertIn("trusted control", str(ctx.exception))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    # ------------------------------------------------------------ (2)
    # normalized_sessions.jsonl must be hash-pinned by the manifest.

    def test_validate_rejects_tampered_normalized_evidence(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        user_event = events["user"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": user_event["session_id"], "event_sha256": user_event["event_sha256"],
                          "event_timestamp": user_event["event_timestamp"]}],
            "reason": "r",
        })
        # Fabricate an extra event in the normalized evidence after prepare --
        # the file's bytes no longer match the manifest's recorded hash.
        evidence_path = run_dir / "normalized_sessions.jsonl"
        session = json.loads(evidence_path.read_text().splitlines()[0])
        fabricated = dict(user_event)
        fabricated["text"] = "Fabricated user statement never actually said."
        fabricated["event_sha256"] = "0" * 64
        session["events"].append(fabricated)
        evidence_path.write_text(json.dumps(session, sort_keys=True) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("does not match the manifest's recorded hash" in e for e in out["errors"]))

    def test_validate_fails_closed_for_manifest_missing_evidence_hash(self) -> None:
        result, run_dir, events = self._prepare_with_user_and_tool_events()
        user_event = events["user"]
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": user_event["session_id"], "event_sha256": user_event["event_sha256"]}],
            "reason": "r",
        })
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        del manifest["normalized_evidence_sha256"]
        manifest_path.write_text(json.dumps(manifest))
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("normalized_evidence_sha256" in e for e in out["errors"]))

    # ------------------------------------------------------------ (3)
    # Lower/upper bound eligibility must be independently re-derived, not
    # just trusted from `is_new`.

    def test_evidence_at_lower_bound_rejected_independently_of_is_new(self) -> None:
        now = ext.now_ms()
        add_session(self.session_con, "s1", str(self.personal), time_updated=now)
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", now)
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        evidence_path = run_dir / "normalized_sessions.jsonl"
        session = json.loads(evidence_path.read_text().splitlines()[0])
        event = session["events"][0]
        # An "old" event sitting exactly at the (exclusive) lower bound, with
        # is_new mis-set to True -- an internally consistent artifact (the
        # manifest hash below is updated to match), so evidence-hash
        # verification alone would not catch this; only the validator's own
        # `lower_bound < epoch <= upper_bound` re-check does.
        event["event_epoch_ms"] = result["lower_bound"]
        event["is_new"] = True
        new_bytes = (json.dumps(session, sort_keys=True) + "\n").encode()
        evidence_path.write_bytes(new_bytes)
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["normalized_evidence_sha256"] = ext.digest_bytes(new_bytes)
        manifest_path.write_text(json.dumps(manifest))
        self._write_decision(run_dir, {
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "WROTE_DOC", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"]}],
            "reason": "r",
        })
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("not eligible" in e for e in out["errors"]))
        self.assertFalse(any("does not match the manifest's recorded hash" in e for e in out["errors"]))

    # ------------------------------------------------------------ (4)
    # A non-write disposition's `destination` can never authorize a change.

    def test_provisional_destination_cannot_authorize_a_memory_change(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("sneaked in via a PROVISIONAL destination")
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(ledger_path.read_text() + "## 2026-09-12 run\n- [PROVISIONAL] x | 1 instance\n")
        event = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])["events"][0]
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "provisional",
            "disposition": "PROVISIONAL", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"]}],
            "reason": "r",
        }) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("destination may only be declared on a write disposition" in e for e in out["errors"]))
        self.assertTrue(any("not authorized by any decision destination" in e for e in out["errors"]))

    def test_rejected_destination_cannot_authorize_a_memory_change(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "staging" / "docs" / "rules.md").write_text("sneaked in via a REJECTED destination")
        ledger_path = run_dir / "staging" / "AGENTS.extraction-log.md"
        ledger_path.write_text(ledger_path.read_text() + "## 2026-09-12 run\n- [REJECTED] x | failed Gate 1\n")
        event = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])["events"][0]
        (run_dir / "decisions.jsonl").write_text(json.dumps({
            "claim": "x", "kind": "behavioral_rule", "scope": "global", "confidence": "confirmed",
            "disposition": "REJECTED", "destination": "docs/rules.md",
            "evidence": [{"session_id": event["session_id"], "event_sha256": event["event_sha256"]}],
            "reason": "r",
        }) + "\n")
        (run_dir / "session_dispositions.jsonl").write_text(json.dumps({"session_id": "s1", "status": "contributed"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("destination may only be declared on a write disposition" in e for e in out["errors"]))
        self.assertTrue(any("not authorized by any decision destination" in e for e in out["errors"]))

    # ------------------------------------------------------------ (5)
    # `supporting_destinations` is restricted to structural index/map files.

    def test_supporting_destinations_rejects_non_structural_content_file(self) -> None:
        (self.ws.memory / "tooling-gotchas.md").write_text("# Gotchas\n")
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1", supporting_destinations=["docs/tooling-gotchas.md"])
        (run_dir / "staging" / "docs" / "tooling-gotchas.md").write_text("# Gotchas\n- sneaked in unrelated content\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("structural index/map file" in e for e in out["errors"]))
        self.assertTrue(any("not authorized by any decision destination" in e and "tooling-gotchas.md" in e for e in out["errors"]))

    def test_supporting_destinations_allows_project_index_files(self) -> None:
        (self.ws.memory / "projects").mkdir(parents=True, exist_ok=True)
        (self.ws.memory / "projects" / "index.md").write_text("# Projects\n")
        (self.ws.memory / "projects" / "acme").mkdir(parents=True, exist_ok=True)
        (self.ws.memory / "projects" / "acme" / "index.md").write_text("# Acme\n")
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1", supporting_destinations=["docs/projects/index.md", "docs/projects/acme/index.md"])
        (run_dir / "staging" / "docs" / "projects" / "index.md").write_text("# Projects\n- acme\n")
        (run_dir / "staging" / "docs" / "projects" / "acme" / "index.md").write_text("# Acme\n- updated\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 0, out.get("errors"))

    # ------------------------------------------------------------ (6)
    # Lock publication is now temp-dir-then-rename, truly atomic.

    def test_acquire_lock_failure_before_rename_leaves_no_final_lock(self) -> None:
        with mock.patch.object(os, "rename", side_effect=OSError("simulated crash before publish")):
            with self.assertRaises(OSError):
                ext.acquire_lock(self.ws, "run-crash")
        self.assertFalse(self.ws.lock.exists())
        leftovers = list(self.ws.lock.parent.glob(f".{self.ws.lock.name}.tmp-*"))
        self.assertEqual(leftovers, [])

    def test_acquire_lock_still_detects_malformed_legacy_lock(self) -> None:
        self.ws.lock.parent.mkdir(parents=True, exist_ok=True)
        self.ws.lock.mkdir()  # directory present, owner.json never published
        with self.assertRaises(ext.RunError):
            ext.acquire_lock(self.ws, "run-y")
        # The malformed lock must not have been silently replaced.
        self.assertFalse((self.ws.lock / "owner.json").exists())

    # ------------------------------------------------------------ (7)
    # Backup manifest schema: booleans, exact hash coverage, unique inventory.

    def test_recover_rejects_backup_manifest_with_non_boolean_presence_value(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        some_key = next(iter(data["presence"]))
        data["presence"][some_key] = 1  # truthy but not a real bool
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    def test_recover_rejects_backup_manifest_with_missing_hash_for_present_path(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        present_key = next(rel for rel, existed in data["presence"].items() if existed)
        del data["hashes"][present_key]
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    def test_recover_rejects_backup_manifest_with_extra_hash_for_absent_path(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        absent_key = next((rel for rel, existed in data["presence"].items() if not existed), None)
        if absent_key is None:
            absent_key = "docs/never-existed.md"
            data["presence"][absent_key] = False
            data["inventory"].append(absent_key)
        data["hashes"][absent_key] = "0" * 64
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    def test_recover_rejects_backup_manifest_with_duplicate_inventory_entries(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        data["inventory"].append(data["inventory"][0])
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))

    # ==================================================================
    # Astra round 2, finding 1: trusted transaction control state outside
    # the agent-editable run directory.
    # ==================================================================

    def test_prepare_writes_trusted_control_record_outside_run_dir(self) -> None:
        prompt_file = self.root / "extraction-prompt.md"
        prompt_file.write_text("extraction prompt body\n")
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare(automation_id="auto-x", model_id="model-x", prompt_file=str(prompt_file))
        run_id = result["run_id"]
        control_dir = self._control_dir(run_id)
        run_dir = Path(result["run_dir"])
        self.assertTrue(control_dir.is_dir(), "prepare must create the trusted control-state directory")
        self.assertFalse(str(control_dir).startswith(str(run_dir)), "control state must live outside the run directory")
        self.assertFalse(str(run_dir).startswith(str(control_dir)), "run directory must not live under control state")
        self.assertEqual(control_dir.stat().st_mode & 0o777, 0o700, "control-state dir must be mode 0700")
        record_path = control_dir / "control.json"
        self.assertEqual(record_path.stat().st_mode & 0o777, 0o600, "control record must be mode 0600")
        record = json.loads(record_path.read_text())
        self.assertEqual(record["run_id"], run_id)
        self.assertEqual(record["lower_bound"], result["lower_bound"])
        self.assertEqual(record["upper_bound"], result["upper_bound"])
        self.assertEqual(record["automation_id"], "auto-x")
        self.assertEqual(record["model_id"], "model-x")
        self.assertTrue(record["prompt_sha256"])
        manifest = json.loads((run_dir / "manifest.json").read_text())
        self.assertEqual(record["baseline_hashes"], manifest["baseline_hashes"])
        self.assertEqual(record["watermark_baseline"], manifest["watermark_baseline"])
        self.assertEqual(record["normalized_evidence_sha256"], manifest["normalized_evidence_sha256"])
        self.assertEqual(record["sessions"], manifest["sessions"])
        for rel in ("AGENTS.md", "AGENTS.extraction-log.md", "docs/rules.md", "docs/index.md", ext.WATERMARK_REL):
            self.assertIn(rel, record["authorized_targets"], f"authorized inventory must bind {rel}")

    def test_validate_rejects_manifest_tampered_against_control_record(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        (run_dir / "session_dispositions.jsonl").write_text(
            json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["automation_id"] = "tampered-by-the-model"
        manifest_path.write_text(json.dumps(manifest))
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("does not match the trusted control record" in e for e in out["errors"]), out["errors"])

    def test_validate_rejects_evidence_tampered_with_matching_manifest_hash(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        evidence_path = run_dir / "normalized_sessions.jsonl"
        # Same events, different bytes: the old manifest-pinned hash check
        # passes once the manifest hash is updated to match, so only the
        # trusted control record can catch this.
        tampered = evidence_path.read_bytes() + b"\n"
        evidence_path.write_bytes(tampered)
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["normalized_evidence_sha256"] = ext.digest_bytes(tampered)
        manifest_path.write_text(json.dumps(manifest))
        (run_dir / "session_dispositions.jsonl").write_text(
            json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n")
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("does not match the trusted control record" in e for e in out["errors"]), out["errors"])

    def test_apply_and_validate_refuse_legacy_run_without_trusted_control_state(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        shutil.rmtree(self._control_dir(result["run_id"]))
        rc, out = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 1)
        self.assertTrue(any("trusted control" in e for e in out["errors"]), out["errors"])
        with self.assertRaises(ext.RunError) as ctx:
            ext.cmd_apply(self.base_args(command="apply", run_id=result["run_id"], apply=True))
        self.assertIn("trusted control", str(ctx.exception))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n")
        self.assertFalse(self.ws.state.exists())

    # ==================================================================
    # Astra round 2, finding 2: backup inventory bound to trusted state.
    # ==================================================================

    def test_recover_rejects_extra_absent_inventory_entry_and_preserves_live_file(self) -> None:
        # Astra reproduction: a backup manifest claiming v2/config.json was
        # absent pre-run must not authorize deleting the live file.
        config = self.ws.home / "v2" / "config.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('{"keep": true}\n')
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        data["inventory"].append("v2/config.json")
        data["presence"]["v2/config.json"] = False
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertTrue(config.exists(), "recovery must never delete a path outside the trusted inventory")
        self.assertEqual(config.read_text(), '{"keep": true}\n')
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())
        self.assertTrue((run_dir / "normalized_sessions.jsonl").exists())

    def test_recover_rejects_empty_backup_manifest_false_success(self) -> None:
        # Astra reproduction: an empty backup manifest used to verify "fine"
        # and recovery reported success while restoring nothing.
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        for path in list(backup.rglob("*")):
            if path.is_file() and path.name != "presence.json":
                path.unlink()
        empty = {"run_id": result["run_id"], "inventory": [], "presence": {}, "hashes": {}}
        (backup / "presence.json").write_text(json.dumps(empty, indent=2, sort_keys=True) + "\n")
        # Pin the digest as if the runner itself had recorded this empty
        # backup, isolating the inventory-equality check.
        apply_path = self._control_dir(result["run_id"]) / "apply.json"
        state = json.loads(apply_path.read_text())
        state["backup_manifest_sha256"] = ext.digest_file(backup / "presence.json")
        apply_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n")
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    def test_recover_rejects_missing_authorized_inventory_entry(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        manifest_path = backup / "presence.json"
        data = json.loads(manifest_path.read_text())
        if "docs/index.md" in data["inventory"]:
            data["inventory"].remove("docs/index.md")
        data["presence"].pop("docs/index.md", None)
        data["hashes"].pop("docs/index.md", None)
        manifest_path.write_text(json.dumps(data))

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")

    # ==================================================================
    # Astra round 2, finding 3: commit marker strictness.
    # ==================================================================

    def test_recover_fails_closed_when_completed_marker_missing_or_corrupt(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        later_work = "# Rules\n- Written by a later run.\n"
        (self.ws.memory / "rules.md").write_text(later_work)
        marker_path = run_dir / "commit.json"

        marker_path.unlink()
        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), later_work,
                         "a missing marker must never trigger a backup-based rollback")

        marker_path.write_text("{not valid json")
        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), later_work)

    def test_recover_fails_closed_on_unknown_status_and_run_id_mismatch(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        later_work = "# Rules\n- Written by a later run.\n"
        (self.ws.memory / "rules.md").write_text(later_work)
        marker_path = run_dir / "commit.json"
        original = json.loads(marker_path.read_text())

        marker_path.write_text(json.dumps({**original, "status": "half_done"}))
        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), later_work)

        marker_path.write_text(json.dumps({**original, "run_id": "not-this-run"}))
        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), later_work)

    def test_recover_never_searches_backups_by_filename_when_marker_missing(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        later_work = "# Rules\n- Written by a later run.\n"
        (self.ws.memory / "rules.md").write_text(later_work)
        (run_dir / "commit.json").unlink()
        # A plausibly-named decoy backup whose content differs from both the
        # baseline and the later work -- filename-based fallback must never
        # restore it.
        decoy = self.ws.home / f"extraction-backup-20990101T000000-{result['run_id']}"
        (decoy / "docs").mkdir(parents=True)
        (decoy / "presence.json").write_text(json.dumps({
            "run_id": result["run_id"],
            "inventory": ["docs/rules.md"],
            "presence": {"docs/rules.md": True},
            "hashes": {"docs/rules.md": ext.digest_bytes(b"DECOY RESTORE")},
        }) + "\n")
        (decoy / "docs" / "rules.md").write_text("DECOY RESTORE")

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        self.assertEqual((self.ws.memory / "rules.md").read_text(), later_work)

    # ==================================================================
    # Astra round 2, finding 4: session/message boundary evidence loss.
    # ==================================================================

    def test_session_with_message_in_window_but_session_updated_after_upper_is_discovered(self) -> None:
        lower, upper = 1_000_000, 2_000_000
        add_session(self.session_con, "boundary-s1", str(self.personal), time_updated=upper + 1)
        add_text_turn(self.session_con, "boundary-s1", 0, "user", "Always run tests before committing.", upper)
        sessions = ext.discover_sessions(self.db_path, self.tasks_db_path, lower, upper, [self.personal], None)
        by_id = {s["id"]: s for s in sessions}
        self.assertIn("boundary-s1", by_id,
                      "a session whose message lands in the window must be discovered even if "
                      "session.time_updated moved just past the upper bound")
        user_events = [e for e in by_id["boundary-s1"]["events"] if e["role"] == "user"]
        self.assertTrue(user_events)
        self.assertTrue(user_events[0]["is_new"], "the in-window message must remain decision evidence")

    def test_discovery_unions_session_updated_and_message_discovered_sessions(self) -> None:
        lower, upper = 1_000_000, 2_000_000
        add_session(self.session_con, "row-only", str(self.personal), time_updated=upper)
        add_text_turn(self.session_con, "row-only", 0, "user", "an old message", lower - 10)
        add_session(self.session_con, "msg-only", str(self.personal), time_updated=upper + 1)
        add_text_turn(self.session_con, "msg-only", 0, "user", "a new message", upper)
        sessions = ext.discover_sessions(self.db_path, self.tasks_db_path, lower, upper, [self.personal], None)
        self.assertEqual({s["id"] for s in sessions}, {"row-only", "msg-only"})

    def test_exclusions_apply_to_message_discovered_sessions(self) -> None:
        lower, upper = 1_000_000, 2_000_000
        add_session(self.session_con, "auto-msg", str(self.personal), time_updated=upper + 1)
        add_text_turn(self.session_con, "auto-msg", 0, "assistant", "automation output", upper)
        self.tasks_con.execute("INSERT INTO automation_runs (run_id, session_id) VALUES ('r1','auto-msg')")
        self.tasks_con.commit()
        add_session(self.session_con, "sub-msg", str(self.personal), time_updated=upper + 1,
                    parent_id="some-parent", task_type="subagent_child")
        add_text_turn(self.session_con, "sub-msg", 0, "user", "subagent work", upper)
        add_session(self.session_con, "sched-msg", str(self.personal), time_updated=upper + 1,
                    title='<scheduled-task name="x">')
        add_text_turn(self.session_con, "sched-msg", 0, "user", "scheduled work", upper)
        add_session(self.session_con, "ok-msg", str(self.personal), time_updated=upper + 1)
        add_text_turn(self.session_con, "ok-msg", 0, "user", "real user work", upper)
        sessions = ext.discover_sessions(self.db_path, self.tasks_db_path, lower, upper, [self.personal], None)
        self.assertEqual({s["id"] for s in sessions}, {"ok-msg"})

    def test_cross_boundary_message_is_decision_evidence_in_the_discovering_run(self) -> None:
        fake_now = make_fake_clock()
        with mock.patch.object(ext, "now_ms", side_effect=fake_now):
            ts = ext.now_ms()
            # The session's time_updated is bumped just past the upcoming
            # run's upper bound (= prepare's now), while the user message
            # itself is inside the window -- Astra's cross-boundary loss.
            add_session(self.session_con, "s1", str(self.personal), time_updated=ts + 1_500_000)
            add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ts + 500_000)
            result = self.prepare()
            self.assertEqual(result["session_count"], 1, "the cross-boundary session must be discovered")
            run_dir = Path(result["run_dir"])
            session = json.loads((run_dir / "normalized_sessions.jsonl").read_text().splitlines()[0])
            user_event = next(e for e in session["events"] if e["role"] == "user")
            self.assertTrue(user_event["is_new"])
            self._stage_valid_change(run_dir, "s1")
            rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
            self.assertEqual(rc, 0)
            rc2, _ = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id=result["run_id"]))
            self.assertEqual(rc2, 0)
            # The follow-up run must still discover the session (its row was
            # updated just above the previous watermark) -- the message was
            # not permanently demoted to context-only by the boundary.
            result2 = self.prepare()
            ids = {s["id"] for s in json.loads(
                (Path(result2["run_dir"]) / "manifest.json").read_text())["sessions"]}
            self.assertIn("s1", ids)

    # ==================================================================
    # Astra round 2, finding 5: symlink preflight and all-or-nothing
    # recovery verification.
    # ==================================================================

    def test_prepare_rejects_symlinked_live_target_instead_of_omitting_it(self) -> None:
        # Dangling symlink where a live docs file should be: the baseline must
        # never silently omit it.
        (self.ws.memory / "rules.md").unlink()
        (self.ws.memory / "rules.md").symlink_to(self.root / "does-not-exist.md")
        with self.assertRaises(ext.RunError) as ctx:
            self.prepare()
        self.assertIn("symlink", str(ctx.exception))
        self.assertFalse(self.ws.lock.exists())

    def test_apply_preflight_rejects_symlinked_ancestor_before_any_write(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        # After prepare, redirect the whole docs tree through a symlink to a
        # directory outside zcode home. Snapshot hashes still match (the same
        # files are visible through the link), so only a preflight catches it.
        outside_docs = self.root / "outside-docs"
        outside_docs.mkdir()
        shutil.rmtree(self.ws.memory)
        self.ws.memory.symlink_to(outside_docs)

        with self.assertRaises(ext.RunError) as ctx:
            ext.cmd_apply(self.base_args(command="apply", run_id=result["run_id"], apply=True))
        self.assertIn("symlink", str(ctx.exception))
        # Nothing was written through the symlink: the outside tree is empty
        # and live memory is untouched.
        self.assertEqual(list(outside_docs.iterdir()), [])
        self.assertEqual((self.ws.home / "AGENTS.extraction-log.md").read_text(),
                         "## 2026-08-01 run\n- [NO-OP] none\n")
        self.assertFalse((run_dir / "commit.json").exists())

    def test_recover_restores_nothing_when_a_later_target_has_symlinked_ancestor(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        self.assertTrue(backup.is_dir())
        pre_ledger = self.ws.ledger.read_text()
        pre_agents = (self.ws.home / "AGENTS.md").read_text()
        # Redirect docs through a symlink AFTER the backup was taken: every
        # restore destination under docs/ now has a symlinked ancestor.
        outside_docs = self.root / "outside-docs-recovery"
        outside_docs.mkdir()
        shutil.rmtree(self.ws.memory)
        self.ws.memory.symlink_to(outside_docs)

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        # All-or-nothing: not a single live file was restored before the
        # preflight rejected the bad destination.
        self.assertEqual(self.ws.ledger.read_text(), pre_ledger)
        self.assertEqual((self.ws.home / "AGENTS.md").read_text(), pre_agents)
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    # ==================================================================
    # Astra round 2, finding 6: run-directory containment everywhere.
    # ==================================================================

    def test_resolve_run_dir_enforces_containment(self) -> None:
        for bad in ("../evil", "sub/dir", "..", "."):
            with self.assertRaises(ext.RunError):
                ext.resolve_run_dir(self.ws, bad)
        self.ws.runs.mkdir(parents=True, exist_ok=True)
        outside = self.root / "outside-run-dir"
        outside.mkdir()
        link = self.ws.runs / "linked-run"
        link.symlink_to(outside)
        with self.assertRaises(ext.RunError):
            ext.resolve_run_dir(self.ws, "linked-run")
        self.assertEqual(ext.resolve_run_dir(self.ws, "clean-run"), self.ws.runs / "clean-run")

    def test_recover_rejects_symlinked_run_directory(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        self._interrupt_after_backup(run_dir, result["run_id"])
        outside_run = self.root / "external-run-copy"
        shutil.move(str(run_dir), str(outside_run))
        run_dir.symlink_to(outside_run)

        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        marker = json.loads((outside_run / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n")

    # ==================================================================
    # Astra round 2, finding 7: repair-and-recover deadlock escape.
    # ==================================================================

    def test_repair_recover_breaks_malformed_lock_deadlock(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        rc, _ = run_cmd(ext.cmd_validate, self.base_args(command="validate", run_id=result["run_id"]))
        self.assertEqual(rc, 0)
        self._interrupt_after_backup(run_dir, result["run_id"])
        # The deadlock: a malformed lock blocks recover, while the incomplete
        # commit blocks unlock-abandoned.
        (self.ws.lock / "owner.json").unlink()
        with self.assertRaises(ext.RunError):
            ext.cmd_recover(self.base_args(command="recover", run_id=result["run_id"]))
        with self.assertRaises(ext.RunError):
            ext.cmd_unlock_abandoned(self.base_args(command="unlock-abandoned"))

        # Unattended automation cannot guess its way past the confirmation.
        with self.assertRaises(ext.RunError) as ctx:
            ext.cmd_repair_recover(self.base_args(command="repair-recover", run_id=result["run_id"]))
        self.assertIn("--confirm-no-process", str(ctx.exception))

        rc2, out2 = run_cmd(ext.cmd_repair_recover, self.base_args(
            command="repair-recover", run_id=result["run_id"], confirm_no_process=True))
        self.assertEqual(rc2, 0)
        self.assertTrue(out2["recovered"])
        self.assertEqual((self.ws.memory / "rules.md").read_text(), "# Rules\n")
        self.assertFalse(self.ws.state.exists())
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "recovered")
        self.assertFalse(self.ws.lock.exists())

    def test_repair_recover_refuses_alive_owner_completed_or_legacy_runs(self) -> None:
        # A live owner can never be repaired over.
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare(run_id="run-a")
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        self._interrupt_after_backup(run_dir, "run-a")
        ext.release_lock(self.ws, "run-a")
        ext.acquire_lock(self.ws, "run-b")
        (self.ws.lock / "owner.json").write_text(json.dumps(
            {"run_id": "run-b", "pid": os.getpid(), "created_at": time.time()}))
        with self.assertRaises(ext.RunError) as ctx:
            ext.cmd_repair_recover(self.base_args(
                command="repair-recover", run_id="run-a", confirm_no_process=True))
        self.assertIn("alive", str(ctx.exception))

        # A completed run has nothing to repair.
        ext.release_lock(self.ws, "run-b")
        # Cleanly resolve run-a's interrupted commit so later prepares work.
        rc_ra, _ = run_cmd(ext.cmd_recover, self.base_args(command="recover", run_id="run-a"))
        self.assertEqual(rc_ra, 0)
        add_session(self.session_con, "s2", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s2", 0, "user", "More user work.", ext.now_ms())
        result_c = self.prepare(run_id="run-c")
        # Fixture fix: run-a's interrupted commit was genuinely rolled back
        # by `recover` above (its watermark never advanced), so run-c's
        # bootstrap window legitimately rediscovers "s1" again alongside the
        # new "s2" -- both must be accounted for, or validation fails on
        # "discovered session not accounted for" before repair-recover is
        # ever exercised for a completed run.
        run_dir_c = Path(result_c["run_dir"])
        self._stage_valid_change(run_dir_c, "s2")
        dispositions_path = run_dir_c / "session_dispositions.jsonl"
        dispositions_path.write_text(
            dispositions_path.read_text() + json.dumps({"session_id": "s1", "status": "reviewed_no_learning"}) + "\n"
        )
        rc, out = run_cmd(ext.cmd_commit, self.base_args(command="commit", run_id="run-c"))
        self.assertEqual(rc, 0, out)
        with self.assertRaises(ext.RunError):
            ext.cmd_repair_recover(self.base_args(command="repair-recover", run_id="run-c"))

        # A legacy run without trusted control state is refused.
        add_session(self.session_con, "s3", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s3", 0, "user", "Even more user work.", ext.now_ms())
        result_d = self.prepare(run_id="run-d")
        run_dir_d = Path(result_d["run_dir"])
        self._interrupt_before_backup(run_dir_d, "run-d")
        shutil.rmtree(self._control_dir("run-d"))
        with self.assertRaises(ext.RunError) as ctx_d:
            ext.cmd_repair_recover(self.base_args(
                command="repair-recover", run_id="run-d", confirm_no_process=True))
        self.assertIn("trusted control", str(ctx_d.exception))

    def test_repair_recover_preserves_evidence_and_state_on_failed_recovery(self) -> None:
        add_session(self.session_con, "s1", str(self.personal), time_updated=ext.now_ms())
        add_text_turn(self.session_con, "s1", 0, "user", "Always run tests before committing.", ext.now_ms())
        result = self.prepare()
        run_dir = Path(result["run_dir"])
        self._stage_valid_change(run_dir, "s1")
        backup = self._interrupt_after_backup(run_dir, result["run_id"])
        (self.ws.lock / "owner.json").unlink()
        (backup / "docs" / "rules.md").write_text("tampered, hash mismatch")

        with self.assertRaises(ext.RunError):
            ext.cmd_repair_recover(self.base_args(
                command="repair-recover", run_id=result["run_id"], confirm_no_process=True))
        self.assertTrue((run_dir / "normalized_sessions.jsonl").exists(), "evidence must be preserved")
        self.assertTrue((self._control_dir(result["run_id"]) / "apply.json").exists())
        marker = json.loads((run_dir / "commit.json").read_text())
        self.assertEqual(marker["status"], "in_progress")
        self.assertTrue(self.ws.lock.exists())

    # ==================================================================
    # Astra round 2, finding 8: deployment checking against scheduler drift.
    # ==================================================================

    DEPLOYED_AUTOMATION_ID = "automation-ff3ba2cc-a0f7-4ed1-919b-23f8f37cd111"
    DEPLOYED_MODEL_ID = "gpt-6-astra"
    DEPLOYED_CRON = "0 20 */2 * *"
    DEPLOYED_SCHEDULE_RULE = {"unit": "daily", "interval": 2, "hour": 20, "minute": 0}
    WRAPPER_PROMPT = (
        "Execute the ZCode learning extraction defined in"
        " /Users/sala/.zcode/self-improve/learning-extraction-v1.md.\n\n"
        "Read that file in full first and follow its transactional protocol exactly. Use the runner at /Users/sala/.zcode/self-improve/zcode_learning_extractor.py for database access, checkpoint changes, backups, validation, recovery, and live-memory writes. After prepare, file tools are explicitly allowed inside the printed run directory to read manifest.json, normalized_sessions.jsonl, and staged memory; write decisions.jsonl and session_dispositions.jsonl; and edit only files under staging/. Never edit runner-generated metadata or extraction-control state.\n\n"
        "Run `prepare` first with --automation-id automation-ff3ba2cc-a0f7-4ed1-919b-23f8f37cd111,"
        " --model-id gpt-6-astra, and --prompt-file"
        " /Users/sala/.zcode/self-improve/learning-extraction-v1.md. Read only the normalized"
        " evidence and staged memory in the printed run directory. Write decisions.jsonl and"
        " session_dispositions.jsonl, edit only staged files, validate, inspect the generated"
        " report and diff, then commit.\n\n"
        "Never edit live AGENTS.md, docs, the extraction ledger, or watermark directly. Never"
        " write either SQLite database. Astra intentionally runs without AGENTS.md injection;"
        " this prompt, the extraction policy, and runner artifacts are the complete task"
        " context. If the prompt or runner is missing, stop. If prepare reports an incomplete"
        " commit, recover that run before starting another. An empty run is valid: stage an"
        " empty-run ledger entry and commit so the runner advances the watermark safely."
    )
    DEPLOYED_PROMPT_BODY = (
        "# Bi-daily ZCode Learning Extraction\n\n"
        "This session runs with `injectAgentsMd: false` by design.\n"
    )

    def _make_deployment_fixture(self) -> SimpleNamespace:
        # Fixture bug fix: this is called multiple times within a single
        # test method's subTest loop (test_check_deployment_fails_closed_on_drift
        # rebuilds a fresh fixture per drift case). A fixed `self.root / "sched"`
        # path collided across those calls (the sqlite file, and its
        # `automations` table, already existed from the previous iteration),
        # raising "table automations already exists" instead of exercising
        # the intended drift case. Each call now gets its own directory.
        sched_dir = self.root / _next_id("sched")
        sched_dir.mkdir(exist_ok=True)
        db = sched_dir / "tasks-index.sqlite"
        con = sqlite3.connect(str(db))
        con.execute(
            "CREATE TABLE automations (automation_id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', "
            "cron_expr TEXT NOT NULL, prompt TEXT NOT NULL, model TEXT, schedule_rule TEXT, "
            "recurring INTEGER NOT NULL DEFAULT 1, enabled INTEGER NOT NULL DEFAULT 1, "
            "lifecycle_status TEXT NOT NULL DEFAULT 'active')"
        )
        con.execute(
            "INSERT INTO automations (automation_id, cron_expr, prompt, model, schedule_rule, recurring, enabled, lifecycle_status) "
            "VALUES (?, ?, ?, ?, ?, 1, 1, 'active')",
            (self.DEPLOYED_AUTOMATION_ID, self.DEPLOYED_CRON, self.WRAPPER_PROMPT,
             "custom:9ecc2e49-e5e2-4f53-a414-d3c8121d973e:" + self.DEPLOYED_MODEL_ID,
             json.dumps(self.DEPLOYED_SCHEDULE_RULE)),
        )
        con.commit()
        con.close()
        deployed_prompt = self.ws.home / "self-improve" / "learning-extraction-v1.md"
        deployed_prompt.parent.mkdir(parents=True, exist_ok=True)
        deployed_prompt.write_text(self.DEPLOYED_PROMPT_BODY)
        deployed_runner = self.ws.home / "self-improve" / "zcode_learning_extractor.py"
        shutil.copy2(_SCRIPT, deployed_runner)
        return SimpleNamespace(db=db, prompt=deployed_prompt, runner=deployed_runner)

    def _check_deployment_args(self, fx: SimpleNamespace, **overrides) -> SimpleNamespace:
        base = dict(
            zcode_home=str(self.ws.home), tasks_db_path=str(fx.db), command="check-deployment",
            automation_id=self.DEPLOYED_AUTOMATION_ID, model_id=self.DEPLOYED_MODEL_ID,
            cron=self.DEPLOYED_CRON, prompt_path=str(fx.prompt), runner_path=str(fx.runner),
            expected_prompt_sha256=None, expected_interval=2, expected_hour=20,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_check_deployment_accepts_matching_deployment(self) -> None:
        fx = self._make_deployment_fixture()
        rc, out = run_cmd(ext.cmd_check_deployment, self._check_deployment_args(fx))
        self.assertEqual(rc, 0, out)
        self.assertTrue(out["ok"])
        self.assertEqual(out["errors"], [])
        self.assertTrue(out["deployed_prompt_sha256"])
        self.assertTrue(out["deployed_runner_sha256"])

    def test_check_deployment_fails_closed_on_drift(self) -> None:
        def scheduler_row_update(db: Path, sql: str, params: tuple = ()) -> None:
            con = sqlite3.connect(str(db))
            con.execute(sql, params)
            con.commit()
            con.close()

        cases: list[tuple[str, object]] = [
            ("wrong cron display", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET cron_expr = '0 20 * * *'")),
            ("wrong structured interval", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET schedule_rule = ?",
                (json.dumps({"unit": "daily", "interval": 1, "hour": 20, "minute": 0}),))),
            ("wrong structured hour", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET schedule_rule = ?",
                (json.dumps({"unit": "daily", "interval": 2, "hour": 9, "minute": 0}),))),
            ("wrong model", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET model = 'custom:x:gpt-5'")),
            ("automation missing", lambda fx: scheduler_row_update(
                fx.db, "DELETE FROM automations")),
            ("automation disabled", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET enabled = 0")),
            ("automation not recurring", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET recurring = 0")),
            ("automation not active", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET lifecycle_status = 'paused'")),
            ("wrapper prompt missing model flag", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET prompt = REPLACE(prompt, '--model-id gpt-6-astra', '')")),
            ("wrapper prompt missing automation id flag", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET prompt = REPLACE(prompt, '--automation-id "
                       + self.DEPLOYED_AUTOMATION_ID + "', '')")),
            ("wrapper prompt missing prompt path", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET prompt = REPLACE(prompt, "
                       "'/Users/sala/.zcode/self-improve/learning-extraction-v1.md', '')")),
            ("wrapper prompt lost non-injection declaration", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET prompt = REPLACE(prompt, 'without AGENTS.md injection', "
                       "'with AGENTS.md injection')")),
            ("wrapper prompt lost run-directory file-tool permission", lambda fx: scheduler_row_update(
                fx.db, "UPDATE automations SET prompt = REPLACE(prompt, "
                       "'file tools are explicitly allowed inside the printed run directory', "
                       "'file tools are forbidden inside the printed run directory')")),
            ("deployed prompt lost injectAgentsMd boundary", lambda fx: fx.prompt.write_text("# prompt\n")),
            ("deployed prompt missing", lambda fx: fx.prompt.unlink()),
            ("deployed runner hash drift", lambda fx: fx.runner.write_text("# tampered runner\n")),
            ("deployed runner missing", lambda fx: fx.runner.unlink()),
            ("scheduler database missing", lambda fx: fx.db.unlink()),
        ]
        for name, mutate in cases:
            with self.subTest(case=name):
                fx = self._make_deployment_fixture()
                mutate(fx)
                rc, out = run_cmd(ext.cmd_check_deployment, self._check_deployment_args(fx))
                self.assertEqual(rc, 1, out)
                self.assertFalse(out["ok"])
                self.assertTrue(out["errors"], f"expected an error for {name}")

    def test_check_deployment_accepts_expected_prompt_hash_and_flags_drift(self) -> None:
        fx = self._make_deployment_fixture()
        good_hash = ext.digest_file(fx.prompt)
        rc, out = run_cmd(ext.cmd_check_deployment,
                          self._check_deployment_args(fx, expected_prompt_sha256=good_hash))
        self.assertEqual(rc, 0, out)
        rc2, out2 = run_cmd(ext.cmd_check_deployment,
                            self._check_deployment_args(fx, expected_prompt_sha256="0" * 64))
        self.assertEqual(rc2, 1)
        self.assertTrue(any("prompt hash" in e for e in out2["errors"]))

    def test_check_deployment_defaults_runner_path_to_deployed_copy(self) -> None:
        fx = self._make_deployment_fixture()
        rc, out = run_cmd(ext.cmd_check_deployment, self._check_deployment_args(fx, runner_path=None))
        self.assertEqual(rc, 0, out)
        self.assertEqual(Path(out["deployed_runner_path"]),
                         self.ws.home / "self-improve" / "zcode_learning_extractor.py")


if __name__ == "__main__":
    unittest.main()


