"""Context-limit acceptance math and recall trace parsing."""

import unittest

from hindsight_bench.fixtures import load_golden
from hindsight_bench.runner import run_context_limit, run_recall_trace
from hindsight_bench.tracing import parse_recall_trace
from hindsight_bench.config import BenchConfig
from hindsight_bench.tracing import TraceRecorder


class ContextLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden("context_limits")

    def test_recorded_probes_reproduce_acceptance(self):
        config = BenchConfig(mode="offline", allow_network=False, allow_persistence=False, dry_run=True)
        cases = run_context_limit(config, TraceRecorder(None, "test"))
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(case["status"], "pass", case.get("error"))

    def test_over_limit_math(self):
        window = self.golden["models"]["openai/gpt-oss-20b"]["context_tokens"]
        probe = next(p for p in self.golden["probes"]["openai/gpt-oss-20b"] if not p["accepted"])
        self.assertGreater(probe["input_tokens"] + 3000, window)
        for probe in self.golden["probes"]["openai/gpt-oss-20b"]:
            if probe["accepted"]:
                self.assertLessEqual(probe["input_tokens"] + 3000, window)


class TraceParsingTests(unittest.TestCase):
    def test_sample_trace_parses_to_golden_values(self):
        import json

        from hindsight_bench.config import BENCH_ROOT

        sample = json.loads((BENCH_ROOT / "fixtures/retrieval/recall_trace_sample.json").read_text())
        parsed = parse_recall_trace(sample)
        golden = load_golden("recall")["sample_trace"]
        for phase, expected in golden["phases"].items():
            self.assertAlmostEqual(parsed["phases"][phase], expected, places=4, msg=phase)
        self.assertEqual(parsed["counts"], golden["counts"])
        self.assertAlmostEqual(parsed["total_duration_seconds"], golden["total_duration_seconds"], places=4)

    def test_diagnostics_excluded_from_phases(self):
        import json

        from hindsight_bench.config import BENCH_ROOT

        sample = json.loads((BENCH_ROOT / "fixtures/retrieval/recall_trace_sample.json").read_text())
        parsed = parse_recall_trace(sample)
        self.assertNotIn("semaphore_wait", parsed["phases"])
        self.assertIn("semaphore_wait", parsed["diagnostics"])


class OfflineSuiteRunnerTests(unittest.TestCase):
    def test_recall_offline_run_passes(self):
        config = BenchConfig(mode="offline", allow_network=False, allow_persistence=False, dry_run=True)
        cases = run_recall_trace(config, TraceRecorder(None, "test"))
        self.assertEqual([c["status"] for c in cases], ["pass"])


if __name__ == "__main__":
    unittest.main()
