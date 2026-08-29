"""Criteria-based fact scoring and rank metrics, including the manual-review corrections."""

import unittest

from hindsight_bench.fixtures import load_golden
from hindsight_bench.scoring import evaluate_fact_criteria, mrr, ndcg_at_k, rank_metrics


class RetainCriteriaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = load_golden("retain")

    def _evaluate(self, section, label):
        ref = next(r for r in self.golden[section]["reference_outputs"] if r["label"] == label)
        case = self.golden[section]["case"]
        return evaluate_fact_criteria(ref["facts"], case), ref

    def test_reference_outputs_match_expected_verdicts(self):
        for section in ("matrix", "adversarial"):
            for ref in self.golden[section]["reference_outputs"]:
                case = self.golden[section]["case"]
                result = evaluate_fact_criteria(ref["facts"], case)
                with self.subTest(section=section, label=ref["label"]):
                    self.assertEqual(
                        result["passed"],
                        ref["expected_verdict"] == "pass",
                        f"violations: {result['violations']}",
                    )

    def test_correction_qualifier_suppresses_stale_date_violation(self):
        # The exact manual-review lesson: restating the superseded date WITH a
        # correction qualifier must pass, without it must fail. Evaluated
        # against a minimal case so only the forbidden check is exercised.
        case = {"forbidden": self.golden["matrix"]["case"]["forbidden"]}
        good = [{"what": "The deadline moved to September 6, 2026, correcting the earlier September 5 date."}]
        bad = [{"what": "The deadline is September 5, 2026."}]
        self.assertTrue(evaluate_fact_criteria(good, case)["passed"])
        self.assertFalse(evaluate_fact_criteria(bad, case)["passed"])

    def test_split_attribution_counts_as_covered(self):
        # 'User does not own a Tesla' + 'Arun owns a blue Model 3' as separate
        # facts is correct extraction, not mis-attribution.
        case = self.golden["adversarial"]["case"]
        facts = [{"what": "User does not own a Tesla"}, {"what": "Arun owns a blue Model 3"}]
        result = evaluate_fact_criteria(facts, case)
        self.assertTrue(result["criteria"]["tesla_not_user"]["passed"])
        self.assertTrue(result["criteria"]["arun_owns"]["passed"])

    def test_regex_forbidden_path_needs_qualifier(self):
        case = {"forbidden": self.golden["matrix"]["case"]["forbidden"]}
        stale = [{"what": "The live directory is /srv/appdata/live-db."}]
        corrected = [{"what": "The live directory is /srv/appdata/live-db-new; the old path is rollback-only."}]
        self.assertFalse(evaluate_fact_criteria(stale, case)["passed"])
        self.assertTrue(evaluate_fact_criteria(corrected, case)["passed"])

    def test_unsupported_fact_counting(self):
        case = dict(self.golden["matrix"]["case"])
        case["limits"] = {"max_unsupported": 0}
        facts = [{"what": "User works at Northwind Labs"}, {"what": "Totally unrelated invented claim about zebras"}]
        result = evaluate_fact_criteria(facts, case)
        self.assertEqual(result["unsupported_count"], 1)


class RankMetricTests(unittest.TestCase):
    def test_ndcg_known_answer(self):
        # ideal [3,2,1]: dcg_ideal = 7 + 3/log2(3) + 1/log2(4) = 10.3923...
        self.assertAlmostEqual(ndcg_at_k([3, 2, 1], [3, 2, 1], 10), 1.0, places=6)
        self.assertAlmostEqual(ndcg_at_k([0, 0, 0], [3, 2, 1], 10), 0.0, places=6)

    def test_mrr_and_hit(self):
        self.assertEqual(mrr([0, 3, 1]), 0.5)
        self.assertEqual(mrr([1, 0, 2]), 1 / 3)
        self.assertEqual(mrr([0, 0, 0]), 0.0)

    def test_rank_metrics_shape(self):
        metrics = rank_metrics([3, 0, 0], [3, 1])
        self.assertEqual(metrics["top1_grade"], 3)
        self.assertTrue(metrics["hit1"])
        self.assertIn("ndcg10", metrics)


if __name__ == "__main__":
    unittest.main()
