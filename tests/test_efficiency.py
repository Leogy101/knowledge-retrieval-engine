"""Offline receipts with known arithmetic; no live transport or private data."""
from copy import deepcopy
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from kre.efficiency import (MeasurementError, compare_runs, estimate_cost, fingerprint,
                            load_json, main, measure_content, normalize_usage,
                            model_configuration_sha256, render_markdown, strict_loads, summarize_run)

H = "a" * 64
J = "b" * 64
CONFIG = fingerprint({"provider": "fixture", "model": "fixture-model", "model_revision": "revision-1", "reasoning_sha256": H})


def usage(**changes):
    value = {"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 40,
             "cache_write_tokens": 10, "reasoning_tokens": 5, "total_tokens": 170,
             "input_semantics": "excludes_cache", "output_semantics": "includes_reasoning",
             "source_kind": "synthetic", "provenance_sha256": H}
    value.update(changes)
    return value


def request(identifier="request-1", **changes):
    value = {"id": identifier, "state": "completed", "retry_of": None, "usage": usage(),
             "configuration_sha256": CONFIG,
             "context": {"model_input_bytes": 1000, "injected_tool_bytes": 200,
                         "injected_evidence_bytes": 100, "estimated_input_tokens": 250,
                         "input_sha256": H},
             "actual_cost": {"amount": .002, "currency": "USD", "source_kind": "provider_billed", "basis_sha256": H},
             "estimated_cost": {"amount": .003, "currency": "USD", "source_kind": "estimated", "basis_sha256": J}}
    value.update(changes)
    return value


def run(condition="disabled", **changes):
    value = {
        "format": "efficiency-run/1", "source_kind": "synthetic", "condition": condition,
        "identity": {"task_id": "fixture.task", "pair_id": "pair-1", "repetition": 1,
                     "task_sha256": H, "input_sha256": H, "corpus_sha256": H, "rubric_sha256": H},
        "answer_sha256": H, "observation_sha256": H, "trial_order": 1 if condition == "disabled" else 2,
        "comparison": {"system": "kre", "allowed_differences": []},
        "configuration": {"provider": "fixture", "model": "fixture-model", "model_revision": "revision-1",
                          "reasoning_sha256": H, "tools": ["read"] + (["kre_retrieve", "kre_validate"] if condition == "enabled" else []),
                          "permissions_sha256": H, "environment_sha256": H, "history_sha256": H,
                          "source_access_sha256": H, "retry_policy_sha256": H, "cache_state": "cold", "warm_state": "warm", "memory_state": "isolated"},
        "coverage": {"requests": "complete", "auxiliary": "complete", "tools": "complete", "context": "complete"},
        "requests": [request()],
        "tools": [{"id": "tool-1", "name": "read", "state": "completed", "response_bytes": 200,
                   "response_sha256": H, "elapsed_seconds": .1}],
        "measurements": {"completion_seconds": 2.0, "retrieval_core_seconds": .01,
                         "retrieval_round_trip_seconds": .1, "validation_seconds": 0,
                         "routing_seconds": 0, "local_cpu_seconds": .02,
                         "setup_seconds": .3, "setup_cpu_seconds": .1, "storage_bytes": 4096},
        "outcome": "completed",
    }
    value.update(changes)
    return value


def quality(**changes):
    value = {"format": "quality-score/1", "task_id": "fixture.task", "task_sha256": H,
             "rubric_sha256": H, "answer_sha256": H, "observation_sha256": H,
             "completion_pass": True, "critical_pass": True, "quality_pass": True,
             "citation_exactness": {"passed": 1, "total": 1, "unknown": 0, "score": 1.0},
             "citation_support": {"passed": 1, "total": 1, "unknown": 0, "score": 1.0},
             "evidence_recall": {"passed": 1, "total": 1, "unknown": 0, "score": 1.0},
             "evidence_validity": {"passed": 1, "total": 1, "unknown": 0, "score": 1.0}}
    value.update(changes)
    return value


def metric(report, name):
    return next(row for row in report["rows"] if row["metric"] == name)


class EfficiencyTests(unittest.TestCase):
    def test_cache_semantics_and_reasoning_are_not_added_twice(self):
        exclusive = normalize_usage(usage())
        inclusive = normalize_usage(usage(input_tokens=150, input_semantics="includes_cache"))
        self.assertEqual(exclusive, inclusive)
        self.assertEqual(exclusive["input_tokens"], 150)
        self.assertEqual(exclusive["uncached_input_tokens"], 100)
        self.assertEqual(exclusive["total_tokens"], 170)
        self.assertEqual(exclusive["reasoning_tokens"], 5)

    def test_unknown_categories_stay_unknown_without_losing_reported_total(self):
        result = normalize_usage(usage(cache_read_tokens=None))
        self.assertIsNone(result["input_tokens"])
        self.assertIsNone(result["cache_read_tokens"])
        self.assertEqual(result["total_tokens"], 170)
        self.assertIsNone(normalize_usage(None)["total_tokens"])

    def test_invalid_usage_and_partial_lower_bounds_rejected(self):
        variants = [usage(input_tokens=True), usage(total_tokens=169), usage(reasoning_tokens=21),
                    usage(input_tokens=40, input_semantics="includes_cache"),
                    usage(input_tokens=None, output_tokens=None, cache_read_tokens=100, cache_write_tokens=0, reasoning_tokens=None, total_tokens=10, input_semantics="includes_cache"),
                    usage(input_tokens=None, output_tokens=None, cache_read_tokens=40, cache_write_tokens=40, reasoning_tokens=None, total_tokens=50, input_semantics="includes_cache"),
                    usage(input_tokens=100, output_tokens=None, cache_read_tokens=None, cache_write_tokens=None, reasoning_tokens=None, total_tokens=1),
                    usage(input_tokens=None, output_tokens=None, cache_read_tokens=None, cache_write_tokens=None, reasoning_tokens=100, total_tokens=1),
                    usage(output_semantics="unknown"), usage(input_tokens=10**1000)]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(MeasurementError):
                normalize_usage(value)

    def test_aggregation_multiple_requests_counts_retransmitted_context(self):
        value = run(requests=[request(), request("request-2")])
        summary = summarize_run(value)
        self.assertEqual(summary["metrics"]["total_tokens"]["value"], 340)
        self.assertEqual(summary["metrics"]["model_requests"]["value"], 2)
        self.assertEqual(summary["metrics"]["model_input_bytes"]["value"], 2000)
        self.assertEqual(summary["metrics"]["injected_tool_bytes"]["value"], 400)
        self.assertEqual(summary["metrics"]["tool_response_bytes"]["value"], 200)
        self.assertEqual(summary["metrics"]["actual_cost"]["value"], .004)
        self.assertEqual(summary["metrics"]["estimated_cost"]["value"], .006)

    def test_large_integer_totals_remain_exact(self):
        first = request(usage=usage(input_tokens=9007199254740992, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0, reasoning_tokens=0, total_tokens=None))
        second = request("request-2", usage=usage(input_tokens=1, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0, reasoning_tokens=0, total_tokens=None))
        self.assertEqual(summarize_run(run(requests=[first, second]))["metrics"]["total_tokens"]["value"], 9007199254740993)

    def test_missing_failed_attempt_usage_invalidates_complete_sum_not_known_subtotal(self):
        failed = request("failed", state="failed", usage=None, actual_cost=None, estimated_cost=None)
        retry = request("retry", retry_of="failed")
        summary = summarize_run(run(requests=[failed, retry]))
        self.assertIsNone(summary["metrics"]["total_tokens"]["value"])
        self.assertEqual(summary["metrics"]["total_tokens"]["known_sum"], 170)
        self.assertEqual(summary["metrics"]["total_tokens"]["known_records"], 1)
        self.assertEqual(summary["metrics"]["model_requests"]["value"], 2)
        self.assertEqual(summary["observed_retries"], 1)
        self.assertEqual(summary["attempt_outcomes"]["failed"], 1)

    def test_cancelled_usage_and_pending_unknown_attempts_retained(self):
        summary = summarize_run(run(requests=[request(state="cancelled"), request("pending", state="started", usage=None, actual_cost=None, estimated_cost=None)], outcome="incomplete"))
        self.assertEqual(summary["attempt_outcomes"]["cancelled"], 1)
        self.assertEqual(summary["attempt_outcomes"]["started"], 1)
        self.assertEqual(summary["metrics"]["total_tokens"]["known_sum"], 170)
        self.assertFalse(summary["execution_terminal"])

    def test_incomplete_numeric_snapshots_are_partial_not_final_totals(self):
        for state in ("started", "incomplete"):
            with self.subTest(state=state):
                summary = summarize_run(run(requests=[request(state=state)], outcome="incomplete"))
                for key, subtotal in (("total_tokens", 170), ("actual_cost", .002),
                                      ("completion_seconds", 2.0), ("model_requests", 1)):
                    self.assertIsNone(summary["metrics"][key]["value"])
                    self.assertEqual(summary["metrics"][key]["known_sum"], subtotal)
                    self.assertEqual(summary["metrics"][key]["coverage"], "partial")
        value = run()
        value["tools"][0]["state"] = "started"
        self.assertEqual(summarize_run(value)["metrics"]["total_tokens"]["coverage"], "partial")

    def test_empty_incomplete_execution_does_not_invent_zero_usage(self):
        summary = summarize_run(run(requests=[], tools=[], outcome="incomplete"))
        for key in ("total_tokens", "actual_cost", "model_requests"):
            self.assertIsNone(summary["metrics"][key]["value"])
            self.assertIsNone(summary["metrics"][key]["known_sum"])
            self.assertEqual(summary["metrics"][key]["coverage"], "unknown")

    def test_failed_and_cancelled_final_receipts_are_counted_with_missing_usage(self):
        for state in ("failed", "cancelled"):
            with self.subTest(state=state):
                failed = request(state=state)
                summary = summarize_run(run(requests=[failed, request("retry", retry_of=failed["id"])]))
                self.assertEqual(summary["metrics"]["total_tokens"]["value"], 340)
                self.assertEqual(summary["metrics"]["total_tokens"]["coverage"], "complete")
                failed["usage"] = None
                failed["actual_cost"] = failed["estimated_cost"] = None
                summary = summarize_run(run(requests=[failed, request("retry", retry_of=failed["id"])]))
                self.assertIsNone(summary["metrics"]["total_tokens"]["value"])
                self.assertEqual(summary["metrics"]["total_tokens"]["known_sum"], 170)
                self.assertEqual(summary["metrics"]["total_tokens"]["coverage"], "partial")
                self.assertEqual(summary["metrics"]["model_requests"]["value"], 2)

    def test_auxiliary_coverage_unknown_prevents_whole_workflow_totals(self):
        value = run()
        value["coverage"]["auxiliary"] = "unknown"
        summary = summarize_run(value)
        self.assertIsNone(summary["metrics"]["model_requests"]["value"])
        self.assertIsNone(summary["metrics"]["total_tokens"]["value"])
        self.assertEqual(summary["metrics"]["total_tokens"]["known_sum"], 170)

    def test_duplicate_receipts_and_empty_pending_transition_deduplicate(self):
        complete = request()
        pending = request(state="started", usage=None, actual_cost=None, estimated_cost=None)
        for rows in ([complete, complete], [pending, complete], [complete, pending]):
            self.assertEqual(summarize_run(run(requests=rows))["metrics"]["model_requests"]["value"], 1)

    def test_conflicting_terminal_or_partial_updates_are_rejected(self):
        variants = [[request(), request(usage=usage(input_tokens=90, total_tokens=160))],
                    [request(state="started"), request()],
                    [request(), request(state="failed")]]
        for rows in variants:
            with self.subTest(rows=rows), self.assertRaises(MeasurementError):
                summarize_run(run(requests=rows))

    def test_retry_cycles_and_missing_origins_are_rejected(self):
        for rows in ([request(retry_of="absent")], [request(retry_of="request-2"), request("request-2", retry_of="request-1")]):
            with self.assertRaises(MeasurementError):
                summarize_run(run(requests=rows))

    def test_empty_complete_ledger_proves_zero_only_with_explicit_coverage(self):
        summary = summarize_run(run(requests=[], tools=[]))
        self.assertEqual(summary["metrics"]["model_requests"]["value"], 0)
        self.assertEqual(summary["metrics"]["total_tokens"]["value"], 0)
        value = run(requests=[])
        value["coverage"]["requests"] = "unknown"
        self.assertIsNone(summarize_run(value)["metrics"]["total_tokens"]["value"])

    def test_estimate_is_separate_and_missing_price_input_is_unknown(self):
        pricing = {"currency": "USD", "price_sha256": J, "uncached_input_per_million": 1,
                   "cache_read_per_million": .5, "cache_write_per_million": 2, "output_per_million": 3}
        result = estimate_cost(usage(), pricing)
        self.assertEqual(result["amount"], .0002)
        self.assertEqual(result["source_kind"], "estimated")
        self.assertIsNone(estimate_cost(usage(cache_read_tokens=None), pricing))
        value = run()
        value["requests"].append(request("second"))
        value["requests"][1]["actual_cost"]["currency"] = "EUR"
        with self.assertRaises(MeasurementError):
            summarize_run(value)

    def test_percentages_negative_savings_and_quality_differences(self):
        disabled, enabled = run(), run("enabled")
        enabled["requests"].append(request("request-2"))
        enabled["measurements"]["completion_seconds"] = 1
        report = compare_runs(disabled, enabled, quality_disabled=quality(), quality_enabled=quality())
        self.assertEqual(metric(report, "total_tokens")["change"]["percent"], -100)
        self.assertEqual(metric(report, "total_tokens")["change"]["direction"], "regression")
        self.assertEqual(metric(report, "completion_seconds")["change"]["percent"], 50)
        self.assertEqual(metric(report, "quality_pass")["change"]["percent"], 0)
        self.assertTrue(report["quality_preserved"])
        self.assertEqual(report["claims"]["total_tokens"], "synthetic_only")
        rendered = render_markdown(report)
        self.assertIn("-100% reduction (regression)", rendered)
        self.assertIn("Synthetic verification only", rendered)

    def test_zero_and_missing_denominators_are_na(self):
        disabled, enabled = run(), run("enabled")
        disabled["measurements"]["completion_seconds"] = 0
        enabled["measurements"]["routing_seconds"] = None
        report = compare_runs(disabled, enabled)
        self.assertIsNone(metric(report, "completion_seconds")["change"]["percent"])
        self.assertIsNone(metric(report, "routing_seconds")["change"]["percent"])

    def test_task_and_corpus_mismatch_refused(self):
        for field in ("task_sha256", "input_sha256", "corpus_sha256", "rubric_sha256"):
            value = run("enabled")
            value["identity"][field] = J
            with self.subTest(field=field), self.assertRaises(MeasurementError):
                compare_runs(run(), value)

    def test_mismatched_controls_and_unknown_memory_cannot_claim_control(self):
        disabled, enabled = run(), run("enabled")
        enabled["configuration"]["permissions_sha256"] = J
        report = compare_runs(disabled, enabled)
        self.assertFalse(report["controlled"])
        self.assertIn("unmatched_permissions_sha256", report["control_limitations"])
        enabled = run("enabled")
        enabled["configuration"]["memory_state"] = "unknown"
        self.assertFalse(compare_runs(disabled, enabled)["controlled"])

    def test_gcb_predeclared_model_difference_and_treatment_tools(self):
        disabled, enabled = run(), run("enabled")
        for value in (disabled, enabled):
            value["comparison"] = {"system": "gcb", "allowed_differences": ["model", "reasoning_sha256"]}
            value["configuration"]["tools"] = ["read"]
        enabled["configuration"]["model"] = "fixture-other"
        enabled["configuration"]["reasoning_sha256"] = J
        enabled["configuration"]["tools"].append("gcb_recommend")
        enabled["requests"][0]["configuration_sha256"] = model_configuration_sha256(enabled["configuration"])
        enabled["guidance"] = {"preview_sha256": H, "policy_sha256": H, "bio_sha256": H,
                               "selected_configuration_sha256": model_configuration_sha256(enabled["configuration"]), "recorded_before_execution": True}
        report = compare_runs(disabled, enabled)
        self.assertTrue(report["controlled"])
        self.assertTrue(report["declared_configuration_differences"]["model"]["predeclared"])
        enabled["configuration"]["tools"].append("write-anywhere")
        self.assertFalse(compare_runs(disabled, enabled)["controlled"])

    def test_estimated_price_change_requires_an_actual_predeclared_model_difference(self):
        disabled, enabled = run(), run("enabled")
        for value in (disabled, enabled):
            value["source_kind"] = "captured"
            value["requests"][0]["usage"]["source_kind"] = "provider_reported"
            value["comparison"] = {"system": "gcb", "allowed_differences": ["model", "reasoning_sha256"]}
            value["configuration"]["tools"] = ["read"]
        enabled["guidance"] = {"preview_sha256": H, "policy_sha256": H, "bio_sha256": H,
                               "selected_configuration_sha256": CONFIG, "recorded_before_execution": True}
        enabled["requests"][0]["estimated_cost"].update(amount=.001, basis_sha256=H)
        for changed in (None, "reasoning_sha256", "model"):
            with self.subTest(changed=changed):
                value = deepcopy(enabled)
                if changed:
                    value["configuration"][changed] = J if changed == "reasoning_sha256" else "fixture-other"
                    selected = model_configuration_sha256(value["configuration"])
                    value["requests"][0]["configuration_sha256"] = selected
                    value["guidance"]["selected_configuration_sha256"] = selected
                report = compare_runs(disabled, value, quality_disabled=quality(), quality_enabled=quality())
                self.assertTrue(report["controlled"])
                self.assertEqual(metric(report, "estimated_cost")["comparable"], changed == "model")
                self.assertEqual(report["claims"]["estimated_cost"], "improvement" if changed == "model" else "not_demonstrated")

    def test_rendered_reductions_do_not_claim_savings_when_quality_regresses(self):
        disabled, enabled = run(), run("enabled")
        for value in (disabled, enabled):
            value["source_kind"] = "captured"
            value["requests"][0]["usage"]["source_kind"] = "provider_reported"
        enabled["requests"][0]["usage"] = usage(input_tokens=50, total_tokens=120, source_kind="provider_reported")
        report = compare_runs(disabled, enabled, quality_disabled=quality(),
                              quality_enabled=quality(quality_pass=False, critical_pass=False))
        self.assertEqual(report["claims"]["total_tokens"], "not_demonstrated")
        rendered = render_markdown(report)
        self.assertIn("29.411765% reduction", rendered)
        self.assertNotIn("% savings", rendered)
        self.assertIn("total_tokens=not_demonstrated", rendered)
        self.assertIn("total_tokens=complete / complete", rendered)

    def test_quality_is_bound_to_answer_task_and_rubric(self):
        for key in ("answer_sha256", "observation_sha256", "task_sha256", "rubric_sha256", "task_id"):
            score = quality(**{key: J if key != "task_id" else "different-task"})
            with self.subTest(key=key), self.assertRaises(MeasurementError):
                compare_runs(run(), run("enabled"), quality_enabled=score)

    def test_request_configuration_and_tool_completion_are_not_inferred(self):
        enabled = run("enabled")
        enabled["requests"][0]["configuration_sha256"] = None
        self.assertIn("request_configuration_unknown", compare_runs(run(), enabled)["control_limitations"])
        enabled["requests"][0]["configuration_sha256"] = J
        self.assertIn("request_configuration_deviation", compare_runs(run(), enabled)["control_limitations"])
        enabled = run("enabled")
        enabled["tools"][0]["state"] = "started"
        self.assertFalse(compare_runs(run(), enabled)["all_request_coverage"])

    def test_treatment_and_guidance_must_exist_before_claiming_enabled(self):
        enabled = run("enabled")
        enabled["configuration"]["tools"] = ["read"]
        self.assertIn("kre_treatment_unavailable", compare_runs(run(), enabled)["control_limitations"])
        disabled = run()
        for value in (disabled, enabled):
            value["comparison"] = {"system": "gcb", "allowed_differences": []}
        self.assertIn("gcb_guidance_unverified", compare_runs(disabled, enabled)["control_limitations"])

    def test_trial_order_and_retry_policy_are_explicit_controls(self):
        enabled = run("enabled", trial_order=None)
        self.assertIn("trial_order_unknown", compare_runs(run(), enabled)["control_limitations"])
        enabled = run("enabled")
        enabled["configuration"]["retry_policy_sha256"] = J
        self.assertIn("unmatched_retry_policy_sha256", compare_runs(run(), enabled)["control_limitations"])

    def test_missing_quality_blocks_success_and_unknown_scores_are_preserved(self):
        report = compare_runs(run(), run("enabled"))
        self.assertFalse(report["quality_preserved"])
        unknown = quality(quality_pass=None, critical_pass=None,
                          citation_support={"passed": 0, "total": 1, "unknown": 1, "score": None})
        report = compare_runs(run(), run("enabled"), quality_disabled=quality(), quality_enabled=unknown)
        self.assertFalse(report["quality_preserved"])
        self.assertIsNone(metric(report, "citation_support")["enabled"])

    def test_nonapplicable_quality_metrics_are_null_and_mixed_counts_rejected(self):
        null_metric = {"passed": None, "total": None, "unknown": None, "score": None}
        score = quality(**{key: null_metric for key in ("citation_exactness", "citation_support", "evidence_recall", "evidence_validity")})
        report = compare_runs(run(), run("enabled"), quality_disabled=score, quality_enabled=score)
        self.assertTrue(report["quality_preserved"])
        self.assertIsNone(metric(report, "citation_exactness")["enabled"])
        score = quality(citation_support={"passed": None, "total": 1, "unknown": 0, "score": None})
        with self.assertRaises(MeasurementError):
            compare_runs(run(), run("enabled"), quality_enabled=score)

    def test_real_cancelled_score_without_answer_is_retained_not_rejected(self):
        from kre.quality import rubric_hash, score_trial
        rubric = {"format": "task-quality-rubric/1", "task_id": "fixture.task", "task_sha256": H,
                  "criteria": [{"id": "correct", "category": "correctness", "critical": True,
                                "method": "exact", "path": ["ok"], "expected": True}]}
        good_observation = {"format": "task-quality-observation/1", "task_id": "fixture.task",
                            "task_sha256": H, "rubric_sha256": rubric_hash(rubric),
                            "completion": "completed", "answer": {"ok": True}}
        cancelled_observation = {key: value for key, value in good_observation.items() if key != "answer"}
        cancelled_observation["completion"] = "cancelled"
        good = score_trial(rubric, good_observation)
        cancelled = score_trial(rubric, cancelled_observation)
        self.assertIsNone(cancelled["answer_sha256"])
        disabled, enabled = run(), run("enabled", outcome="cancelled")
        for trace, score in ((disabled, good), (enabled, cancelled)):
            trace["identity"]["rubric_sha256"] = score["rubric_sha256"]
            trace["answer_sha256"] = score["answer_sha256"]
            trace["observation_sha256"] = score["observation_sha256"]
        report = compare_runs(disabled, enabled, quality_disabled=good, quality_enabled=cancelled)
        self.assertFalse(report["quality_preserved"])
        self.assertFalse(report["quality_enabled"]["quality_pass"])
        self.assertEqual(metric(report, "quality_pass")["change"]["percent"], -100)
        contradictory = dict(cancelled, completion_pass=True, critical_pass=True, quality_pass=True)
        with self.assertRaises(MeasurementError):
            compare_runs(disabled, enabled, quality_enabled=contradictory)

    def test_quality_regression_and_inconsistent_score_are_not_success(self):
        bad = quality(quality_pass=False, critical_pass=False)
        report = compare_runs(run(), run("enabled"), quality_disabled=quality(), quality_enabled=bad)
        self.assertFalse(report["quality_preserved"])
        self.assertEqual(metric(report, "quality_pass")["change"]["percent"], -100)
        impossible = quality(citation_exactness={"passed": 0, "total": 1, "unknown": 0, "score": 0.0})
        with self.assertRaises(MeasurementError):
            compare_runs(run(), run("enabled"), quality_enabled=impossible)
        cancelled = run("enabled", outcome="cancelled")
        self.assertFalse(compare_runs(run(), cancelled, quality_disabled=quality(), quality_enabled=quality())["quality_preserved"])

    def test_content_hash_measurement_and_output_do_not_export_bodies_or_request_ids(self):
        text = "private-fixture-☃"
        receipt = measure_content(text)
        self.assertEqual(receipt["bytes"], len(text.encode()))
        self.assertNotIn(text, json.dumps(receipt))
        value = run(requests=[request("private-request-identifier")])
        output = json.dumps(summarize_run(value))
        self.assertNotIn("private-request-identifier", output)
        value["requests"][0]["response_body"] = text
        with self.assertRaises(MeasurementError):
            summarize_run(value)

    def test_bounded_json_duplicate_keys_and_nonfinite_values(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '"' + 'x' * (2 * 1024 * 1024) + '"'):
            with self.subTest(size=len(text)), self.assertRaises(MeasurementError):
                strict_loads(text)

    def test_cli_safe_errors_and_reproducible_report(self):
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory) / "disabled.json", Path(directory) / "enabled.json"
            left.write_text(json.dumps(run()))
            right.write_text(json.dumps(run("enabled")))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["compare", str(left), str(right)]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result, compare_runs(load_json(left), load_json(right)))
            left.write_text('{"private_body":"do-not-print"}')
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["summarize", str(left)]), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertNotIn("do-not-print", err.getvalue())
            self.assertNotIn(directory, err.getvalue())


if __name__ == "__main__":
    unittest.main()
