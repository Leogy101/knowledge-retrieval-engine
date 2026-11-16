"""Small reproducible local-file measurement, not a general RAG benchmark."""
import argparse
import hashlib
import json
import math
import os
import platform
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path
from kre import Store, __version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rng = random.Random(20261114)
    topics = ["rollback", "deployment", "cache", "recovery", "release"]
    documents = [(f"source-{i:04d}", "\n\n".join(
        f"recordkey{i:04d}step{j} {rng.choice(topics)} synthetic procedure value {rng.randrange(1000)}."
        for j in range(5)) + "\n") for i in range(200)]
    corpus_hash = hashlib.sha256(json.dumps(documents, separators=(",", ":")).encode()).hexdigest()
    scratch = Path(__file__).resolve().parents[1] / ".scratch"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temporary:
        root = Path(temporary).resolve()
        for source_id, text in documents:
            (root / (source_id + ".md")).write_text(text, encoding="utf-8")
        database = root / "knowledge.sqlite3"
        with Store(str(database), principal="measurement", scopes={"measure": {"synthetic"}}, permitted_roots=[root]) as store:
            start = time.perf_counter()
            for source_id, _ in documents:
                store.ingest_file(root / (source_id + ".md"), source_id=source_id, collection="synthetic")
            ingest_ms = (time.perf_counter() - start) * 1000
            queries = [(f"recordkey{i:04d}step2", f"source-{i:04d}") for i in range(0, 200, 5)]
            timings, sizes, hits, covering_hits = [], [], 0, 0
            for index, (query, expected) in enumerate(queries[:10] + queries):
                request = {"contract_version": "0.1", "request_id": f"measurement-{index}", "query": query,
                           "access_scope_ref": "measure", "destination": "local_only", "purpose": "current_answer",
                           "budget": {"max_tokens": 32768, "max_items": 5, "max_bytes": 262144}}
                start = time.perf_counter()
                result = store.context(request)
                elapsed = (time.perf_counter() - start) * 1000
                if result["error"]:
                    raise RuntimeError(result["error"])
                if index >= 10:
                    timings.append(elapsed)
                    sizes.append(result["token_usage"]["context_bytes"])
                    hits += any(item["source_id"] == expected and item["locator"]["line_start"] == 5
                                and item["locator"]["line_end"] == 5 and query in item["text"] for item in result["items"])
                    covering_hits += any(
                        item["source_id"] == expected
                        and item["locator"]["line_start"] <= 5 <= item["locator"]["line_end"]
                        and query in item["text"].splitlines()[5 - item["locator"]["line_start"]]
                        for item in result["items"])
            ordered = sorted(timings)
            report = {
                "package_version": __version__, "seed": 20261114, "corpus_sha256": corpus_hash,
                "runtime": {"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                            "platform": platform.platform(), "machine": platform.machine(), "logical_cpus": os.cpu_count()},
                "documents": len(documents), "chunks": store.db.execute("SELECT count(*) FROM chunks").fetchone()[0],
                "raw_source_bytes": sum(len(text.encode()) for _, text in documents),
                "fresh_database_file_ingestion_ms": ingest_ms, "warmup_queries": 10, "measured_queries": len(timings),
                "context_warm_p50_ms": statistics.median(timings),
                "context_warm_p95_ms": ordered[math.ceil(len(ordered) * .95) - 1],
                "expected_identifier_and_line_hits": hits,
                "expected_identifier_and_covering_line_hits": covering_hits,
                "median_context_bytes": statistics.median(sizes),
                "database_bytes": database.stat().st_size, "journal_mode": store.db.execute("PRAGMA journal_mode").fetchone()[0],
                "limitations": [
                    "Fresh database ingestion includes safe file reads; fixture files were just written, so OS caches are not cold.",
                    "40 deliberately easy unique identifier queries; no paraphrase, multi-hop, or generated-answer evaluation.",
                    "Ten warmups then one measured request per query; p95 uses nearest rank; ordinary host activity.",
                    "No baseline generation, provider tokenization, token/cost savings, network, or harness measurement.",
                    "The original exact-single-line hit metric is retained; covering-line hits also accept a larger exact excerpt containing the target source line.",
                    "200 small files do not establish larger corpus targets; actual stored chunks are reported, not assumed.",
                ],
            }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
