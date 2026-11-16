"""Local SQLite retrieval. Caller grants are trusted application configuration."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from types import MappingProxyType
from pathlib import Path

from .ingestion import IngestError, PARSER_VERSION, chunks, normalize, read_permitted_file


# Query grammar is not useful evidence in a small corpus: otherwise a rare
# "if" or "by" can outrank the subject of a multi-part question. Keep domain
# words and negation; this is deliberately not stemming or semantic rewriting.
_QUESTION_WORDS = frozenset("""
a an and are as at be been being by can could did do does for from had has have
how i if in into is it its of on or our should than that the their them then
there these they this those to was were what when where which who why will
with would you your
""".split())
_QUESTION_LEADS = frozenset("""
Which What When Where Who Why How If Does Do Did Is Are Can Could Should Would
""".split())


def _query_terms(query: str) -> list[str]:
    terms = list(dict.fromkeys(re.findall(r"\w+", query, flags=re.UNICODE)))
    # Preserve literal searches composed entirely of these words. The original
    # term bound is checked by the caller, before any filtering.
    # Preserve capitalized names/acronyms (e.g. Will, IT), except ordinary
    # sentence-leading question words. Do not rewrite the stored source text.
    return [term for term in terms if term.casefold() not in _QUESTION_WORDS
            or (not term.islower() and term not in _QUESTION_LEADS)] or terms


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _identifier(value: object) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def evidence_ref(item: dict) -> dict:
    """An exact immutable reference for required evidence or task dependencies."""
    return {key: item[key] for key in ("source_id", "revision_id", "chunk_id", "content_sha256")}


def _valid_refs(refs) -> bool:
    if not isinstance(refs, list) or len(refs) > 32:
        return False
    keys = {"source_id", "revision_id", "chunk_id", "content_sha256"}
    if any(not isinstance(ref, dict) or ref.keys() != keys or
           not all(_identifier(ref[k]) for k in keys) or
           re.fullmatch(r"[0-9a-f]{64}", ref["content_sha256"]) is None for ref in refs):
        return False
    return len({json.dumps(ref, sort_keys=True) for ref in refs}) == len(refs)


class StartupError(RuntimeError):
    """Unsupported SQLite runtime, schema or database."""


class Store:
    """One local trust domain; scope grants come only from the trusted host."""

    def __init__(self, path: str, *, principal: str, scopes: dict[str, set[str]],
                 destinations: frozenset[str] = frozenset({"local_only"}), permitted_roots=()):
        if not _identifier(principal) or not scopes or any(not _identifier(k) for k in scopes):
            raise ValueError("Invalid trusted binding")
        if any(not values or any(not _identifier(v) for v in values) for values in scopes.values()):
            raise ValueError("Invalid collection grant")
        if not destinations or not destinations <= {"local_only", "approved_remote"}:
            raise ValueError("Invalid destination grant")
        self.principal = principal
        self.scopes = MappingProxyType({k: frozenset(v) for k, v in scopes.items()})
        self.destinations = frozenset(destinations)
        self.permitted_roots = tuple((Path(os.path.abspath(Path(p).expanduser())), Path(p).expanduser().resolve(strict=True)) for p in permitted_roots)
        if any(not canonical.is_dir() for _, canonical in self.permitted_roots):
            raise IngestError("Permitted roots must be directories")
        if str(path) != ":memory:":
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass  # Existing permissions belong to the operator.
            else:
                os.close(descriptor)
        self.db = sqlite3.connect(path, timeout=1)
        self.db.row_factory = sqlite3.Row
        try:
            self._startup()
        except (sqlite3.Error, StartupError) as exc:
            self.db.close()
            raise StartupError("KRE requires SQLite FTS5 and a compatible KRE schema (1 or 2)") from exc

    def _startup(self):
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("CREATE VIRTUAL TABLE temp.kre_fts_check USING fts5(text)")
        self.db.execute("DROP TABLE temp.kre_fts_check")
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        identity = self.db.execute("PRAGMA application_id").fetchone()[0]
        if tables or version or identity:
            if version not in (1, 2) or identity != 1263682865:
                raise StartupError("Unknown database or unsupported schema")
            expected = {"metadata": {"key", "value"},
                        "sources": {"source_id", "collection", "authority", "origin", "freshness", "egress", "state", "display_uri"},
                        "revisions": {"revision_id", "source_id", "text", "content_hash", "recorded_at", "lifecycle", "original_hash", "parser_version"},
                        "chunks": {"id", "revision_id", "text", "line_start", "line_end"},
                        "tasks": {"task_id", "principal", "scope_ref", "refs_json"}, "chunk_fts": {"text"}}
            if version == 2:
                expected["task_cards"] = {"task_id", "principal", "scope_ref", "card_json", "recorded_at"}
            for table, columns in expected.items():
                actual = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
                if not columns <= actual:
                    raise StartupError("Incomplete schema")
            if {r[0] for r in self.db.execute("SELECT key FROM metadata")} != {"generation", "namespace"}:
                raise StartupError("Invalid store metadata")
            if version == 1:
                # Schema-only migration. Existing revisions, locators and legacy tasks remain intact.
                with self.db:
                    self.db.execute("BEGIN IMMEDIATE")
                    self.db.execute("CREATE TABLE task_cards(task_id TEXT PRIMARY KEY, principal TEXT NOT NULL, scope_ref TEXT NOT NULL, card_json TEXT NOT NULL, recorded_at TEXT NOT NULL)")
                    self.db.execute("PRAGMA user_version=2")
                    self._changed()
            return
        self.db.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sources(
                source_id TEXT PRIMARY KEY, collection TEXT NOT NULL,
                authority TEXT NOT NULL, origin TEXT NOT NULL, freshness TEXT NOT NULL,
                egress TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'active', display_uri TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(
                revision_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources,
                text TEXT NOT NULL, content_hash TEXT NOT NULL, recorded_at TEXT NOT NULL,
                lifecycle TEXT NOT NULL, original_hash TEXT NOT NULL, parser_version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions,
                text TEXT NOT NULL, line_start INTEGER NOT NULL, line_end INTEGER NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(text);
            CREATE TABLE IF NOT EXISTS tasks(
                task_id TEXT PRIMARY KEY, principal TEXT NOT NULL, scope_ref TEXT NOT NULL,
                refs_json TEXT NOT NULL);
            CREATE TABLE task_cards(task_id TEXT PRIMARY KEY, principal TEXT NOT NULL,
                scope_ref TEXT NOT NULL, card_json TEXT NOT NULL, recorded_at TEXT NOT NULL);
            INSERT INTO metadata VALUES ('generation', '0');
            INSERT INTO metadata VALUES ('namespace', lower(hex(randomblob(16))));
            PRAGMA application_id=1263682865;
            PRAGMA user_version=2;
            COMMIT;
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def status(self):
        allowed = sorted(set().union(*self.scopes.values()))
        marks = ",".join("?" for _ in allowed)
        sources = [dict(r) for r in self.db.execute(
            f"SELECT source_id,collection,state,authority,origin,freshness,egress,display_uri FROM sources WHERE collection IN ({marks}) ORDER BY source_id", allowed)]
        return {"schema_version": 2, "sqlite_version": sqlite3.sqlite_version, "fts5": True,
                "context_revision": self._generation(), "sources": sources}

    def revision(self, revision_id, *, scope_ref):
        if scope_ref not in self.scopes:
            raise PermissionError("Evidence unavailable in caller scope")
        row = self.db.execute("""SELECT r.*,s.collection,s.display_uri,s.state FROM revisions r
            JOIN sources s ON s.source_id=r.source_id WHERE revision_id=?""", (revision_id,)).fetchone()
        if not row or row["collection"] not in self.scopes[scope_ref] or row["state"] != "active":
            raise PermissionError("Evidence unavailable in caller scope")
        return dict(row)

    def _generation(self) -> str:
        meta = dict(self.db.execute("SELECT key, value FROM metadata"))
        return f"{meta['namespace']}:{meta['generation']}"

    def _changed(self) -> None:
        self.db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='generation'")

    def _fingerprint(self, scope: str) -> str:
        return _hash(json.dumps([self.principal, scope, sorted(self.scopes[scope])]))

    def ingest_text(self, source_id: str, text: str, *, collection: str,
               authority: str | None = None, origin: str | None = None,
               freshness: str | None = None, egress: str | None = None, _display_uri: str = "",
               _original_hash: str | None = None) -> str:
        """Trusted application ingestion. Document prose cannot grant authority."""
        if not _identifier(source_id) or not _identifier(collection) or not isinstance(text, str):
            raise ValueError("Invalid text source")
        if collection not in set().union(*self.scopes.values()):
            raise PermissionError("Collection is outside trusted caller grants")
        if authority not in (None, "authoritative", "unverified") or origin not in (
            None, "source_evidence", "user_assertion", "model_inference"
        ) or freshness not in (None, "fresh", "stale", "unknown") or egress not in (
            None, "local_only", "approved_remote"
        ):
            raise ValueError("Invalid trusted source labels")
        normalized = normalize(text)
        segments = chunks(normalized)
        original_hash = _original_hash or _hash(text)
        digest = _hash(normalized)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            existing = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
            supplied = {"authority": authority, "origin": origin, "freshness": freshness, "egress": egress}
            defaults = {"authority": "unverified", "origin": "source_evidence", "freshness": "unknown", "egress": "local_only"}
            labels = (collection, *(supplied[key] if supplied[key] is not None else
                                    (existing[key] if existing else defaults[key]) for key in defaults))
            if existing:
                if existing["state"] != "active":
                    raise ValueError("Revoked or deleted source cannot be reactivated by ingest")
                if tuple(existing[k] for k in ("collection", "authority", "origin", "freshness", "egress")) != labels:
                    raise ValueError("Ingest cannot implicitly change source policy")
                if existing["display_uri"] != _display_uri:
                    raise ValueError("Source identity is already bound to another origin")
                current = self.db.execute(
                    "SELECT * FROM revisions WHERE source_id=? AND lifecycle='active'", (source_id,)
                ).fetchone()
                if current and current["content_hash"] == digest and current["original_hash"] == original_hash and current["parser_version"] == PARSER_VERSION:
                    return current["revision_id"]
            else:
                self.db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, 'active', ?)", (source_id, *labels, _display_uri))
            revision = "r-" + uuid.uuid4().hex
            self.db.execute("UPDATE revisions SET lifecycle='superseded' WHERE source_id=? AND lifecycle='active'", (source_id,))
            self.db.execute("INSERT INTO revisions VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                            (revision, source_id, normalized, digest, _now(), original_hash, PARSER_VERSION))
            for start, end, text_chunk in segments:
                row = self.db.execute("INSERT INTO chunks(revision_id,text,line_start,line_end) VALUES (?,?,?,?)",
                                      (revision, text_chunk, start, end))
                self.db.execute("INSERT INTO chunk_fts(rowid,text) VALUES (?,?)", (row.lastrowid, text_chunk))
            self._changed()
        return revision

    def ingest_file(self, path, *, collection="default", source_id=None, **labels):
        selected, text, original_hash = read_permitted_file(path, self.permitted_roots)
        source_id = source_id or "file-" + _hash(str(selected))[:32]
        revision = self.ingest_text(source_id, text, collection=collection, _display_uri=str(selected),
                                    _original_hash=original_hash, **labels)
        return {"source_id": source_id, "revision_id": revision, "path": str(selected)}

    def revoke(self, source_id: str) -> None:
        self.lifecycle(source_id, "revoke")

    def update_policy(self, source_id: str, *, freshness=None, authority=None,
                      origin=None, egress=None, collection=None) -> dict:
        """Explicit trusted host action; timestamps and document prose never promote trust."""
        choices = {"freshness": {"fresh", "stale", "unknown"},
                   "authority": {"authoritative", "unverified"},
                   "origin": {"source_evidence", "user_assertion", "model_inference"},
                   "egress": {"local_only", "approved_remote"}}
        supplied = {"freshness": freshness, "authority": authority, "origin": origin,
                    "egress": egress, "collection": collection}
        updates = {key: value for key, value in supplied.items() if value is not None}
        if not _identifier(source_id) or not updates:
            raise ValueError("Provide a source and at least one explicit policy update")
        if any(not isinstance(value, str) or value not in choices[key]
               for key, value in updates.items() if key != "collection"):
            raise ValueError("Invalid trusted source labels")
        grants = set().union(*self.scopes.values())
        if collection is not None and (not _identifier(collection) or collection not in grants):
            raise PermissionError("Destination collection is outside trusted caller grants")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
            if not row or row["collection"] not in grants:
                raise PermissionError("Source unavailable in caller scope")
            if row["state"] != "active":
                raise ValueError("Policy updates cannot reactivate revoked or deleted sources")
            changed = any(row[key] != value for key, value in updates.items())
            if changed:
                self.db.execute("UPDATE sources SET " + ",".join(key + "=?" for key in updates) + " WHERE source_id=?",
                                [*updates.values(), source_id])
                self._changed()
            return {"source_id": source_id, "changed": changed, "context_revision": self._generation(),
                    "policy": {key: updates.get(key, row[key]) for key in supplied}}

    def lifecycle(self, source_id: str, action: str) -> None:
        if action not in {"revoke", "delete", "supersede"}:
            raise ValueError("Unknown lifecycle action")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            source = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
            if not source or source["collection"] not in set().union(*self.scopes.values()):
                raise PermissionError("Source unavailable in caller scope")
            if source["state"] == "deleted" or (source["state"] == "revoked" and action != "delete"):
                return
            if action == "supersede":
                changed = self.db.execute("UPDATE revisions SET lifecycle='superseded' WHERE source_id=? AND lifecycle='active'", (source_id,)).rowcount
                if changed:
                    self._changed()
                return
            state = "revoked" if action == "revoke" else "deleted"
            self.db.execute("UPDATE sources SET state=? WHERE source_id=?", (state, source_id))
            self.db.execute("UPDATE revisions SET lifecycle=? WHERE source_id=?", (state, source_id))
            self.db.execute("DELETE FROM chunk_fts WHERE rowid IN (SELECT c.id FROM chunks c JOIN revisions r ON c.revision_id=r.revision_id WHERE r.source_id=?)", (source_id,))
            self._changed()

    def _request_error(self, request: object) -> str | None:
        required = {"contract_version", "request_id", "query", "access_scope_ref", "destination", "budget", "purpose"}
        optional = {"freshness_requirement", "source_ids"}
        if not isinstance(request, dict) or not required <= request.keys() or request.keys() - required - optional:
            return "INVALID_REQUEST"
        if request["contract_version"] != "0.1":
            return "UNSUPPORTED_VERSION"
        if not _identifier(request["request_id"]) or not _identifier(request["access_scope_ref"]):
            return "INVALID_REQUEST"
        if not isinstance(request["query"], str) or not 1 <= len(request["query"]) <= 8192:
            return "INVALID_REQUEST"
        if request["purpose"] not in ("current_answer", "historical_evidence"):
            return "INVALID_REQUEST"
        if request.get("freshness_requirement", "allow_unknown") not in ("allow_unknown", "fresh_only"):
            return "INVALID_REQUEST"
        if request["destination"] not in ("local_only", "approved_remote"):
            return "INVALID_REQUEST"
        budget = request["budget"]
        limits = {"max_tokens": 32768, "max_items": 32, "max_bytes": 262144}
        if not isinstance(budget, dict) or budget.keys() != limits.keys():
            return "INVALID_REQUEST"
        if any(type(budget[k]) is not int or not 1 <= budget[k] <= cap for k, cap in limits.items()):
            return "INVALID_REQUEST"
        if "source_ids" in request and (not isinstance(request["source_ids"], list) or not 1 <= len(request["source_ids"]) <= 64 or not all(_identifier(x) for x in request["source_ids"])):
            return "INVALID_REQUEST"
        return None

    def _response(self, request: object, *, code: str | None = None) -> dict:
        request = request if isinstance(request, dict) else {}
        request_id = request.get("request_id")
        scope = request.get("access_scope_ref")
        if code:
            try:
                generation = self._generation()
            except sqlite3.Error:
                generation = "unavailable"
        else:
            generation = self._generation()
        return {
            "contract_version": "0.1", "request_id": request_id if _identifier(request_id) else "invalid-request",
            "status": "error" if code else "ok", "context_revision": generation,
            "generated_at": _now(), "scope_fingerprint": self._fingerprint(scope) if isinstance(scope, str) and scope in self.scopes else "unavailable",
            "items": [], "context_text": "", "token_usage": {
                "estimated_tokens": 0, "counter_kind": "conservative_bytes", "counter_id": "utf8_bytes",
                "counter_revision": "1", "context_bytes": 0, "includes_citations": True},
            "coverage": "unknown", "omissions": {}, "warnings": ["APPROXIMATE_TOKEN_COUNT"],
            "error": {"code": code, "message": "Request unavailable or outside the supported context contract.", "retryable": False} if code else None,
        }

    @staticmethod
    def _item(row: sqlite3.Row, citation: str) -> dict:
        return {
            "citation_id": citation, "source_id": row["source_id"], "revision_id": row["revision_id"],
            "chunk_id": f"c-{row['id']}", "text": row["text"], "content_sha256": _hash(row["text"]),
            "locator": {"label": f"lines {row['line_start']}-{row['line_end']}", "line_start": row["line_start"], "line_end": row["line_end"]},
            "recorded_at": row["recorded_at"], "authority": row["authority"], "origin": row["origin"],
            "lifecycle": row["lifecycle"], "freshness": row["freshness"], "egress": {"restriction": row["egress"]},
        }

    @staticmethod
    def _render(items: list[dict]) -> str:
        return json.dumps(items, ensure_ascii=False, separators=(",", ":")) if items else ""

    @staticmethod
    def _heading_covered(heading, others, query_words):
        """Only suppress a standalone Markdown heading covered by same-revision prose.

        This conservative word check is a packing heuristic, not semantic relevance.
        Required items never pass through this filter.
        """
        pattern = r" {0,3}#{1,6}[ \t]+\S[^\n]*"
        if not re.fullmatch(pattern, heading["text"]):
            return False
        words = set(re.findall(r"\w+", heading["text"].casefold())) & query_words
        return bool(words) and any(
            row["revision_id"] == heading["revision_id"]
            and not re.fullmatch(pattern, row["text"])
            and words <= set(re.findall(r"\w+", row["text"].casefold()))
            for row in others
        )

    def context(self, request: object) -> dict:
        try:
            return self._context(request)
        except sqlite3.OperationalError:
            return self._response(request, code="INDEX_UNAVAILABLE")

    def _ref_row(self, ref):
        row = self.db.execute("""SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,
            s.authority,s.origin,s.freshness,s.egress,s.collection,s.state
            FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id
            JOIN sources s ON s.source_id=r.source_id
            WHERE s.source_id=? AND r.revision_id=? AND ('c-'||c.id)=?""",
            (ref["source_id"], ref["revision_id"], ref["chunk_id"])).fetchone()
        return row if row and _hash(row["text"]) == ref["content_sha256"] else None

    def _eligible_ref(self, ref, request):
        row = self._ref_row(ref)
        if not row or row["collection"] not in self.scopes[request["access_scope_ref"]] or row["state"] != "active":
            return None
        if row["lifecycle"] not in {"active", "superseded"}:
            return None
        if request["purpose"] == "current_answer" and (row["lifecycle"] != "active" or row["freshness"] == "stale"):
            return None
        if request.get("freshness_requirement") == "fresh_only" and row["freshness"] != "fresh":
            return None
        if request.get("source_ids") and row["source_id"] not in request["source_ids"]:
            return None
        if request["destination"] == "approved_remote" and row["egress"] != "approved_remote":
            return None
        return row

    def context_required(self, request: object, *, required_refs: list) -> dict:
        """Local wrapper, not an extension to the shared 0.1 wire request."""
        valid = _valid_refs(required_refs)
        missing = []
        if not valid:
            response = self._response(request, code="INVALID_REQUIRED_REFS")
        else:
            try:
                response = self._context(request, required_refs=required_refs, missing=missing)
            except sqlite3.OperationalError:
                response = self._response(request, code="INDEX_UNAVAILABLE")
        requested = json.loads(json.dumps(required_refs)) if valid else []
        delivered = [ref for ref in requested if ref in [evidence_ref(item) for item in response["items"]]]
        if response["error"] and not missing:
            reason = "budget" if response["error"]["code"] == "BUDGET_TOO_SMALL" else "request_error"
            missing = [{"ref": ref, "reason": reason} for ref in requested]
        return {"wrapper_version": "kre-required/1", "status": response["status"], "context": response,
                "required": {"requested": requested, "delivered": delivered, "missing": missing},
                "error": response["error"]}

    def _context(self, request: object, *, required_refs=(), missing=None) -> dict:
        code = self._request_error(request)
        if code:
            return self._response(request, code=code)
        scope = request["access_scope_ref"]
        if scope not in self.scopes:
            return self._response(request, code="ACCESS_DENIED")
        if request["destination"] not in self.destinations:
            return self._response(request, code="DESTINATION_DENIED")
        terms = list(dict.fromkeys(re.findall(r"\w+", request["query"], flags=re.UNICODE)))
        if len(terms) > 64:
            return self._response(request, code="INVALID_REQUEST")
        terms = _query_terms(request["query"])
        with self.db:
            self.db.execute("BEGIN")  # explicit read snapshot including generation
            response = self._response(request)
            required_rows = []
            for ref in required_refs:
                row = self._eligible_ref(ref, request)
                if row is None:
                    missing.append({"ref": ref, "reason": "unavailable"})
                else:
                    required_rows.append(row)
            if missing:
                return self._response(request, code="REQUIRED_EVIDENCE_MISSING")
            if not terms and not required_rows:
                response["warnings"].append("NO_EVIDENCE")
                return response
            match = " OR ".join('"' + term + '"' for term in terms)
            collections = sorted(self.scopes[scope])
            clauses = ["chunk_fts MATCH ?", "s.state='active'", "r.lifecycle IN ('active','superseded')",
                       "s.collection IN (" + ",".join("?" for _ in collections) + ")"]
            params = [match, *collections]
            if request["purpose"] == "current_answer":
                clauses += ["r.lifecycle='active'", "s.freshness!='stale'"]
            if request.get("freshness_requirement") == "fresh_only":
                clauses.append("s.freshness='fresh'")
            if request.get("source_ids"):
                clauses.append("s.source_id IN (" + ",".join("?" for _ in request["source_ids"]) + ")")
                params.extend(request["source_ids"])
            sql = """SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,s.authority,s.origin,s.freshness,s.egress,
                bm25(chunk_fts) AS relevance FROM chunk_fts JOIN chunks c ON c.id=chunk_fts.rowid
                JOIN revisions r ON r.revision_id=c.revision_id JOIN sources s ON s.source_id=r.source_id
                WHERE """ + " AND ".join(clauses) + " ORDER BY relevance,c.id LIMIT ?"
            params.append(request["budget"]["max_items"] * 4)
            rows = self.db.execute(sql, params).fetchall() if terms else []
            if request["destination"] == "approved_remote" and any(row["egress"] == "local_only" for row in rows):
                return self._response(request, code="DESTINATION_DENIED")
            allowance = min(request["budget"]["max_tokens"], request["budget"]["max_bytes"])
            mandatory = [self._item(row, f"E{i + 1}") for i, row in enumerate(required_rows)]
            if len(mandatory) > request["budget"]["max_items"] or len(self._render(mandatory).encode("utf-8")) > allowance:
                return self._response(request, code="BUDGET_TOO_SMALL")
            response["items"] = mandatory
            required_ids = {row["id"] for row in required_rows}
            # Keep immutable chunks and citation accounting unchanged. Defer a
            # heading only when an eligible same-revision body candidate covers
            # its query words; drop it only if that body actually fits the pack.
            query_words = {term.casefold() for term in terms}
            deferred = [row for row in rows if self._heading_covered(row, [*required_rows, *rows], query_words)]
            deferred_ids = {row["id"] for row in deferred}
            ordered_rows = [row for row in rows if row["id"] not in deferred_ids] + deferred
            omitted = item_omitted = 0
            for row in ordered_rows:
                if row["id"] in required_ids:
                    continue
                if self._heading_covered(row, response["items"], query_words):
                    continue
                if len(response["items"]) >= request["budget"]["max_items"]:
                    item_omitted += 1
                    continue
                item = self._item(row, f"E{len(response['items']) + 1}")
                candidate = self._render([*response["items"], item])
                if len(candidate.encode("utf-8")) > allowance:
                    omitted += 1
                    continue
                response["items"].append(item)
            if not response["items"] and rows:
                return self._response(request, code="BUDGET_TOO_SMALL")
            response["context_text"] = self._render(response["items"])
            size = len(response["context_text"].encode("utf-8"))
            response["token_usage"].update(estimated_tokens=size, context_bytes=size)
            omissions = {}
            if omitted:
                omissions["budget"] = omitted
            if item_omitted:
                omissions["item_limit"] = item_omitted
            if omissions:
                response.update(status="partial", coverage="partial", omissions=omissions)
            if not rows and not mandatory:
                response["warnings"].append("NO_EVIDENCE")
            if len(json.dumps(response, ensure_ascii=False).encode("utf-8")) > 1_048_576:
                return self._response(request, code="BUDGET_TOO_SMALL")
            return response

    def checkpoint_task(self, task_id: str, *, scope_ref: str, card: dict) -> dict:
        from .continuity import checkpoint_task
        return checkpoint_task(self, task_id, scope_ref=scope_ref, card=card)

    def resume_task(self, task_id: str, *, scope_ref: str) -> dict:
        from .continuity import resume_task
        return resume_task(self, task_id, scope_ref=scope_ref)

    def validate_context(self, response: dict, *, scope_ref: str, destination: str) -> str:
        """Local pre-use snapshot check, NOT atomic with external dispatch."""
        try:
            return self._validate_context(response, scope_ref=scope_ref, destination=destination)
        except (sqlite3.Error, TypeError, ValueError):
            return "denied"

    def _validate_context(self, response, *, scope_ref, destination):
        if not isinstance(response, dict) or not isinstance(scope_ref, str):
            return "denied"
        if scope_ref not in self.scopes or not isinstance(destination, str) or destination not in self.destinations:
            return "denied"
        if response.get("status") not in ("ok", "partial") or response.get("scope_fingerprint") != self._fingerprint(scope_ref):
            return "denied"
        with self.db:
            self.db.execute("BEGIN")
            if response.get("context_revision") != self._generation():
                return "changed"
            items = response.get("items")
            if not isinstance(items, list) or len(items) > 32 or response.get("context_text") != self._render(items):
                return "denied"
            size = len(response["context_text"].encode("utf-8"))
            usage = response.get("token_usage", {})
            if not isinstance(usage, dict) or any(type(usage.get(k)) is not int for k in ("context_bytes", "estimated_tokens")):
                return "denied"
            if size > 262144 or usage.get("context_bytes") != size or usage.get("estimated_tokens") != size:
                return "denied"
            for item in items:
                if not isinstance(item, dict) or not all(_identifier(item.get(k)) for k in ("source_id", "revision_id", "chunk_id", "citation_id")):
                    return "denied"
                row = self.db.execute("""SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,s.authority,s.origin,s.freshness,s.egress,s.collection,s.state
                    FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id JOIN sources s ON s.source_id=r.source_id
                    WHERE ('c-' || c.id)=? AND r.revision_id=? AND r.source_id=?""",
                    (item.get("chunk_id"), item.get("revision_id"), item.get("source_id"))).fetchone()
                if not row or row["collection"] not in self.scopes[scope_ref] or row["state"] != "active" or row["lifecycle"] not in {"active", "superseded"}:
                    return "denied"
                if destination == "approved_remote" and row["egress"] != "approved_remote":
                    return "denied"
                if json.dumps(item, sort_keys=True, allow_nan=False) != json.dumps(self._item(row, item.get("citation_id")), sort_keys=True, allow_nan=False):
                    return "denied"
        return "current"

    def checkpoint_refs(self, task_id: str, *, scope_ref: str, items: list[dict]) -> None:
        """Dependency references only; no task prose, compaction or wire task_resume."""
        if not _identifier(task_id) or scope_ref not in self.scopes:
            raise ValueError("Invalid task binding")
        refs = [(item["source_id"], item["revision_id"], item["chunk_id"]) for item in items]
        if not refs or len(refs) > 32 or len(set(refs)) != len(refs):
            raise ValueError("Invalid references")
        if len(self._live_refs(refs, scope_ref)) != len(refs):
            raise ValueError("Unavailable references")
        with self.db:
            existing = self.db.execute("SELECT principal,scope_ref FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            if existing and tuple(existing) != (self.principal, scope_ref):
                raise ValueError("Task scope cannot change")
            self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?,?,?)", (task_id,self.principal,scope_ref,json.dumps(refs)))
            self._changed()

    def _live_refs(self, refs: list, scope_ref: str) -> list:
        live = []
        for source, revision, chunk in refs:
            row = self.db.execute("""SELECT s.collection FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id
                JOIN sources s ON s.source_id=r.source_id WHERE s.source_id=? AND r.revision_id=?
                AND ('c-'||c.id)=? AND s.state='active' AND r.lifecycle='active' AND s.freshness!='stale'""",
                (source,revision,chunk)).fetchone()
            if row and row["collection"] in self.scopes[scope_ref]:
                live.append((source,revision,chunk))
        return live

    def resume_refs(self, task_id: str, *, scope_ref: str) -> list:
        if scope_ref not in self.scopes:
            return []
        with self.db:
            self.db.execute("BEGIN")
            row = self.db.execute("SELECT refs_json FROM tasks WHERE task_id=? AND principal=? AND scope_ref=?",
                                  (task_id,self.principal,scope_ref)).fetchone()
            if not row:
                return []
            refs = json.loads(row["refs_json"])
            live = self._live_refs(refs, scope_ref)
            return live if len(live) == len(refs) else []
