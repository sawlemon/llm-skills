"""Reranker pool construction, scoring pipeline, and candidate-cap invariants."""

import unittest

from hindsight_bench.fixtures import build_neutral_pool, load_golden
from hindsight_bench.rerank import build_pool, truncate_for_cap
from hindsight_bench.scoring import rank_metrics


class PoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden("rerank")

    def test_pool_is_padded_to_target(self):
        for case in self.golden["cases"]:
            documents, grades = build_pool(case)
            with self.subTest(case=case["case_id"]):
                self.assertEqual(len(documents), case.get("pad_to", 300))
                self.assertEqual(max(grades.values()), 3)
                self.assertIn(0, grades.values())

    def test_neutral_pool_is_deterministic_and_committed_match(self):
        import json

        from hindsight_bench.config import BENCH_ROOT

        pool_path = BENCH_ROOT / "fixtures" / "retrieval" / "neutral_pool.jsonl"
        committed = [json.loads(line)["text"] for line in pool_path.read_text().splitlines() if line.strip()]
        self.assertEqual(committed, build_neutral_pool(len(committed)))

    def test_truncate_for_cap_keeps_gold_docs(self):
        case = self.golden["cases"][0]
        for cap in (1, 2, 5, 50, 300):
            documents, grades = truncate_for_cap(case, cap)
            self.assertEqual(len(documents), cap)
            self.assertTrue(grades)  # gold docs always present
            self.assertTrue(all(i < cap for i in grades))

    def test_gold_docs_ranked_before_filler_for_perfect_rerank(self):
        case = self.golden["cases"][0]
        documents, grades = truncate_for_cap(case, 50)
        perfect = sorted(range(len(documents)), key=lambda i: -grades.get(i, 0))
        ranked_grades = [grades.get(i, 0) for i in perfect[:10]]
        metrics = rank_metrics(ranked_grades, sorted(grades.values(), reverse=True))
        self.assertEqual(metrics["top1_grade"], 3)
        self.assertGreaterEqual(metrics["ndcg10"], 0.99)


class CapSweepTests(unittest.TestCase):
    def test_reference_cap_latency_is_monotonic(self):
        golden = load_golden("rerank")
        for model, caps in golden["candidate_caps"].items():
            ordered = sorted(caps, key=int)
            latencies = [caps[c]["median_s"] for c in ordered]
            with self.subTest(model=model):
                self.assertTrue(
                    all(a <= b + 1e-6 for a, b in zip(latencies, latencies[1:])),
                    f"non-monotonic reference latencies for {model}: {latencies}",
                )

    def test_reference_rankings_reproduce_recorded_metrics(self):
        golden = load_golden("rerank")
        checked = 0
        for case in golden["cases"]:
            ideal = sorted((entry["grade"] for entry in case["graded"]), reverse=True)
            for model, reference in case.get("reference_rankings", {}).items():
                metrics = rank_metrics(reference["ranked_grades"], ideal)
                with self.subTest(case=case["case_id"], model=model):
                    self.assertLessEqual(abs(metrics["ndcg10"] - reference["ndcg10"]), 0.02)
                    self.assertLessEqual(abs(metrics["mrr"] - reference["mrr"]), 0.02)
                checked += 1
        self.assertGreaterEqual(checked, 18)


if __name__ == "__main__":
    unittest.main()
