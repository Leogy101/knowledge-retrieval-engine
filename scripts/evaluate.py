"""Frozen synthetic source/span evaluation; cases are now an authorized tuning set.

Run with PYTHONPATH=src python scripts/evaluate.py --split held_out --output FILE.
The overlap baseline shares eligibility, citation serialization and budgets, but
uses distinct query-token overlap instead of FTS5/BM25. Only equal labeled
coverage cases enter context-size comparisons. This is not answer evaluation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import tempfile
import time

from kre import Store

ROOT = Path(__file__).resolve().parents[1]
EVALUATION = ROOT / "evaluation"
REF_KEYS = ("source_id", "revision_id", "chunk_id", "content_sha256")


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_frozen(folder=EVALUATION):
    freeze = json.loads((folder / "freeze.json").read_text())
    for name, expected in freeze["files"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen fixture changed: create an explicit new evaluation version")
    corpus = json.loads((folder / "corpus.json").read_text())
    cases = json.loads((folder / "cases.json").read_text())
    return corpus, cases, freeze


def build_corpus(store, corpus):
    """Host preparation only; gold spans do not determine index chunks."""
    versions, expected = {}, {}
    for source in corpus["sources"]:
        labels = {k: source.get(k, default) for k, default in (
            ("authority", "unverified"), ("origin", "source_evidence"),
            ("freshness", "unknown"), ("egress", "local_only"))}
        ids = []
        for version in source["versions"]:
            revision = store.ingest_text(source["source_id"], version["text"],
                                         collection=source["collection"], **labels)
            normalized = version["text"].removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
            versions[(source["source_id"], version["label"])] = revision
            expected[revision] = {"source_id": source["source_id"], "version": version["label"],
                                  "text": normalized, "collection": source["collection"],
                                  "lifecycle": "superseded", "state": "active", **labels,
                                  "chunks": {f"c-{row['id']}": (row["line_start"], row["line_end"], row["text"])
                                             for row in store.db.execute("SELECT * FROM chunks WHERE revision_id=?", (revision,))}}
            ids.append(revision)
        expected[ids[-1]]["lifecycle"] = "active"
        if source.get("policy_updates"):
            store.update_policy(source["source_id"], **source["policy_updates"])
            for revision in ids:
                expected[revision].update(source["policy_updates"])
        if source.get("lifecycle_action"):
            store.lifecycle(source["source_id"], source["lifecycle_action"])
            for revision in ids:
                expected[revision].update(state="revoked", lifecycle="revoked")
    return versions, expected


def request_for(case, manifest):
    return {"contract_version": "0.1", "request_id": case["id"], "query": case["query"],
            "access_scope_ref": case.get("scope", "public-reader"), "destination": "local_only",
            "purpose": case.get("purpose", "current_answer"),
            "freshness_requirement": case.get("freshness_requirement", "allow_unknown"),
            "budget": dict(case.get("budget", manifest["default_budget"]))}


def refs_for(store, case, versions):
    refs = []
    for span in case.get("required", []):
        revision = versions.get((span["source_id"], span["version"]))
        if revision is None:
            refs.append({"source_id": span["source_id"], "revision_id": "r-" + "0" * 32,
                         "chunk_id": "c-999999", "content_sha256": "0" * 64})
            continue
        row = store.db.execute("SELECT * FROM chunks WHERE revision_id=? AND line_start<=? AND line_end>=? ORDER BY id",
                               (revision, span["line_start"], span["line_end"])).fetchone()
        if row is None:
            raise ValueError("Frozen required source span is not contained by any actual chunk")
        refs.append({"source_id": span["source_id"], "revision_id": revision,
                     "chunk_id": f"c-{row['id']}", "content_sha256": sha(row["text"])})
    return refs


def identity(ref):
    return tuple(ref[k] for k in REF_KEYS)


def eligible_rows(store, request):
    """Baseline admission uses exactly the same host scope and lifecycle rules."""
    rows = store.db.execute("""SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,
        s.authority,s.origin,s.freshness,s.egress,s.collection,s.state
        FROM chunks c JOIN revisions r ON c.revision_id=r.revision_id
        JOIN sources s ON r.source_id=s.source_id ORDER BY c.id""").fetchall()
    return [row for row in rows if row["collection"] in store.scopes[request["access_scope_ref"]]
            and row["state"] == "active" and row["lifecycle"] in {"active", "superseded"}
            and (request["purpose"] != "current_answer" or (row["lifecycle"] == "active" and row["freshness"] != "stale"))
            and (request.get("freshness_requirement") != "fresh_only" or row["freshness"] == "fresh")]


def overlap_baseline(store, request, refs):
    """Independent simple ranker; no labels/gold are consulted here."""
    rows = eligible_rows(store, request)
    by_ref = {identity({"source_id": row["source_id"], "revision_id": row["revision_id"],
                        "chunk_id": f"c-{row['id']}", "content_sha256": sha(row["text"])}): row for row in rows}
    response = store._response(request)  # common envelope/citation overhead, not shared ranking
    missing = [{"ref": ref, "reason": "unavailable"} for ref in refs if identity(ref) not in by_ref]
    selected = []
    budget = request["budget"]
    allowance = min(budget["max_tokens"], budget["max_bytes"])

    def failure(code, missing_refs):
        context = store._response(request, code=code)
        return {"wrapper_version": "kre-required/1", "status": "error", "context": context,
                "required": {"requested": refs, "delivered": [], "missing": missing_refs}, "error": context["error"]}

    if missing:
        return failure("REQUIRED_EVIDENCE_MISSING", missing)
    for ref in refs:
        selected.append(store._item(by_ref[identity(ref)], f"E{len(selected) + 1}"))
    if len(selected) > budget["max_items"] or len(store._render(selected).encode()) > allowance:
        return failure("BUDGET_TOO_SMALL", [{"ref": ref, "reason": "budget"} for ref in refs])
    terms = set(re.findall(r"\w+", request["query"].casefold()))
    ranked = []
    for row in rows:
        score = len(terms & set(re.findall(r"\w+", row["text"].casefold())))
        if score:
            ranked.append((-score, row["id"], row))
    ranked.sort(key=lambda value: (value[0], value[1]))
    omitted = 0
    required_ids = {ref["chunk_id"] for ref in refs}
    for _, _, row in ranked[:budget["max_items"] * 4]:
        if f"c-{row['id']}" in required_ids:
            continue
        if len(selected) >= budget["max_items"]:
            break
        item = store._item(row, f"E{len(selected) + 1}")
        if len(store._render([*selected, item]).encode()) > allowance:
            omitted += 1
            continue
        selected.append(item)
    if not selected and ranked:
        return failure("BUDGET_TOO_SMALL", [])
    response.update(items=selected, context_text=store._render(selected))
    size = len(response["context_text"].encode())
    response["token_usage"].update(context_bytes=size, estimated_tokens=size)
    if omitted:
        response.update(status="partial", coverage="partial", omissions={"budget": omitted})
    return {"wrapper_version": "kre-required/1", "status": response["status"], "context": response,
            "required": {"requested": refs, "delivered": refs, "missing": []}, "error": None}


def execute_kre(store, request, refs, required):
    if required:
        return store.context_required(request, required_refs=refs)
    context = store.context(request)
    return {"wrapper_version": "evaluation-plain/1", "status": context["status"], "context": context,
            "required": {"requested": [], "delivered": [], "missing": []}, "error": context["error"]}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def score(case, request, wrapper, refs, versions, expected, scopes):
    context = wrapper["context"]
    items = context["items"]
    exact, relevant = [], []
    covered = set()
    unauthorized, freshness, metadata = 0, 0, 0
    gold = case["gold"]
    for item in items:
        source = expected.get(item["revision_id"])
        locator = item["locator"]
        start, end = locator["line_start"], locator["line_end"]
        citation_ok = bool(source and source["source_id"] == item["source_id"]
                           and type(start) is int and type(end) is int and 1 <= start <= end <= len(source["text"].split("\n"))
                           and "\n".join(source["text"].split("\n")[start-1:end]) == item["text"]
                           and sha(item["text"]) == item["content_sha256"]
                           and source["chunks"].get(item["chunk_id"]) == (start, end, item["text"]))
        exact.append(citation_ok)
        if not source or source["collection"] not in scopes[request["access_scope_ref"]] or source["state"] != "active":
            unauthorized += 1
        if source:
            freshness += int((request["purpose"] == "current_answer" and (source["lifecycle"] != "active" or source["freshness"] == "stale"))
                             or (request.get("freshness_requirement") == "fresh_only" and source["freshness"] != "fresh"))
            metadata += int(any(item[k] != source[k] for k in ("authority", "origin", "freshness", "lifecycle"))
                            or item["egress"]["restriction"] != source["egress"])
        matches = [index for index, span in enumerate(gold) if citation_ok
                   and item["source_id"] == span["source_id"]
                   and item["revision_id"] == versions[(span["source_id"], span["version"])]
                   and start <= span["line_start"] and end >= span["line_end"]]
        covered.update(matches)
        relevant.append(bool(matches))
    returned_sources = {item["source_id"] for item in items}
    gold_sources = {unit["source_id"] for unit in gold}
    matched_sources = {gold[index]["source_id"] for index in covered}
    actual_refs = {identity(item) for item in items}
    delivered = [ref for ref in refs if identity(ref) in actual_refs]
    size = len(context["context_text"].encode("utf-8"))
    budget = request["budget"]
    accounting_ok = (size == context["token_usage"]["context_bytes"] == context["token_usage"]["estimated_tokens"]
                     and size <= min(budget["max_tokens"], budget["max_bytes"])
                     and len(items) <= budget["max_items"]
                     and len(json.dumps(context, ensure_ascii=False).encode()) <= 1048576
                     and context["context_text"] == Store._render(items))
    required_ok = True
    reporting_ok = (wrapper["required"]["requested"] == refs
                    and {identity(ref) for ref in wrapper["required"]["delivered"]} == {identity(ref) for ref in delivered}
                    and all(identity(entry["ref"]) in {identity(ref) for ref in refs}
                            and entry["reason"] in {"unavailable", "budget"} for entry in wrapper["required"]["missing"]))
    if "required" in case:
        expectation = case["required_expectation"]
        if expectation == "delivered":
            required_ok = len(delivered) == len(refs) and not wrapper["error"] and not wrapper["required"]["missing"]
        else:
            code = "BUDGET_TOO_SMALL" if expectation == "budget" else "REQUIRED_EVIDENCE_MISSING"
            required_ok = (not items and context["context_text"] == "" and wrapper["error"] is not None
                           and wrapper["error"]["code"] == code and bool(wrapper["required"]["missing"])
                           and not wrapper["required"]["delivered"])
    unexpected_error = bool(wrapper["error"]) and case.get("required_expectation") not in {"budget", "unavailable"}
    return {"returned_items": len(items), "relevant_items": sum(relevant), "gold_spans": len(gold),
            "covered_gold_spans": len(covered), "span_precision": ratio(sum(relevant), len(items)),
            "span_recall": ratio(len(covered), len(gold)),
            "returned_sources": len(returned_sources), "relevant_sources": len(returned_sources & gold_sources),
            "gold_sources": len(gold_sources), "covered_gold_sources": len(matched_sources),
            "source_precision": ratio(len(returned_sources & gold_sources), len(returned_sources)),
            "source_recall": ratio(len(matched_sources), len(gold_sources)),
            "citation_exact": sum(exact), "citation_accuracy": ratio(sum(exact), len(items)),
            "unauthorized_or_revoked_items": unauthorized, "freshness_violations": freshness,
            "metadata_label_violations": metadata, "required_requested": len(refs),
            "required_delivered": len(delivered), "required_undelivered": len(refs)-len(delivered),
            "required_missing_report": wrapper["required"]["missing"], "required_behavior_correct": required_ok and reporting_ok, "required_reporting_correct": reporting_ok,
            "accounting_and_budget_correct": accounting_ok, "unexpected_error": unexpected_error, "context_bytes": size,
            "effective_byte_allowance": min(budget["max_tokens"], budget["max_bytes"]),
            "correctness_pass": all(exact) and not unauthorized and not freshness and not metadata and required_ok and reporting_ok and accounting_ok and not unexpected_error}


def percentile(values, probability):
    return sorted(values)[math.ceil(len(values) * probability)-1] if values else None


def evaluate(split="held_out", repetitions=5, folder=EVALUATION):
    if split not in {"development", "held_out", "all"} or not 1 <= repetitions <= 20:
        raise ValueError("Invalid evaluation split or repetition count")
    corpus, manifest, freeze = load_frozen(folder)
    cases = manifest["development"] + manifest["held_out"] if split == "all" else manifest[split]
    scratch = ROOT / ".scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="evaluation-", dir=scratch) as temporary:
        with Store(str(Path(temporary)/"evaluation.sqlite3"), principal="synthetic-evaluator",
                   scopes={key:set(value) for key,value in manifest["scopes"].items()}) as store:
            started=time.perf_counter();versions,expected=build_corpus(store,corpus);ingest_ms=(time.perf_counter()-started)*1000
            outputs=[]
            for index,case in enumerate(cases):
                request=request_for(case,manifest);refs=refs_for(store,case,versions)
                calls={"kre":lambda:execute_kre(store,request,refs,"required" in case),
                       "overlap_baseline":lambda:overlap_baseline(store,request,refs)}
                for call in calls.values():call()  # one explicit warmup per algorithm/case
                measurements={name:[] for name in calls};latest={}
                for repeat in range(repetitions):
                    order=list(calls) if (index+repeat)%2==0 else list(reversed(calls))
                    for name in order:
                        start=time.perf_counter();latest[name]=calls[name]();measurements[name].append((time.perf_counter()-start)*1000)
                algorithms={}
                for name,result in latest.items():
                    metric=score(case,request,result,refs,versions,expected,manifest["scopes"])
                    metric.update(latency_p50_ms=statistics.median(measurements[name]),latency_p95_ms=percentile(measurements[name],.95))
                    algorithms[name]={"metrics":metric,"status":result["status"],"error":result["error"],"items":result["context"]["items"],
                                      "context_text":result["context"]["context_text"],"latency_samples_ms":measurements[name]}
                comparable=bool(case["gold"]) and all(a["metrics"]["span_recall"]==1 and a["metrics"]["required_delivered"]==len(refs) for a in algorithms.values())
                outputs.append({"case_id":case["id"],"category":case["category"],"query":case["query"],"gold":case["gold"],
                                "request":request,"required_expectation":case.get("required_expectation"),"algorithms":algorithms,
                                "equal_labeled_and_required_coverage_for_size_comparison":comparable})
            summary={}
            for name in ("kre","overlap_baseline"):
                measured=[case["algorithms"][name]["metrics"] for case in outputs]
                quality=[case["algorithms"][name]["metrics"] for case in outputs if case["gold"] and case["required_expectation"] in (None,"delivered")]
                timings=[t for case in outputs for t in case["algorithms"][name]["latency_samples_ms"]]
                summary[name]={"cases":len(measured),"correctness_failures":sum(not m["correctness_pass"] for m in measured),
                    "positive_gold_achievable_cases":len(quality),"micro_span_recall":ratio(sum(m["covered_gold_spans"] for m in quality),sum(m["gold_spans"] for m in quality)),
                    "macro_span_recall":statistics.mean(m["span_recall"] for m in quality) if quality else None,
                    "micro_span_precision":ratio(sum(m["relevant_items"] for m in quality),sum(m["returned_items"] for m in quality)),
                    "micro_span_precision_all_cases":ratio(sum(m["relevant_items"] for m in measured),sum(m["returned_items"] for m in measured)),
                    "micro_source_precision_all_cases":ratio(sum(m["relevant_sources"] for m in measured),sum(m["returned_sources"] for m in measured)),
                    "micro_source_recall":ratio(sum(m["covered_gold_sources"] for m in quality),sum(m["gold_sources"] for m in quality)),
                    "empty_gold_cases":sum(m["gold_spans"]==0 for m in measured),
                    "empty_gold_cases_returning_items":sum(m["gold_spans"]==0 and m["returned_items"]>0 for m in measured),
                    "citation_accuracy":ratio(sum(m["citation_exact"] for m in measured),sum(m["returned_items"] for m in measured)),
                    "unauthorized_or_revoked_items":sum(m["unauthorized_or_revoked_items"] for m in measured),
                    "freshness_violations":sum(m["freshness_violations"] for m in measured),
                    "metadata_label_violations":sum(m["metadata_label_violations"] for m in measured),
                    "unexpected_errors":sum(m["unexpected_error"] for m in measured),
                    "required_requested":sum(m["required_requested"] for m in measured),
                    "required_delivered":sum(m["required_delivered"] for m in measured),
                    "required_undelivered":sum(m["required_undelivered"] for m in measured),
                    "required_behavior_failures":sum(not m["required_behavior_correct"] for m in measured),
                    "budget_or_accounting_failures":sum(not m["accounting_and_budget_correct"] for m in measured),
                    "latency_warm_p50_ms":statistics.median(timings),"latency_warm_p95_ms":percentile(timings,.95)}
            comparable=[case for case in outputs if case["equal_labeled_and_required_coverage_for_size_comparison"]]
            size_comparison={"case_ids":[case["case_id"] for case in comparable],"cases":len(comparable),
                "median_context_bytes":{name:statistics.median(case["algorithms"][name]["metrics"]["context_bytes"] for case in comparable) if comparable else None for name in summary}}
            return {"evaluation_version":manifest["version"],"split":split,"synthetic":True,"freeze":freeze,
                "evaluation_usage":{"status":"tuning_set","independent_holdout":False,
                    "authorization":"Real-World Readiness milestone explicitly permits analyzing and improving against the original held_out cases.",
                    "disclosure":"Original labels/splits remain unchanged. New results on these cases are development measurements, not independent validation. K2 results are preserved."},
                "runtime":{"python":platform.python_version(),"sqlite":sqlite3.sqlite_version,"platform":platform.platform()},
                "corpus_sources":len(corpus["sources"]),"corpus_chunks":store.db.execute("SELECT count(*) FROM chunks").fetchone()[0],
                "fresh_database_ingestion_ms":ingest_ms,"repetitions_per_case":repetitions,"summary":summary,
                "equal_coverage_size_comparison":size_comparison,"cases":outputs,"metric_policy":manifest["metric_policy"],
                "limitations":["Original held_out cases are now explicitly used for tuning; this is not an independent validation result.",
                    "Frozen synthetic source/span labels, not generated-answer correctness or real-world semantic quality.",
                    "Both methods use lexical matching; overlap baseline is case-folded Unicode words, while SQLite FTS5 applies its configured tokenizer.",
                    "Positive-gold quality aggregates exclude deliberately impossible required-ref/budget controls; all cases remain in per-case output.",
                    "Warm local query/admission/packing/serialization timings only; no cold process, adapter, network or model latency.",
                    "Byte accounting is a conservative heuristic, not a provider token count or token-saving proof.",
                    "Structured contradictions are labeled examples retrieved as evidence; no semantic conflict detector or answer generator is claimed.",
                    "A finite synthetic corpus and zero observed violations do not prove universal privacy or retrieval correctness."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split",choices=("development","held_out","all"),default="held_out")
    parser.add_argument("--repetitions",type=int,default=5)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args();report=evaluate(args.split,args.repetitions)
    rendered=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(rendered)
    print(json.dumps({"split":report["split"],"summary":report["summary"],"equal_coverage_size_comparison":report["equal_coverage_size_comparison"]},indent=2))
    return int(any(value["correctness_failures"] for value in report["summary"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
