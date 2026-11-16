#!/usr/bin/env python3
"""Offline frozen transfer evaluation; no generated-answer or semantic scoring.

Each implementation runs in a separate isolated Python subprocess and new Store.
The gold is used only after Store.context, never as retrieval hints or required refs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_HASH = "60c1d649cf1175e73b96407a3c13e444f95564d9eeccfc678fecb6e36548a582"
CURRENT_INGESTION_HASH = "16dd33a740fcc60980020646f5444d06000079cbb74aeeba1d51ec21f703d6b1"
BASELINE_COMMIT = "74ee976aa1a52e8aba314466ee125e9e79c81436"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_frozen(folder):
    manifest = json.loads((folder / "SHA256_MANIFEST.json").read_text())
    for entry in manifest["files"]:
        path = folder / entry["path"]
        if path.parent != folder or sha256(path.read_bytes()) != entry["sha256"]:
            raise ValueError(f"Frozen artifact changed: {entry['path']}")
    raw = (folder / "offline-transfer-eight.v1.json").read_bytes()
    if sha256(raw) != FIXTURE_HASH:
        raise ValueError("Frozen fixture hash differs from pre-retrieval commitment")
    fixture = json.loads(raw)
    for case in fixture["cases"]:
        for gold in case["gold"]:
            source = next(s for s in fixture["sources"] if s["source_id"] == gold["source_id"])
            if "\n".join(source["text"].splitlines()[gold["line_start"] - 1:gold["line_end"]]) != gold["quote"]:
                raise ValueError("Gold quote differs from exact source lines")
    return fixture, manifest


def request_for(case):
    return {"contract_version": "0.1", "request_id": case["id"], "query": case["query"],
            "access_scope_ref": case["scope"], "destination": case["destination"],
            "purpose": case["purpose"], "budget": dict(case["budget"])}


def render(items):
    return json.dumps(items, ensure_ascii=False, separators=(",", ":")) if items else ""


def score_case(fixture, case, response, registry):
    """Measure literal coverage and safety; request errors remain zero-coverage rows.

    registry records actual ingested immutable chunks. Exact source text, locator,
    text hash, revision/chunk identity, policy labels, and eligibility are checked
    separately. A span may be covered by multiple exact, eligible chunks.
    """
    sources = {s["source_id"]: s for s in fixture["sources"]}
    chunks = {(r["source_id"], r["revision_id"], r["chunk_id"]): r for r in registry}
    scope = set(fixture["scope_definitions"][case["scope"]]["collections"])
    items = response["items"]
    checks, eligible_exact = [], []
    for item in items:
        source = sources.get(item.get("source_id"))
        row = chunks.get(tuple(item.get(k) for k in ("source_id", "revision_id", "chunk_id")))
        loc = item.get("locator", {})
        start, end = loc.get("line_start"), loc.get("line_end")
        valid_range = bool(source and type(start) is int and type(end) is int
                           and 1 <= start <= end <= len(source["text"].splitlines()))
        source_text = "\n".join(source["text"].splitlines()[start - 1:end]) if valid_range else None
        exact_text = valid_range and item.get("text") == source_text
        text_hash = isinstance(item.get("text"), str) and item.get("content_sha256") == sha256(item["text"].encode("utf-8"))
        identity = bool(row and row["text"] == item.get("text") and row["line_start"] == start
                        and row["line_end"] == end and row["content_sha256"] == item.get("content_sha256"))
        labels = bool(source and all(item.get(k) == source[k] for k in ("authority", "origin", "freshness"))
                      and item.get("egress", {}).get("restriction") == "local_only"
                      and row and item.get("lifecycle") == row["lifecycle"])
        scope_ok = bool(source and source["collection"] in scope)
        lifecycle_ok = bool(source and source["state"] == "active" and row and row["lifecycle"] == "active")
        freshness_ok = bool(source and source["freshness"] != "stale")
        forbidden_ok = item.get("source_id") not in case["forbidden_sources"]
        exact = bool(exact_text and text_hash and identity)
        permitted = bool(scope_ok and lifecycle_ok and freshness_ok and forbidden_ok)
        checks.append({"citation_id": item.get("citation_id"), "source_id": item.get("source_id"),
                       "exact_source_lines": bool(exact_text), "text_sha256_correct": bool(text_hash),
                       "immutable_chunk_identity_correct": identity, "policy_labels_correct": labels,
                       "scope_allowed": scope_ok, "lifecycle_allowed": lifecycle_ok,
                       "freshness_allowed": freshness_ok, "not_forbidden": forbidden_ok})
        if exact and permitted and labels:
            eligible_exact.append(item)
    spans = []
    for gold in case["gold"]:
        expected = set(range(gold["line_start"], gold["line_end"] + 1))
        covered, citations = set(), []
        for item in eligible_exact:
            if item["source_id"] != gold["source_id"]:
                continue
            loc = item["locator"]
            overlap = expected & set(range(loc["line_start"], loc["line_end"] + 1))
            if overlap:
                covered |= overlap
                citations.append(item["citation_id"])
        spans.append({"source_id": gold["source_id"], "line_start": gold["line_start"],
                      "line_end": gold["line_end"], "quote_sha256": sha256(gold["quote"].encode("utf-8")),
                      "covered": covered == expected, "covered_lines": sorted(covered),
                      "missing_lines": sorted(expected - covered), "citation_ids": citations})
    context = response["context_text"]
    size = len(context.encode("utf-8"))
    payload = sum(len(item["text"].encode("utf-8")) for item in items)
    usage = response["token_usage"]
    budget = case["budget"]
    budget_ok = size <= budget["max_bytes"] and usage["estimated_tokens"] <= budget["max_tokens"] and len(items) <= budget["max_items"]
    rendered_ok = context == render(items)
    accounting_ok = (usage["context_bytes"] == size and usage["estimated_tokens"] == size
                     and usage["counter_kind"] == "conservative_bytes" and usage["counter_id"] == "utf8_bytes"
                     and usage["includes_citations"] is True)
    error_ok = ((response["status"] == "error" and response["error"] is not None and not items and not context)
                or (response["status"] in {"ok", "partial"} and response["error"] is None))
    citations_ok = all(c[k] for c in checks for k in ("exact_source_lines", "text_sha256_correct", "immutable_chunk_identity_correct", "policy_labels_correct"))
    restrictions_ok = all(c[k] for c in checks for k in ("scope_allowed", "lifecycle_allowed", "freshness_allowed", "not_forbidden"))
    covered_count = sum(s["covered"] for s in spans)
    total_lines = sum(s["line_end"] - s["line_start"] + 1 for s in spans)
    covered_lines = sum(len(s["covered_lines"]) for s in spans)
    return {"id": case["id"], "response_status": response["status"], "request_error": response["error"],
            "query_distinct_terms": len(set(re.findall(r"\w+", case["query"]))),
            "gold_spans_covered": covered_count, "gold_spans_total": len(spans),
            "gold_span_coverage": covered_count / len(spans) if spans else None,
            "gold_lines_covered": covered_lines, "gold_lines_total": total_lines,
            "gold_line_coverage": covered_lines / total_lines if total_lines else None,
            "gold": spans, "item_checks": checks,
            "retrieved_sources": sorted({i["source_id"] for i in items}),
            "context_sizes": {"items": len(items), "utf8_bytes": size, "estimated_tokens": usage["estimated_tokens"],
                              "payload_utf8_bytes": payload, "citation_and_metadata_utf8_bytes": size - payload},
            "budget": dict(budget), "omissions": response["omissions"], "warnings": response["warnings"],
            "integrity": {"exact_citations_and_labels": citations_ok, "scope_lifecycle_freshness": restrictions_ok,
                          "budget": budget_ok, "context_rendering": rendered_ok, "token_accounting": accounting_ok,
                          "error_shape": error_ok},
            "integrity_pass": all((citations_ok, restrictions_ok, budget_ok, rendered_ok, accounting_ok, error_ok))}


def package_manifest(root):
    return {str(p.relative_to(root)): sha256(p.read_bytes()) for p in sorted((root / "src/kre").rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def run_worker(source_root, fixture_dir, output):
    sys.path.insert(0, str(source_root / "src"))
    from kre import Store
    import kre.store
    import kre.ingestion
    if not Path(kre.store.__file__).resolve().is_relative_to(source_root.resolve()):
        raise RuntimeError("Implementation import escaped isolated source snapshot")
    fixture, _ = load_frozen(fixture_dir)
    scopes = {name: set(value["collections"]) for name, value in fixture["scope_definitions"].items()}
    started = utc_now()
    with Store(":memory:", principal="post96-transfer-evaluator", scopes=scopes,
               destinations=frozenset({"local_only"})) as store:
        for source in fixture["sources"]:
            store.ingest_text(source["source_id"], source["text"], collection=source["collection"],
                              authority=source["authority"], origin=source["origin"], freshness=source["freshness"], egress="local_only")
            if source["state"] == "revoked":
                store.revoke(source["source_id"])
        registry = [dict(row) for row in store.db.execute(
            "SELECT r.source_id,r.revision_id,('c-'||c.id) AS chunk_id,c.text,c.line_start,c.line_end,r.lifecycle "
            "FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id ORDER BY c.id")]
        for row in registry:
            row["content_sha256"] = sha256(row["text"].encode("utf-8"))
        rows = []
        for case in fixture["cases"]:
            request = request_for(case)
            before = perf_counter_ns()
            response = store.context(request)
            elapsed = perf_counter_ns() - before
            scored = score_case(fixture, case, response, registry)
            rows.append({"request": request, "response": response, "metrics": scored,
                         "query_elapsed_ns_descriptive_only": elapsed})
    result = {"schema_version": 1, "evaluation_kind": "offline_literal_evidence_transfer",
              "semantic_answer_judgment": False, "model_or_network_calls": 0,
              "started_at_utc": started, "completed_at_utc": utc_now(),
              "fixture_sha256": FIXTURE_HASH, "source_package_sha256": package_manifest(source_root),
              "store_module": str(Path(kre.store.__file__).resolve()), "parser_version": kre.ingestion.PARSER_VERSION,
              "runtime": {"python": platform.python_version(), "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
              "source_count": len(fixture["sources"]), "ingested_chunk_count": len(registry),
              "registry": registry, "cases": rows}
    write_json(output, result)


def snapshot_sources(repository, destination, commit=None):
    if commit:
        names = subprocess.check_output(["git", "-C", str(repository), "ls-tree", "-r", "--name-only", commit, "src/kre"], text=True).splitlines()
        for name in names:
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(subprocess.check_output(["git", "-C", str(repository), "show", f"{commit}:{name}"]))
    else:
        shutil.copytree(repository / "src/kre", destination / "src/kre", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def summarize(result):
    metrics = [row["metrics"] for row in result["cases"]]
    covered = sum(row["gold_spans_covered"] for row in metrics)
    total = sum(row["gold_spans_total"] for row in metrics)
    return {"case_count": len(metrics), "gold_spans_covered": covered, "gold_spans_total": total,
            "gold_span_coverage": covered / total, "all_gold_covered_cases": sum(row["gold_spans_covered"] == row["gold_spans_total"] for row in metrics),
            "request_errors": [{"id": row["id"], "error": row["request_error"]} for row in metrics if row["request_error"]],
            "integrity_pass_cases": sum(row["integrity_pass"] for row in metrics),
            "total_context_bytes": sum(row["context_sizes"]["utf8_bytes"] for row in metrics),
            "total_items": sum(row["context_sizes"]["items"] for row in metrics)}


def compare(args):
    fixture_dir, output = args.fixture_directory.resolve(), args.output.resolve()
    fixture, _ = load_frozen(fixture_dir)
    if sha256((ROOT / "src/kre/ingestion.py").read_bytes()) != CURRENT_INGESTION_HASH:
        raise ValueError("Current implementation differs from the pre-disclosure lock")
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", args.baseline_ref], text=True).strip()
    if commit != BASELINE_COMMIT:
        raise ValueError("Baseline must resolve to exact original commit 74ee976")
    output.mkdir(parents=True, exist_ok=False)
    for label, revision in (("old", commit), ("current", None)):
        snapshot_sources(ROOT, output / f"{label}-source", revision)
    if sha256((output / "current-source/src/kre/ingestion.py").read_bytes()) != CURRENT_INGESTION_HASH:
        raise ValueError("Current snapshot changed while copying the locked implementation")
    protocol = {"created_before_retrieval_at_utc": utc_now(), "fixture_sha256": FIXTURE_HASH,
                "fixture_frozen_at_utc": fixture["frozen_at_utc"], "baseline_commit": commit,
                "locked_current_ingestion_sha256": CURRENT_INGESTION_HASH,
                "evaluator_sha256": sha256(Path(__file__).read_bytes()),
                "source_snapshots": {label: package_manifest(output / f"{label}-source") for label in ("old", "current")},
                "queries_unchanged": True, "gold_not_used_for_retrieval": True, "model_or_network_calls": 0,
                "scoring": "exact immutable citation verification and union of eligible exact cited gold lines; no semantic judgments",
                "known_fixture_limit": "Compact case uses max_tokens=300; conservative byte accounting includes citation metadata. Preserve errors without budget repair."}
    write_json(output / "EXECUTION_PROTOCOL.json", protocol)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
    for label in ("old", "current"):
        subprocess.run([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--worker",
                        "--source-root", str(output / f"{label}-source"), "--fixture-directory", str(fixture_dir),
                        "--output", str(output / f"{label}-results.json")], check=True, env=env)
    results = {label: json.loads((output / f"{label}-results.json").read_text()) for label in ("old", "current")}
    for label, result in results.items():
        expected = protocol["source_snapshots"][label]
        if result["source_package_sha256"] != expected or package_manifest(output / f"{label}-source") != expected:
            raise ValueError(f"Source snapshot changed during execution: {label}")
    comparison = {"generated_at_utc": utc_now(), "fixture_sha256": FIXTURE_HASH, "baseline_commit": commit,
                  "current_ingestion_sha256": CURRENT_INGESTION_HASH, "semantic_answer_judgment": False,
                  "summary": {label: summarize(result) for label, result in results.items()},
                  "cases": [{"id": old["metrics"]["id"], "old": old["metrics"], "current": new["metrics"]}
                            for old, new in zip(results["old"]["cases"], results["current"]["cases"], strict=True)]}
    write_json(output / "comparison.json", comparison)
    artifacts = [p for p in sorted(output.rglob("*")) if p.is_file()]
    write_json(output / "FIRST_RUN_SHA256_MANIFEST.json", {
        "sealed_at_utc": utc_now(), "kind": "first_frozen_transfer_run", "no_tuning": True,
        "files": [{"path": str(p.relative_to(output)), "sha256": sha256(p.read_bytes()), "bytes": p.stat().st_size} for p in artifacts]})
    print(json.dumps({"output": str(output), "summary": comparison["summary"]}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-directory", type=Path, default=ROOT / "evaluation/post96-transfer")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline-ref", default=BASELINE_COMMIT)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--source-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        run_worker(args.source_root.resolve(), args.fixture_directory.resolve(), args.output.resolve())
    else:
        compare(args)


if __name__ == "__main__":
    main()
