"""Regression floor for the frozen synthetic holdout; no inference or network.

KRE_SOURCE_ROOT optionally names the checkout under test. Otherwise the nearest
ancestor containing src/kre is used, making this file portable inside a repo.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
FIXTURE_SHA256 = "40e6067515a64cc952746b6fe1375e9b1a1dd050096bf57fd557d0a643d3bb3d"


class FrozenAlphaHoldout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        explicit = os.environ.get("KRE_SOURCE_ROOT")
        roots = [Path(explicit).resolve()] if explicit else list(HERE.parents)
        source = next((root for root in roots if (root / "src" / "kre").is_dir()), None)
        if source is None:
            raise unittest.SkipTest("Set KRE_SOURCE_ROOT to a checkout with src/kre")
        cls.fixture_bytes = (HERE / "fixture.json").read_bytes()
        cls.fixture = json.loads(cls.fixture_bytes)
        with tempfile.TemporaryDirectory(prefix="kre-holdout-regression-") as temp:
            output = Path(temp) / "results.json"
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            run = subprocess.run([sys.executable, "-I", "-B", str(HERE / "evaluate.py"),
                                  "--worker", "--source-root", str(source), "--output", str(output)],
                                 cwd=temp, env=env, text=True, capture_output=True, timeout=60)
            if run.returncode:
                raise AssertionError("Offline holdout worker failed: " + run.stderr)
            cls.results = json.loads(output.read_text())
        cls.by_id = {result["case_id"]: result for result in cls.results["results"]}

    def test_frozen_fixture_exact_spans(self):
        self.assertEqual(hashlib.sha256(self.fixture_bytes).hexdigest(), FIXTURE_SHA256)
        self.assertEqual(len(self.fixture["cases"]), 16)
        self.assertEqual(sum(len(c["documents"]) for c in self.fixture["cases"]), 32)
        self.assertEqual(sum(len(c["gold"]) for c in self.fixture["cases"]), 31)
        for case in self.fixture["cases"]:
            docs = {d["id"]: d for d in case["documents"]}
            for span in case["gold"]:
                text = docs[span["source_id"]]["text"]
                self.assertEqual(text[span["char_start"]:span["char_end"]], span["quote"])
                self.assertEqual(text.count(span["quote"]), 1)

    def test_all_cases_execute_and_ordinary_recall_floor(self):
        self.assertEqual(len(self.by_id), 16)
        for result in self.by_id.values():
            self.assertNotIn("execution_error", result, result)
        ordinary = self.results["aggregate"]["ordinary"]
        self.assertEqual(ordinary["gold_spans"], 28)
        self.assertGreaterEqual(ordinary["covered_spans"], 24)
        self.assertGreaterEqual(ordinary["complete_positive_cases"], 10)

    def test_exact_citations_current_snapshots_and_budgets(self):
        for result in self.by_id.values():
            with self.subTest(case=result["case_id"]):
                metrics = result["metrics"]
                self.assertEqual(metrics["citation_errors"], [])
                self.assertEqual(metrics["exact_citations"], metrics["items"])
                if result["response"]["status"] == "error":
                    self.assertEqual(metrics["snapshot_validation"], "denied")
                else:
                    self.assertEqual(metrics["snapshot_validation"], "current")
                self.assertEqual(metrics["budget_errors"], [])

    def test_policy_and_missing_evidence_controls(self):
        for result in self.by_id.values():
            self.assertEqual(result["metrics"]["policy_errors"], [], result["case_id"])
        denial = self.by_id["H11"]
        self.assertTrue(denial["expected_behavior_pass"])
        self.assertEqual(denial["response"]["items"], [])
        self.assertEqual(denial["response"]["context_text"], "")
        self.assertFalse(self.by_id["H09"]["metrics"]["unsupported_sufficiency_claim"])
        self.assertEqual(self.by_id["H10"]["metrics"]["covered_spans"], 1)
        self.assertEqual(self.by_id["H15"]["metrics"]["covered_spans"], 2)

    def test_declared_references_fit_and_safe_budget_failure(self):
        self.assertTrue(self.by_id["H12"]["expected_behavior_pass"])
        self.assertEqual(self.by_id["H12"]["metrics"]["covered_spans"], 2)
        failure = self.by_id["H13"]
        self.assertTrue(failure["expected_behavior_pass"])
        self.assertEqual(failure["required_wrapper"]["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(failure["response"]["context_text"], "")

    def test_checkpoint_retains_then_invalidates_dependency(self):
        state = self.by_id["H14"]["continuity"]
        self.assertTrue(state["pass"])
        self.assertTrue(state["before_supported"])
        self.assertTrue(state["dependent_removed"])
        self.assertTrue(state["independent_assertion_retained"])
        self.assertTrue(state["invalidation_visible"])
        self.assertNotEqual(state["previous_context_validation"], "current")


if __name__ == "__main__":
    unittest.main()
