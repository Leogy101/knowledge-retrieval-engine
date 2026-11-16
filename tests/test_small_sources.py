"""Small-source evidence units: exactness, boundaries and upgrade behavior.

No benchmark IDs, gold spans or model calls are used by ingestion/retrieval.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kre import Store, evidence_ref
from kre.ingestion import chunks, normalize, PARSER_VERSION, TARGET_CHUNK_BYTES


def request(query="Meridian", **updates):
    value = {"contract_version": "0.1", "request_id": "small-source",
             "query": query, "access_scope_ref": "reader",
             "destination": "local_only", "purpose": "current_answer",
             "budget": {"max_tokens": 16000, "max_bytes": 16000, "max_items": 16}}
    value.update(updates)
    return value


class SmallSourceTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:", principal="owner",
                           scopes={"reader": {"public"}, "owner": {"public", "private"}},
                           destinations=frozenset({"local_only", "approved_remote"}))
        self.addCleanup(self.store.close)

    def ingest(self, source, text, **labels):
        return self.store.ingest_text(source, text, collection=labels.pop("collection", "public"), **labels)

    def test_complete_unit_preserves_internal_blank_lines_and_original_coordinates(self):
        raw = "\ufeff\r\n# Meridian\r\n\r\n  Receive two keys.  \r\n \t\r\nAsk the custodian.\r\n\r\n"
        text = normalize(raw)
        self.assertEqual(chunks(text), [(2, 6, "\n".join(text.split("\n")[1:6]))])
        self.ingest("manual", raw)
        result = self.store.context(request())
        item, = result["items"]
        self.assertEqual((item["locator"]["line_start"], item["locator"]["line_end"]), (2, 6))
        self.assertEqual(item["text"], chunks(text)[0][2])
        self.assertEqual(item["content_sha256"], hashlib.sha256(item["text"].encode()).hexdigest())
        self.assertEqual(self.store.validate_context(result, scope_ref="reader", destination="local_only"), "current")

    def test_threshold_is_utf8_bytes_and_large_source_chunking_is_unchanged(self):
        prefix = "# Manual\n\n"
        small = prefix + "é" * ((TARGET_CHUNK_BYTES - len(prefix.encode())) // 2)
        self.assertEqual(len(small.encode()), TARGET_CHUNK_BYTES)
        self.assertEqual(len(chunks(small)), 1)
        larger = small + "x"
        self.assertEqual(len(larger.encode()), TARGET_CHUNK_BYTES + 1)
        self.assertEqual(chunks(larger), [(1, 1, "# Manual"), (3, 3, larger.split("\n")[2])])

    def test_two_distinct_sources_fit_two_items_without_losing_nonmatching_facts(self):
        self.ingest("manual", "# Meridian collection\n\nKeep six samples.\n\nObtain a signed receipt.")
        self.ingest("handoff", "# Meridian handoff\n\nThe custodian is Priya.\n\nUse the east counter.")
        result = self.store.context(request(budget={"max_tokens": 4000, "max_bytes": 4000, "max_items": 2}))
        self.assertEqual({i["source_id"] for i in result["items"]}, {"manual", "handoff"})
        text = "\n".join(i["text"] for i in result["items"])
        for fact in ("six samples", "signed receipt", "Priya", "east counter"):
            self.assertIn(fact, text)
        self.assertLessEqual(result["token_usage"]["context_bytes"], 4000)

    def test_small_sources_still_require_lexical_candidates(self):
        self.ingest("manual", "# Meridian\n\nKeep six samples.")
        result = self.store.context(request("unmatchedplatypus"))
        self.assertEqual(result["items"], [])
        self.assertIn("NO_EVIDENCE", result["warnings"])

    def test_tight_budget_does_not_slice_or_silently_drop_required_evidence(self):
        self.ingest("manual", "# Meridian\n\nKeep six samples.\n\n" + "context " * 100)
        full = self.store.context(request())
        item, = full["items"]
        size = full["token_usage"]["context_bytes"]
        exact = request(budget={"max_tokens": size, "max_bytes": size, "max_items": 1})
        self.assertEqual(self.store.context(exact)["items"][0]["text"], item["text"])
        tight = request(budget={"max_tokens": size - 1, "max_bytes": size - 1, "max_items": 1})
        result = self.store.context_required(tight, required_refs=[evidence_ref(item)])
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(result["context"]["items"], [])
        self.assertEqual(len(result["required"]["missing"]), 1)
        self.assertEqual(self.store.context(tight)["error"]["code"], "BUDGET_TOO_SMALL")

    def test_scope_lifecycle_and_freshness_filters_still_precede_selection(self):
        for source, labels in (("active", {"freshness": "fresh"}),
                               ("private", {"collection": "private"}),
                               ("stale", {"freshness": "stale"}),
                               ("unknown", {"freshness": "unknown"}),
                               ("revoked", {"freshness": "fresh"})):
            self.ingest(source, f"# Meridian {source}\n\nKeep six samples.", **labels)
        self.store.revoke("revoked")
        result = self.store.context(request(freshness_requirement="fresh_only"))
        self.assertEqual([i["source_id"] for i in result["items"]], ["active"])
        self.assertEqual(self.store.validate_context(result, scope_ref="reader", destination="local_only"), "current")
        with self.assertRaises(ValueError):
            self.ingest("revoked", "# Meridian\n\nNew text.")

    def test_source_filter_egress_and_derived_labels_are_preserved(self):
        self.ingest("local", "# Meridian private transport\n\nNo export.")
        self.ingest("remote", "# Meridian derived note\n\nUnverified conclusion.",
                    egress="approved_remote", origin="model_inference", authority="unverified")
        blocked = self.store.context(request(destination="approved_remote"))
        self.assertEqual(blocked["items"], [])
        self.assertEqual(blocked["error"]["code"], "DESTINATION_DENIED")
        allowed = self.store.context(request(destination="approved_remote", source_ids=["remote"]))
        item, = allowed["items"]
        self.assertEqual((item["source_id"], item["origin"], item["authority"]),
                         ("remote", "model_inference", "unverified"))

    def test_parser_upgrade_is_explicit_and_invalidates_old_task_dependencies(self):
        text = "# Meridian\n\nKeep six samples.\n\nObtain a receipt.\n"
        legacy = [(1, 1, "# Meridian"), (3, 3, "Keep six samples."), (5, 5, "Obtain a receipt.")]
        root = Path(__file__).resolve().parents[1] / ".scratch"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = str(Path(directory) / "legacy.sqlite3")
            with Store(path, principal="owner", scopes={"reader": {"public"}}) as old:
                with patch("kre.store.PARSER_VERSION", "text-lines-v1"), patch("kre.store.chunks", return_value=legacy):
                    revision = old.ingest_text("manual", text, collection="public")
                before = old.context(request("samples"))
                item, = before["items"]
                card = {"objective": {"text": "Prepare collection", "origin": "user_assertion", "refs": []},
                        "constraints": [], "questions": [], "next_actions": [],
                        "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [evidence_ref(item)]}]}
                old.checkpoint_task("collection", scope_ref="reader", card=card)
            with Store(path, principal="owner", scopes={"reader": {"public"}}) as reopened:
                self.assertEqual(reopened.context(request("samples"))["items"], before["items"])
                self.assertEqual(reopened.resume_task("collection", scope_ref="reader")["status"], "ok")
                successor = reopened.ingest_text("manual", text, collection="public")
                self.assertNotEqual(revision, successor)
                self.assertEqual(successor, reopened.ingest_text("manual", text, collection="public"))
                prior = reopened.revision(revision, scope_ref="reader")
                self.assertEqual((prior["lifecycle"], prior["text"]), ("superseded", text))
                row = reopened.db.execute("SELECT parser_version FROM revisions WHERE revision_id=?", (successor,)).fetchone()
                self.assertEqual(row["parser_version"], PARSER_VERSION)
                self.assertEqual(reopened.validate_context(before, scope_ref="reader", destination="local_only"), "changed")
                resumed = reopened.resume_task("collection", scope_ref="reader")
                self.assertEqual(resumed["status"], "partial")
                self.assertEqual(resumed["card"]["decisions"], [])
                self.assertEqual(resumed["evidence"], [])
                self.assertEqual(reopened.db.execute("SELECT count(*) FROM chunks WHERE revision_id=?", (revision,)).fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
