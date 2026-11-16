"""Evaluation integrity/metric tests use separate tiny examples, not held-out tuning."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from kre import Store

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("kre_evaluation", ROOT / "scripts/evaluate.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
comparison_spec = importlib.util.spec_from_file_location("kre_comparison", ROOT / "scripts/compare_evaluation.py")
comparison = importlib.util.module_from_spec(comparison_spec)
comparison_spec.loader.exec_module(comparison)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:", principal="metric-test",
                           scopes={"public-reader": {"public"}, "private-reader": {"public", "private"}})
        self.addCleanup(self.store.close)
        self.corpus = {"sources": [
            # Keep the heading separate from the gold body span: this tests the
            # scorer's distinction between source recall and exact span recall.
            {"source_id": "note", "collection": "public", "versions": [{"label": "v1", "text": "# Heading\n\nQuartz control is enabled.\n\n" + "unrelated-padding " * 100}]},
            {"source_id": "secret", "collection": "private", "versions": [{"label": "v1", "text": "Private quartz control.\n"}]},
        ]}
        self.versions, self.expected = evaluation.build_corpus(self.store, self.corpus)
        self.manifest = {"scopes": {"public-reader": ["public"], "private-reader": ["public", "private"]},
                         "default_budget": {"max_tokens": 3000, "max_items": 5, "max_bytes": 8000}}
        self.case = {"id": "metric-test", "query": "quartz", "category": "metric", "gold": [
            {"source_id": "note", "version": "v1", "line_start": 3, "line_end": 3}]}
        self.request = evaluation.request_for(self.case, self.manifest)

    def measure(self, case=None, request=None, result=None, refs=None):
        case, request = case or self.case, request or self.request
        result = result or evaluation.execute_kre(self.store, request, [], False)
        return evaluation.score(case, request, result, refs or [], self.versions, self.expected, self.manifest["scopes"])

    def test_frozen_hash_and_disjoint_development_gold(self):
        corpus, cases, freeze = evaluation.load_frozen()
        self.assertEqual((len(cases["development"]), len(cases["held_out"])), (4, 24))
        key = lambda span: (span["source_id"], span["version"], span["line_start"], span["line_end"])
        dev = {key(span) for case in cases["development"] for span in case["gold"]}
        held = {key(span) for case in cases["held_out"] for span in case["gold"]}
        self.assertFalse(dev & held)
        self.assertTrue(freeze["frozen_at_utc"])
        self.assertTrue(corpus["synthetic"])

    def test_freeze_refuses_silent_fixture_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ("freeze.json", "corpus.json", "cases.json"):
                shutil.copy2(ROOT / "evaluation" / name, folder / name)
            with (folder / "cases.json").open("a") as target:
                target.write(" ")
            with self.assertRaisesRegex(ValueError, "Frozen fixture changed"):
                evaluation.load_frozen(folder)

    def test_exact_span_score_and_unknown_chunk_rejected(self):
        result = evaluation.execute_kre(self.store, self.request, [], False)
        score = self.measure(result=result)
        self.assertEqual((score["span_recall"], score["citation_accuracy"]), (1, 1))
        result["context"]["items"][0]["chunk_id"] = "c-nonexistent"
        result["context"]["context_text"] = self.store._render(result["context"]["items"])
        score = self.measure(result=result)
        self.assertEqual((score["span_recall"], score["citation_accuracy"]), (0, 0))
        self.assertFalse(score["correctness_pass"])

    def test_same_source_without_gold_span_does_not_inflate_recall(self):
        req = dict(self.request, query="Heading")
        score = self.measure(request=req)
        self.assertEqual(score["source_precision"], 1)
        self.assertEqual(score["span_recall"], 0)
        self.assertEqual(score["source_recall"], 0)

    def test_empty_gold_has_undefined_recall_not_perfect_score(self):
        case = dict(self.case, gold=[])
        request = dict(self.request, query="unfindableword")
        score = self.measure(case=case, request=request)
        self.assertIsNone(score["span_recall"])
        self.assertIsNone(score["span_precision"])
        self.assertIsNone(score["citation_accuracy"])
        self.assertTrue(score["correctness_pass"])

    def test_private_quote_can_be_exact_and_still_unauthorized(self):
        wide = dict(self.request, query="Private", access_scope_ref="private-reader")
        result = evaluation.execute_kre(self.store, wide, [], False)
        score = self.measure(result=result)
        self.assertEqual(score["citation_accuracy"], 1)
        self.assertEqual(score["unauthorized_or_revoked_items"], 1)
        self.assertFalse(score["correctness_pass"])

    def test_metadata_promotion_is_an_evaluation_failure(self):
        result = evaluation.execute_kre(self.store, self.request, [], False)
        result["context"]["items"][0]["authority"] = "authoritative"
        score = self.measure(result=result)
        self.assertEqual(score["metadata_label_violations"], 1)
        self.assertFalse(score["correctness_pass"])

    def test_baseline_same_scope_and_citation_budget(self):
        result = evaluation.overlap_baseline(self.store, self.request, [])
        self.assertEqual([item["source_id"] for item in result["context"]["items"]], ["note"])
        tiny = dict(self.request, budget={"max_tokens": 10, "max_items": 5, "max_bytes": 10})
        result = evaluation.overlap_baseline(self.store, tiny, [])
        self.assertFalse(result["context"]["items"])
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")

    def test_required_first_fairness_and_missing_report(self):
        case = dict(self.case, required=copy.deepcopy(self.case["gold"]), required_expectation="delivered")
        request = dict(self.request, query="Heading", budget={"max_tokens": 3000, "max_items": 1, "max_bytes": 8000})
        refs = evaluation.refs_for(self.store, case, self.versions)
        for result in (evaluation.overlap_baseline(self.store, request, refs),
                       evaluation.execute_kre(self.store, request, refs, True)):
            score = self.measure(case, request, result, refs)
            self.assertTrue(score["correctness_pass"])
            self.assertEqual(score["required_delivered"], 1)
            result["required"]["delivered"] = []
            self.assertFalse(self.measure(case, request, result, refs)["required_reporting_correct"])

    def test_impossible_required_budget_is_explicit_for_both(self):
        case = dict(self.case, required=copy.deepcopy(self.case["gold"]), required_expectation="budget")
        refs = evaluation.refs_for(self.store, case, self.versions)
        request = dict(self.request, budget={"max_tokens": 10, "max_items": 1, "max_bytes": 10})
        for result in (evaluation.overlap_baseline(self.store, request, refs),
                       evaluation.execute_kre(self.store, request, refs, True)):
            score = self.measure(case, request, result, refs)
            self.assertTrue(score["correctness_pass"])
            self.assertEqual(score["required_undelivered"], 1)
            result["required"]["missing"] = []
            self.assertFalse(self.measure(case, request, result, refs)["required_behavior_correct"])

    def test_development_smoke_without_executing_held_out_queries(self):
        report = evaluation.evaluate("development", repetitions=1)
        self.assertEqual(len(report["cases"]), 4)
        self.assertFalse(report["evaluation_usage"]["independent_holdout"])
        self.assertEqual(report["evaluation_usage"]["status"], "tuning_set")
        for algorithm in report["summary"].values():
            self.assertEqual(algorithm["correctness_failures"], 0)

    @staticmethod
    def comparison_report():
        def case(key, comparable):
            metric = {"context_bytes": 100, "returned_items": 1, "gold_spans": 1, "covered_gold_spans": int(comparable)}
            return {"case_id": key, "query": key, "gold": ["symbolic-test-span"], "request": {},
                    "required_expectation": None, "equal_labeled_and_required_coverage_for_size_comparison": comparable,
                    "algorithms": {"kre": {"metrics": dict(metric)}, "overlap_baseline": {"metrics": dict(metric)}}}
        return {"freeze": {"files": {"corpus.json": "frozen"}}, "summary": {}, "cases": [case("complete", True), case("improved", False)]}

    def test_before_after_size_uses_fixed_complete_coverage_intersection(self):
        before = self.comparison_report()
        after = copy.deepcopy(before)
        after["cases"][0]["algorithms"]["kre"]["metrics"]["context_bytes"] = 80
        after["cases"][1]["equal_labeled_and_required_coverage_for_size_comparison"] = True
        after["cases"][1]["algorithms"]["kre"]["metrics"]["context_bytes"] = 1
        result = comparison.compare(before, after)
        self.assertEqual(result["fixed_complete_coverage_case_ids"], ["complete"])
        self.assertEqual(result["fixed_coverage_context"]["kre_after"]["median_bytes"], 80)
        self.assertFalse(result["independent_holdout"])

    def test_before_after_rejects_changed_fixture_or_query(self):
        before = self.comparison_report()
        for mutation in ("fixture", "query"):
            after = copy.deepcopy(before)
            if mutation == "fixture":
                after["freeze"]["files"]["corpus.json"] = "changed"
            else:
                after["cases"][0]["query"] = "different"
            with self.assertRaises(ValueError):
                comparison.compare(before, after)


if __name__ == "__main__":
    unittest.main()
