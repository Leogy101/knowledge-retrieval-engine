#!/usr/bin/env python3
"""Evaluator implementation correction: decode JSON-rendered items before checking inclusion.
Original evaluate.py and its first outputs remain unchanged.
Offline evaluation of a separately supplied KRE source tree.

No KRE import occurs during authoring, manifest verification, or aggregation.
Only the --worker subprocess imports the evaluated source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def inventory(source_root):
    paths = sorted(p for p in (source_root / "src" / "kre").rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    if not paths:
        raise ValueError("No src/kre package in supplied source root")
    entries = {str(p.relative_to(source_root)): digest(p.read_bytes()) for p in paths}
    return {"files": entries, "sha256": digest(json_bytes(entries))}


def walk(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def request_for(case):
    # Ordinary requests receive only the question and the frozen contract options.
    # Gold, source IDs, expected sources and forbidden sources do not enter here.
    return {"contract_version": "0.1", "request_id": "holdout-" + case["id"],
            "query": case["question"], "access_scope_ref": "reader", **case["request"]}


def score(case, response, revision_ids, validation):
    docs = {d["id"]: d for d in case["documents"]}
    items = response.get("items", [])
    success = response.get("status") in ("ok", "partial") and response.get("error") is None
    citation_errors = []
    policy_errors = []
    citation_ids = []
    exact_items = []
    for index, item in enumerate(items):
        errors = []
        sid = item.get("source_id")
        document = docs.get(sid)
        if document is None:
            errors.append("unknown_source")
        else:
            if item.get("revision_id") != revision_ids.get(sid):
                errors.append("wrong_revision")
            locator = item.get("locator", {})
            start, end = locator.get("line_start"), locator.get("line_end")
            source_lines = document["text"].splitlines(keepends=True)
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(source_lines):
                errors.append("invalid_line_range")
            else:
                raw_slice = "".join(source_lines[start - 1:end])
                # A citation may omit the final line delimiter; no interior whitespace
                # is rewritten and no line omission or excerpt concatenation is allowed.
                acceptable = {raw_slice, raw_slice[:-1] if raw_slice.endswith("\n") else raw_slice}
                if item.get("text") not in acceptable:
                    errors.append("text_not_exact_cited_lines")
            if not isinstance(locator.get("label"), str) or not locator["label"]:
                errors.append("empty_locator_label")
            if document["collection"] != "shared":
                policy_errors.append({"item": index, "source_id": sid, "rule": "private_collection"})
            if document["lifecycle"] == "revoked":
                policy_errors.append({"item": index, "source_id": sid, "rule": "revoked"})
            historical = case["request"]["purpose"] == "historical_evidence"
            if document["lifecycle"] == "superseded" and not historical:
                policy_errors.append({"item": index, "source_id": sid, "rule": "superseded_current"})
            if document["freshness"] == "stale" and not historical:
                policy_errors.append({"item": index, "source_id": sid, "rule": "stale_current"})
            if case["request"]["freshness_requirement"] == "fresh_only" and document["freshness"] != "fresh":
                policy_errors.append({"item": index, "source_id": sid, "rule": "fresh_only"})
            if case["request"]["destination"] == "approved_remote" and document["egress"] == "local_only":
                policy_errors.append({"item": index, "source_id": sid, "rule": "local_only_egress"})
            if sid in case["forbidden_sources"]:
                policy_errors.append({"item": index, "source_id": sid, "rule": "frozen_forbidden_source"})
            for field in ("authority", "origin", "freshness", "lifecycle"):
                if item.get(field) != document[field]:
                    errors.append("wrong_" + field)
            if item.get("egress", {}).get("restriction") != document["egress"]:
                errors.append("wrong_egress_label")
        text = item.get("text")
        if not isinstance(text, str) or item.get("content_sha256") != digest((text or "").encode()):
            errors.append("wrong_text_hash")
        for key in ("citation_id", "chunk_id", "recorded_at"):
            if not isinstance(item.get(key), str) or not item[key]:
                errors.append("empty_" + key)
        cid = item.get("citation_id")
        if cid in citation_ids:
            errors.append("duplicate_citation_id")
        citation_ids.append(cid)
        rendered = response.get("context_text", "")
        if not isinstance(cid, str) or cid not in rendered:
            errors.append("citation_not_rendered")
        try:
            rendered_items = json.loads(rendered)
        except (ValueError, TypeError):
            rendered_items = None
        if rendered_items != items:
            errors.append("rendered_items_differ_from_items")
        if errors:
            citation_errors.append({"item": index, "source_id": sid, "errors": errors})
        else:
            exact_items.append(item)

    # Invalid, ineligible, error-shaped, or stale context earns no evidence credit.
    admissible = success and validation == "current" and not policy_errors
    supported = []
    for span in case["gold"]:
        found = admissible and any(
            item["source_id"] == span["source_id"] and span["quote"] in item["text"]
            and item["locator"]["line_start"] <= span["line_start"]
            and item["locator"]["line_end"] >= span["line_end"] for item in exact_items)
        supported.append({"id": span["id"], "covered": bool(found)})
    returned_sources = sorted({i.get("source_id", "") for i in items})
    relevant_sources = set(case["expected_sources"])
    relevant_returned = relevant_sources.intersection(returned_sources) if admissible else set()
    context_bytes = len(response.get("context_text", "").encode())
    usage = response.get("token_usage", {})
    estimate = usage.get("estimated_tokens")
    budget = case["request"]["budget"]
    budget_errors = []
    if context_bytes > budget["max_bytes"]:
        budget_errors.append("rendered_byte_ceiling")
    if type(estimate) is not int or estimate > budget["max_tokens"] or estimate < 0:
        budget_errors.append("estimated_token_ceiling_or_type")
    if len(items) > budget["max_items"]:
        budget_errors.append("item_ceiling")
    if usage.get("context_bytes") != context_bytes:
        budget_errors.append("reported_byte_mismatch")
    if usage.get("counter_kind") == "conservative_bytes" and estimate != context_bytes:
        budget_errors.append("conservative_estimate_mismatch")
    if usage.get("includes_citations") is not True:
        budget_errors.append("citation_accounting")
    if response.get("status") == "error" and (items or response.get("context_text")):
        budget_errors.append("nonempty_error_context")
    covered = sum(s["covered"] for s in supported)
    total = len(supported)
    return {"span_results": supported, "gold_spans": total, "covered_spans": covered,
            "evidence_recall": covered / total if total else None,
            "complete_evidence": covered == total if total else None,
            "returned_sources": returned_sources, "expected_sources": sorted(relevant_sources),
            "relevant_returned_sources": len(relevant_returned), "returned_source_count": len(returned_sources),
            "source_precision": len(relevant_returned) / len(returned_sources) if returned_sources else None,
            "items": len(items), "exact_citations": len(items) - len(citation_errors),
            "citation_errors": citation_errors, "policy_errors": policy_errors, "budget_errors": budget_errors,
            "rendered_context_bytes": context_bytes, "estimated_tokens": estimate,
            "token_counter_kind": usage.get("counter_kind"),
            "serialized_response_bytes": len(json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode()),
            "snapshot_validation": validation, "status": response.get("status"),
            "error_code": (response.get("error") or {}).get("code"), "coverage_label": response.get("coverage"),
            "unsupported_context_for_missing_question": case["expectation"]["kind"] == "missing" and bool(items),
            "unsupported_sufficiency_claim": case["expectation"]["kind"] == "missing" and response.get("coverage") == "sufficient",
            "tight_budget_failure": case["request"]["budget"]["max_tokens"] <= 800 and total > 0 and covered < total}


def timed(fn):
    start = time.perf_counter_ns()
    value = fn()
    return value, (time.perf_counter_ns() - start) / 1_000_000


def evaluate_case(case, Store, evidence_ref, workdir):
    start = time.perf_counter_ns()
    with Store(str(workdir / (case["id"] + ".sqlite3")), principal="synthetic-holdout-host",
               scopes={"reader": {"shared"}, "owner": {"shared", "private"}},
               destinations=frozenset({"local_only", "approved_remote"})) as store:
        revisions = {}
        for document in case["documents"]:
            revisions[document["id"]] = store.ingest_text(
                document["id"], document["text"], collection=document["collection"],
                **{k: document[k] for k in ("authority", "origin", "freshness", "egress")})
            if document["lifecycle"] != "active":
                action = {"superseded": "supersede", "revoked": "revoke"}[document["lifecycle"]]
                store.lifecycle(document["id"], action)
        setup_ms = (time.perf_counter_ns() - start) / 1_000_000
        request = request_for(case)
        result = {"case_id": case["id"], "category": case["category"], "kind": case["expectation"]["kind"], "gold_spans_expected": len(case["gold"]),
                  "request": request, "revision_ids": revisions, "setup_ms": setup_ms}
        kind = case["expectation"]["kind"]
        if kind in ("required_fit", "required_budget"):
            # These explicitly declared-reference cases are kept outside ordinary
            # retrieval scores. Their only gold-assisted input is preserved below.
            refs = []
            bootstrap = []
            for gid in case["required_gold_ids"]:
                span = next(g for g in case["gold"] if g["id"] == gid)
                known_request = dict(request, request_id=request["request_id"] + "-declared-" + gid,
                                     query=span["quote"], source_ids=[span["source_id"]],
                                     budget={"max_tokens": 32768, "max_bytes": 262144, "max_items": 32})
                prior, prior_ms = timed(lambda: store.context(known_request))
                matching = [item for item in prior.get("items", [])
                            if item["source_id"] == span["source_id"] and span["quote"] in item["text"]]
                bootstrap.append({"gold_id": gid, "request": known_request, "response": prior, "latency_ms": prior_ms})
                if not matching:
                    raise RuntimeError("Declared-reference bootstrap unavailable for " + gid)
                refs.append(evidence_ref(matching[0]))
            refs = list({json.dumps(ref, sort_keys=True): ref for ref in refs}.values())
            wrapper, latency = timed(lambda: store.context_required(request, required_refs=refs))
            response = wrapper["context"]
            result.update(required_refs=refs, declared_reference_bootstrap=bootstrap, required_wrapper=wrapper)
        else:
            response, latency = timed(lambda: store.context(request))
        validation = store.validate_context(response, scope_ref="reader", destination=request["destination"])
        result.update(response=response, retrieval_latency_ms=latency,
                      metrics=score(case, response, revisions, validation))
        if kind == "policy":
            result["expected_behavior_pass"] = (response.get("status") == "error"
                                                  and bool(response.get("error"))
                                                  and not response.get("items") and not response.get("context_text"))
        elif kind == "required_budget":
            error = result["required_wrapper"].get("error") or {}
            result["expected_behavior_pass"] = (error.get("code") == "BUDGET_TOO_SMALL"
                                                  and not response.get("items") and not response.get("context_text"))
        elif kind == "required_fit":
            result["expected_behavior_pass"] = result["required_wrapper"].get("error") is None and result["metrics"]["complete_evidence"]
        elif kind == "missing":
            result["expected_behavior_pass"] = not result["metrics"]["unsupported_sufficiency_claim"]
        else:
            result["expected_behavior_pass"] = result["metrics"]["complete_evidence"]
        if kind == "checkpoint":
            continuity = case["continuity"]
            candidates = [i for i in response.get("items", []) if i["source_id"] == continuity["source_id"]
                          and any(span["quote"] in i["text"] for span in case["gold"])]
            if not candidates or not result["metrics"]["complete_evidence"]:
                result["continuity"] = {"pass": False, "setup_failure": "required_initial_evidence_not_retrieved"}
            else:
                item = candidates[0]
                assertion = lambda text: {"text": text, "origin": "user_assertion", "refs": []}
                card = {"objective": assertion("Prepare the morning volunteer briefing."),
                        "constraints": [assertion(continuity["independent_assertion"])],
                        "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [evidence_ref(item)]}],
                        "questions": [assertion("Which entries still need confirmation?")],
                        "next_actions": [assertion("Check the current guidance before briefing.")]}
                saved, save_ms = timed(lambda: store.checkpoint_task("morning-briefing", scope_ref="reader", card=card))
                before, before_ms = timed(lambda: store.resume_task("morning-briefing", scope_ref="reader"))
                store.lifecycle(continuity["source_id"], continuity["action"])
                after, after_ms = timed(lambda: store.resume_task("morning-briefing", scope_ref="reader"))
                before_strings = [v for v in walk(before) if isinstance(v, str)]
                after_strings = [v for v in walk(after) if isinstance(v, str)]
                before_supported = item["text"] in before_strings
                dependent_removed = not any(span["quote"] in text for span in case["gold"] for text in after_strings)
                assertion_kept = continuity["independent_assertion"] in after_strings
                invalidations = [v["invalidated"] for v in walk(after) if isinstance(v, dict) and "invalidated" in v]
                invalidation_visible = any(bool(v) for v in invalidations)
                old_validation = store.validate_context(response, scope_ref="reader", destination=request["destination"])
                continuity_pass = before_supported and dependent_removed and assertion_kept and invalidation_visible and old_validation != "current"
                result["continuity"] = dict(card=card, checkpoint_result=saved, before=before, after=after,
                    checkpoint_latency_ms=save_ms, resume_before_latency_ms=before_ms, resume_after_latency_ms=after_ms,
                    before_supported=before_supported, dependent_removed=dependent_removed,
                    independent_assertion_retained=assertion_kept, invalidation_visible=invalidation_visible,
                    previous_context_validation=old_validation, **{"pass": continuity_pass})
                result["expected_behavior_pass"] = bool(result["expected_behavior_pass"] and continuity_pass)
        return result


def aggregate(results):
    def group(rows):
        complete = [r for r in rows if "metrics" in r]
        ms = [r["metrics"] for r in complete]
        gold_n = sum(r["gold_spans_expected"] for r in rows)
        hit_n = sum(m["covered_spans"] for m in ms)
        source_n = sum(m["returned_source_count"] for m in ms)
        relevant_n = sum(m["relevant_returned_sources"] for m in ms)
        latencies = sorted(r["retrieval_latency_ms"] for r in complete)
        return {"cases": len(rows), "execution_errors": len(rows) - len(complete),
                "gold_spans": gold_n, "covered_spans": hit_n, "evidence_recall": hit_n / gold_n if gold_n else None,
                "positive_cases": sum(r["gold_spans_expected"] > 0 for r in rows),
                "complete_positive_cases": sum(m["complete_evidence"] is True for m in ms),
                "returned_source_incidences": source_n, "relevant_returned_source_incidences": relevant_n,
                "source_precision": relevant_n / source_n if source_n else None,
                "items": sum(m["items"] for m in ms), "exact_citations": sum(m["exact_citations"] for m in ms),
                "citation_error_items": sum(len(m["citation_errors"]) for m in ms),
                "policy_error_events": sum(len(m["policy_errors"]) for m in ms),
                "budget_error_events": sum(len(m["budget_errors"]) for m in ms),
                "tight_budget_failures": sum(m["tight_budget_failure"] for m in ms),
                "rendered_context_bytes": sum(m["rendered_context_bytes"] for m in ms),
                "estimated_tokens": sum(m["estimated_tokens"] or 0 for m in ms),
                "serialized_response_bytes": sum(m["serialized_response_bytes"] for m in ms),
                "retrieval_latency_ms_median": statistics.median(latencies) if latencies else None,
                "retrieval_latency_ms_p95_nearest_rank": latencies[math.ceil(.95 * len(latencies)) - 1] if latencies else None,
                "expected_behavior_passes": sum(bool(r.get("expected_behavior_pass")) for r in complete)}
    required = {"required_fit", "required_budget"}
    ordinary = [r for r in results if r["kind"] not in required]
    return {"ordinary": group(ordinary),
            "ordinary_positive": group([r for r in ordinary if r["kind"] not in {"missing", "policy"}]),
            "declared_required_references": group([r for r in results if r["kind"] in required]),
            "policy_missing_controls": group([r for r in results if r["kind"] in {"missing", "policy"}]),
            "all_cases_diagnostic_only": group(results),
            "human_semantic_review": "unknown", "generated_answer_quality": "not_measured",
            "provider_tokens": None, "inference_calls": 0, "network_calls": 0}


def worker(args):
    def offline_audit(event, audit_args):
        if event.startswith("socket.") or event in {"subprocess.Popen", "os.system"}:
            raise RuntimeError("offline evaluator forbids " + event)
    sys.addaudithook(offline_audit)
    source = Path(args.source_root).resolve()
    sys.path.insert(0, str(source / "src"))
    import kre
    from kre import Store, evidence_ref
    if not Path(kre.__file__).resolve().is_relative_to(source / "src" / "kre"):
        raise RuntimeError("Imported package outside supplied source root")
    fixture = json.loads((ROOT / "fixture.json").read_text())
    results = []
    with tempfile.TemporaryDirectory(prefix="kre-alpha-holdout-") as temporary:
        for case in fixture["cases"]:
            try:
                results.append(evaluate_case(case, Store, evidence_ref, Path(temporary)))
            except Exception as exc:
                results.append({"case_id": case["id"], "category": case["category"], "kind": case["expectation"]["kind"], "gold_spans_expected": len(case["gold"]),
                                "request": request_for(case),
                                "execution_error": type(exc).__name__ + ": " + str(exc), "traceback": traceback.format_exc()})
    payload = {"imported_package": str(Path(kre.__file__).resolve()), "python": sys.version,
               "results": results, "aggregate": aggregate(results)}
    Path(args.output).write_bytes(json_bytes(payload))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--revision-label")
    parser.add_argument("--algorithm-lock")
    parser.add_argument("--expected-lock-sha256")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not all((args.revision_label, args.algorithm_lock, args.expected_lock_sha256)):
        parser.error("A named locked revision and the exact algorithm-lock hash are mandatory")
    freeze = json.loads((ROOT / "freeze-manifest.json").read_text())
    for relative, expected in freeze["files"].items():
        actual = digest((ROOT / relative).read_bytes())
        if actual != expected:
            raise RuntimeError("Frozen artifact changed: " + relative)
    lock = Path(args.algorithm_lock).resolve()
    if digest(lock.read_bytes()) != args.expected_lock_sha256:
        raise RuntimeError("Algorithm-lock hash mismatch")
    source = Path(args.source_root).resolve()
    before = inventory(source)
    output = Path(args.output).resolve()
    if output.exists():
        raise RuntimeError("Refusing to overwrite an evaluation output")
    output.parent.mkdir(parents=True, exist_ok=True)
    attempts = ROOT / "executions"
    attempts.mkdir(exist_ok=True)
    claim_path = attempts / (before["sha256"] + ".started.json")
    claim = {"revision_label": args.revision_label, "source_root": str(source),
             "source_inventory": before, "algorithm_lock_sha256": args.expected_lock_sha256,
             "freeze_manifest_sha256": digest((ROOT / "freeze-manifest.json").read_bytes()),
             "fixture_sha256": digest((ROOT / "fixture.json").read_bytes()),
             "started_at_unix": time.time(), "output": str(output)}
    with claim_path.open("xb") as stream:
        stream.write(json_bytes(claim))
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryDirectory(prefix="kre-holdout-worker-") as temporary:
        raw = Path(temporary) / "worker.json"
        command = [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker",
                   "--source-root", str(source), "--output", str(raw)]
        begun = time.perf_counter_ns()
        completed = subprocess.run(command, cwd=temporary, env=env, text=True, capture_output=True, timeout=180)
        elapsed = (time.perf_counter_ns() - begun) / 1_000_000
        after = inventory(source)
        record = {"provenance": claim, "source_inventory_after": after,
                  "source_unchanged": before == after, "worker_elapsed_ms": elapsed,
                  "worker_returncode": completed.returncode, "worker_stdout": completed.stdout,
                  "worker_stderr": completed.stderr,
                  "evaluation": json.loads(raw.read_text()) if raw.exists() else None}
        with output.open("xb") as stream:
            stream.write(json_bytes(record))
    print(json.dumps({"path": str(output), "sha256": digest(output.read_bytes()),
                      "source_unchanged": record["source_unchanged"],
                      "worker_returncode": completed.returncode}))


if __name__ == "__main__":
    main()
