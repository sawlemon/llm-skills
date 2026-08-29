"""CLI behavior: offline determinism, config validation, secret handling."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from hindsight_bench import cli
from hindsight_bench.config import BenchConfig, from_args
from hindsight_bench.runner import run_bench
from hindsight_bench.safety import SafetyError


def run_cli(argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


class CliTests(unittest.TestCase):
    def test_list(self):
        code, out = run_cli(["list"])
        self.assertEqual(code, 0)
        for suite in ("retain-matrix", "rerank-neutral", "candidate-cap-scaling"):
            self.assertIn(suite, out)

    def test_validate(self):
        code, out = run_cli(["validate"])
        self.assertEqual(code, 0)
        self.assertIn("validation OK", out)

    def test_offline_all_passes(self):
        code, out = run_cli(["run", "--mode", "offline", "--suite", "all", "--json"])
        self.assertEqual(code, 0)
        run = json.loads(out)
        self.assertEqual(run["aggregate"]["by_status"].get("fail", 0), 0)
        self.assertEqual(run["aggregate"]["by_status"].get("error", 0), 0)

    def test_offline_deterministic_across_runs(self):
        aggregates = []
        for _ in range(2):
            code, out = run_cli(["run", "--mode", "offline", "--suite", "all", "--json"])
            aggregates.append(json.loads(out)["aggregate"])
        self.assertEqual(aggregates[0], aggregates[1])

    def test_artifacts_written_with_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_cli(["run", "--mode", "offline", "--suite", "recall-trace",
                                 "--out-dir", tmp, "--json"])
            self.assertEqual(code, 0)
            run_id = json.loads(out)["run_id"]
            run_dir = Path(tmp) / run_id
            for name in ("run.json", "manifest.json", "report.md"):
                self.assertTrue((run_dir / name).exists(), name)
            manifest = json.loads((run_dir / "manifest.json").read_text())
            self.assertIn("prompts/hindsight-v0.9.2-extraction.md", manifest["input_hashes"])

    def test_score_recomputes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run_cli(["run", "--mode", "offline", "--suite", "context-limit",
                                 "--out-dir", tmp, "--json"])
            run_id = json.loads(out)["run_id"]
            code, out = run_cli(["score", "--results", str(Path(tmp) / run_id / "run.json"), "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["total"], 3)

    def test_unknown_suite_rejected(self):
        with self.assertRaises(SystemExit):
            run_cli(["run", "--mode", "offline", "--suite", "nope"])

    def test_config_problems_detected(self):
        args = type("Args", (), {})()
        args.mode = "live"
        args.suite = ["retain-matrix"]
        args.model = None
        args.models = ()
        args.hindsight_url = None
        args.bank = None
        args.runs = 3
        args.candidate_caps = None
        args.context_limit = None
        args.out_dir = None
        args.include_text = False
        args.allow_network = False
        args.allow_persistence = False
        args.dry_run = False
        args.yes = False
        args.json = False
        args.seed = 1
        args.hindsight_dry_run = False
        args.max_journal_chars = 1000
        args.concurrency = None
        args.timeout = None
        config = from_args(args)
        from hindsight_bench.runner import validate_config

        problems = validate_config(config)
        self.assertTrue(any("allow-network" in p for p in problems))

    def test_offline_mode_rejects_network_gate(self):
        config = BenchConfig(mode="offline", allow_network=True)
        from hindsight_bench.runner import validate_config

        self.assertTrue(validate_config(config))

    def test_live_without_key_raises_safety_error_not_silent(self):
        import os

        env_key = os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("HINDSIGHT_BENCH_OPENROUTER_API_KEY", None)
        try:
            from hindsight_bench.safety import require_env_key

            with self.assertRaises(SafetyError):
                require_env_key("OPENROUTER_API_KEY")
        finally:
            if env_key is not None:
                os.environ["OPENROUTER_API_KEY"] = env_key


if __name__ == "__main__":
    unittest.main()
