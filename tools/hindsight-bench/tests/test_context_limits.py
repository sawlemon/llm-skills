"""Context-limit request sizing and over-limit classification."""

import unittest

from hindsight_bench.fixtures import load_golden
from hindsight_bench.runner import run_context_limit
from hindsight_bench.tracing import TraceRecorder
from hindsight_bench.config import BenchConfig


class RequestSizingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden("context_limits")

    def test_budget_fits_a_180k_char_journal(self):
        # The journal-long default (180,000 chars) must fit comfortably in the
        # per-chunk context of every pinned model — a chunk is ~3,000 chars,
        # but even a whole-journal direct probe at 4 chars/token must fit for
        # the million-token models.
        estimate = self.golden["filler_chars_per_token"]
        journal_tokens = int(180_000 / estimate)
        for model, spec in self.golden["models"].items():
            budget = spec["context_tokens"] - 3000 - self.golden["system_prompt_tokens"]
            with self.subTest(model=model):
                if spec["context_tokens"] >= 1_000_000:
                    self.assertLess(journal_tokens, budget, model)

    def test_per_chunk_requests_trivially_fit(self):
        estimate = self.golden["filler_chars_per_token"]
        chunk_tokens = int(3_000 / estimate)  # 750 tokens
        for spec in self.golden["models"].values():
            budget = spec["context_tokens"] - 3000 - self.golden["system_prompt_tokens"]
            self.assertLess(chunk_tokens, budget / 10)

    def test_offline_runner_replays_probes_as_passes(self):
        config = BenchConfig(mode="offline", allow_network=False, allow_persistence=False, dry_run=True)
        cases = run_context_limit(config, TraceRecorder(None, "test"))
        self.assertEqual(len(cases), 3)
        self.assertTrue(all(case["status"] == "pass" for case in cases))
        rejected = [c for c in cases if not c["metrics"]["accepted"]]
        self.assertEqual(len(rejected), 1)
        self.assertGreater(rejected[0]["metrics"]["input_tokens"] + 3000, rejected[0]["metrics"]["window"])


if __name__ == "__main__":
    unittest.main()
