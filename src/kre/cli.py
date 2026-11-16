"""Small local-owner CLI. It is not a multi-user authorization service."""
import argparse
import json
import sqlite3
import sys
from importlib.resources import files
from pathlib import Path

from . import Store, StartupError, IngestError, __version__


def make_request(query, *, budget=1800, max_bytes=16000, max_items=5, historical=False, fresh_only=False):
    return {"contract_version": "0.1", "request_id": "cli-request", "query": query,
            "access_scope_ref": "local", "destination": "local_only",
            "purpose": "historical_evidence" if historical else "current_answer",
            "freshness_requirement": "fresh_only" if fresh_only else "allow_unknown",
            "budget": {"max_tokens": budget, "max_items": max_items, "max_bytes": max_bytes}}


def parser():
    command = argparse.ArgumentParser(prog="kre", description="Local text retrieval with revision citations and bounded context")
    command.add_argument("--version", action="version", version=__version__)
    command.add_argument("--db", default=".kre/knowledge.sqlite3", help="local database (default: .kre/knowledge.sqlite3)")
    commands = command.add_subparsers(dest="command", required=True)
    measurement = commands.add_parser("measure", help="Offline usage accounting and quality scoring; no model or database access")
    measurement.add_argument("arguments", nargs=argparse.REMAINDER)
    for name in ("init", "ingest", "search", "context", "status", "lifecycle", "inspect", "demo",
                 "update-policy", "task-checkpoint", "task-resume", "demo-k2"):
        sub = commands.add_parser(name)
        sub.add_argument("--collection", action="append", help="local-owner collection scope; repeat to include several")
        sub.add_argument("--json", action="store_true", help="machine-readable output")
        if name == "ingest":
            sub.add_argument("paths", nargs="+", help="explicit .txt/.md/.markdown files (no recursive crawl)")
            sub.add_argument("--root", action="append", required=True, help="permitted directory; symlink descendants are rejected")
            sub.add_argument("--source-id", help="optional stable ID; allowed only with one file")
        if name in ("search", "context"):
            sub.add_argument("query", nargs="?")
            sub.add_argument("--budget", type=int, default=1800, help="conservative token allowance, counted as UTF-8 bytes")
            sub.add_argument("--max-bytes", type=int, default=16000)
            sub.add_argument("--max-items", type=int, default=5)
            sub.add_argument("--historical", action="store_true")
            sub.add_argument("--fresh-only", action="store_true")
            if name == "context":
                sub.add_argument("--request", type=Path, help="contract 0.1 JSON request, at most 64 KiB; scope reference must be local")
                sub.add_argument("--required", type=Path, help="JSON array of exact references; uses the separate K2 wrapper")
        if name == "lifecycle":
            sub.add_argument("source_id")
            sub.add_argument("--action", required=True, choices=("revoke", "delete", "supersede"))
        if name == "inspect":
            sub.add_argument("revision_id")
        if name == "update-policy":
            sub.add_argument("source_id")
            sub.add_argument("--freshness", choices=("fresh", "stale", "unknown"))
            sub.add_argument("--authority", choices=("authoritative", "unverified"))
            sub.add_argument("--origin", choices=("source_evidence", "user_assertion", "model_inference"))
            sub.add_argument("--egress", choices=("local_only", "approved_remote"))
            sub.add_argument("--move-to", help="destination collection, also granted with --collection")
        if name in ("task-checkpoint", "task-resume"):
            sub.add_argument("task_id")
            if name == "task-checkpoint":
                sub.add_argument("--card", required=True, type=Path, help="bounded task card JSON; no generated summary")
    return command


def read_json(path, limit=65536):
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f"JSON file exceeds {limit} bytes")
    return json.loads(raw)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "measure":
        from .efficiency import main as measure_main
        return measure_main(arguments[1:])
    options = parser()
    args = options.parse_args(arguments)
    if args.command == "measure":
        from .efficiency import main as measure_main
        return measure_main(args.arguments)
    collections = set(args.collection or ["default"])
    if args.command == "ingest" and (len(collections) != 1 or len(args.paths) > 100 or (args.source_id and len(args.paths) != 1)):
        options.error("ingest accepts one collection, at most 100 files, and source-id only with one file")
    request = None
    if args.command in ("search", "context"):
        request_path = getattr(args, "request", None)
        if bool(args.query) == bool(request_path):
            options.error("provide a query or --request, exactly one")
        if request_path:
            try:
                request = read_json(request_path)
            except (OSError, ValueError) as exc:
                print(json.dumps({"error": str(exc)}), file=sys.stderr)
                return 2
        else:
            request = make_request(args.query, budget=args.budget, max_bytes=args.max_bytes,
                                   max_items=args.max_items, historical=args.historical, fresh_only=args.fresh_only)
    database = Path(args.db).expanduser()
    try:
        database.parent.mkdir(parents=True, exist_ok=True)
        roots = getattr(args, "root", ())
        if args.command == "demo":
            roots = [Path(str(files("kre").joinpath("sample_data")))]
        with Store(str(database), principal="local-owner", scopes={"local": collections}, permitted_roots=roots) as store:
            if args.command == "init":
                result = {"database": str(database.resolve()), "schema_version": 2, "fts5": True}
            elif args.command == "ingest":
                result = {"files": []}
                failures = 0
                for path in args.paths:
                    try:
                        item = store.ingest_file(path, collection=next(iter(collections)), source_id=args.source_id)
                        result["files"].append({"status": "indexed", **item})
                    except (OSError, ValueError, PermissionError) as exc:
                        result["files"].append({"path": path, "status": "error", "message": str(exc)})
                        failures += 1
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 2 if failures else 0
            elif args.command in ("search", "context"):
                required = getattr(args, "required", None)
                result = store.context_required(request, required_refs=read_json(required)) if required else store.context(request)
                if args.command == "search" and not args.json:
                    if result["error"]:
                        print(result["error"]["code"] + ": " + result["error"]["message"], file=sys.stderr)
                        return 2
                    for item in result["items"]:
                        print(f"[{item['citation_id']}] {item['source_id']} {item['locator']['label']} ({item['authority']}, {item['freshness']})\n{item['text']}\n")
                    print(f"{len(result['items'])} excerpt(s); {result['token_usage']['context_bytes']} UTF-8 bytes including citations.")
                    return 0
            elif args.command == "status":
                result = store.status()
            elif args.command == "lifecycle":
                store.lifecycle(args.source_id, args.action)
                result = {"source_id": args.source_id, "action": args.action, "applied": True}
            elif args.command == "inspect":
                result = store.revision(args.revision_id, scope_ref="local")
            elif args.command == "update-policy":
                result = store.update_policy(args.source_id, freshness=args.freshness, authority=args.authority,
                                             origin=args.origin, egress=args.egress, collection=args.move_to)
            elif args.command == "task-checkpoint":
                result = store.checkpoint_task(args.task_id, scope_ref="local", card=read_json(args.card, 32768))
            elif args.command == "task-resume":
                result = store.resume_task(args.task_id, scope_ref="local")
            elif args.command == "demo-k2":
                from .demo import run_demo
                result = run_demo(store, collection=sorted(collections)[0])
                if not args.json:
                    print("K2 demonstration: fictional documents, no model or network call.")
                    for item in result["initial_context"]["items"]:
                        print(f"Before update, {item['locator']['label']}: {item['text']}")
                    print("Updated the guide; the earlier revision is preserved as superseded.")
                    print(f"Earlier context validation: {result['initial_context_validation_after_update']}. Current evidence:")
                    for item in result["after_revocation"]["items"]:
                        print(f"[{item['citation_id']}] {item['locator']['label']}: {item['text']}")
                    print("Revoked the legacy source; current retrieval excludes it.")
                    print("Required current evidence fits; required revoked evidence returns REQUIRED_EVIDENCE_MISSING.")
                    print(f"Resumed the task with {len(result['resume']['evidence'])} valid excerpt(s); {len(result['resume']['invalidated'])} dependent entry was excluded.")
                    comparison = result["context_size_comparison"]
                    print(f"Context: {comparison['retrieved_bytes']} bytes; all current demo chunks: {comparison['all_current_demo_chunks_bytes']} bytes, with identical citations.")
                    print("This size illustration does not establish task quality or token savings. Use --json for the complete record.")
                    return 0
            else:
                sample = Path(str(files("kre").joinpath("sample_data", "release.md")))
                ingested = store.ingest_file(sample, source_id="demo-release", collection=sorted(collections)[0])
                result = store.context(make_request("rollback", budget=3000))
                if not args.json:
                    print("Indexed the bundled synthetic release note. No model or network call was used.")
                    print(f"Source: {ingested['source_id']}; revision: {ingested['revision_id']}")
                    for item in result["items"]:
                        print(f"\n{item['locator']['label']} — {item['text']}")
                    print(f"\nContext: {result['token_usage']['context_bytes']} bytes including citations; token count is approximate.")
                    print("Try: kre search rollback  (use the same --db if customized)")
                    return 0
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result.get("status") == "error" else 0
    except (OSError, ValueError, PermissionError, sqlite3.Error, StartupError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
