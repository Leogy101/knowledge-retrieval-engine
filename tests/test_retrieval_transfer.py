"""Frozen independent transfer checks; no generated answers or model calls.

The three recall cases were frozen before the focused retrieval correction was
inspected. Their first evaluation is held out; subsequent runs are regressions.
Gold spans are used only by assertions, never as retrieval parameters.
"""
import hashlib
import json
from pathlib import Path
import unittest

from kre import Store
from kre.store import evidence_ref

FIXTURE = Path(__file__).resolve().parents[1] / "evaluation/retrieval-correction-transfer"


def load_fixture():
    raw = (FIXTURE / "fixture.json").read_bytes()
    freeze = json.loads((FIXTURE / "freeze.json").read_text())
    if hashlib.sha256(raw).hexdigest() != freeze["fixture_sha256"]:
        raise ValueError("Transfer fixture changed after freeze")
    return json.loads(raw)


def make_store(data):
    store = Store(":memory:", principal="transfer-evaluation",
                  scopes={"reader": {"public"}, "owner": {"public", "private"}})
    for source in data["sources"]:
        store.ingest_text(source["source_id"], source["text"],
                          collection=source["collection"], freshness=source["freshness"])
    return store


def request(data, query, **updates):
    value = {"contract_version": "0.1", "request_id": "transfer", "query": query,
             "access_scope_ref": "reader", "destination": "local_only",
             "purpose": "current_answer", "freshness_requirement": "allow_unknown",
             "budget": dict(data["budget"])}
    value.update(updates)
    return value


def covered(item, span):
    return (item["source_id"] == span["source_id"]
            and item["locator"]["line_start"] <= span["line_start"]
            and item["locator"]["line_end"] >= span["line_end"])


def evaluate_transfer():
    """Return measured evidence coverage without feeding labels to selection."""
    data = load_fixture()
    with make_store(data) as store:
        results = []
        for case in data["cases"]:
            response = store.context(request(data, case["query"]))
            hits = sum(any(covered(item, span) for item in response["items"])
                       for span in case["gold"])
            results.append({"case_id": case["id"], "covered_gold_spans": hits,
                            "gold_spans": len(case["gold"]),
                            "context_bytes": response["token_usage"]["context_bytes"],
                            "status": response["status"],
                            "selected": [{"source_id": item["source_id"], **item["locator"]}
                                         for item in response["items"]]})
        return {"fixture_sha256": hashlib.sha256((FIXTURE / "fixture.json").read_bytes()).hexdigest(),
                "model_calls": 0, "cases": results,
                "covered_gold_spans": sum(r["covered_gold_spans"] for r in results),
                "gold_spans": sum(r["gold_spans"] for r in results)}


class RetrievalTransferTests(unittest.TestCase):
    def setUp(self):
        self.data = load_fixture()
        self.store = make_store(self.data)
        self.addCleanup(self.store.close)

    def context(self, query, **updates):
        return self.store.context(request(self.data, query, **updates))

    def assert_integrity(self, response, budget=None):
        budget = budget or self.data["budget"]
        self.assertLessEqual(len(response["items"]), budget["max_items"])
        size = len(response["context_text"].encode())
        self.assertEqual(size, response["token_usage"]["context_bytes"])
        self.assertEqual(size, response["token_usage"]["estimated_tokens"])
        self.assertLessEqual(size, min(budget["max_tokens"], budget["max_bytes"]))
        for item in response["items"]:
            row = self.store.db.execute("SELECT text FROM revisions WHERE revision_id=? AND source_id=?",
                                        (item["revision_id"], item["source_id"])).fetchone()
            start, end = item["locator"]["line_start"], item["locator"]["line_end"]
            self.assertEqual(item["text"], "\n".join(row["text"].split("\n")[start - 1:end]))
            self.assertEqual(item["content_sha256"], hashlib.sha256(item["text"].encode()).hexdigest())
            self.assertNotEqual(item["source_id"], "private-audit")
        self.assertEqual(self.store.validate_context(response, scope_ref="reader", destination="local_only"), "current")

    def separate_required_refs(self):
        # Distinct sources guarantee two immutable references independently of
        # short-source chunking. These are local negative-path fixtures, not a
        # change to the frozen transfer corpus or retrieval gold.
        for source, text in (("required-library-access", "Library kiosk readers can inspect the catalogue."),
                             ("required-library-approval", "Library kiosk changes require librarian approval.")):
            self.store.ingest_text(source, text, collection="public")
        rows = self.store.db.execute("""SELECT c.*,r.source_id,r.recorded_at,r.lifecycle,
            s.authority,s.origin,s.freshness,s.egress FROM chunks c
            JOIN revisions r ON r.revision_id=c.revision_id JOIN sources s ON s.source_id=r.source_id
            WHERE s.source_id IN ('required-library-access','required-library-approval')
            ORDER BY s.source_id""").fetchall()
        return [evidence_ref(self.store._item(row, f"E{i + 1}")) for i, row in enumerate(rows)]

    def test_frozen_multi_fact_transfer_coverage_and_exact_citations(self):
        for case in self.data["cases"]:
            with self.subTest(case=case["id"]):
                response = self.context(case["query"])
                self.assert_integrity(response)
                self.assertTrue(all(any(covered(item, span) for item in response["items"])
                                    for span in case["gold"]),
                                [(item["source_id"], item["locator"]) for item in response["items"]])

    def test_missing_lexical_evidence_is_explicit(self):
        response = self.context("xylophonic zeppelin checksumless")
        self.assertFalse(response["items"])
        self.assertIn("NO_EVIDENCE", response["warnings"])
        self.assertEqual(response["context_text"], "")

    def test_scope_cannot_disclose_private_evidence(self):
        response = self.context("secretmarker")
        self.assertFalse(response["items"])
        self.assertIn("NO_EVIDENCE", response["warnings"])

    def test_source_filter_preserves_allowed_source_boundary(self):
        response = self.context(self.data["cases"][1]["query"], source_ids=["release-guide"])
        self.assert_integrity(response)
        self.assertTrue(response["items"])
        self.assertEqual({item["source_id"] for item in response["items"]}, {"release-guide"})

    def test_current_revision_replaces_superseded_without_rewriting_citations(self):
        before = self.context("Juniper audit records retained deletion")
        old_revisions = {item["revision_id"] for item in before["items"] if item["source_id"] == "records-guide"}
        self.store.ingest_text("records-guide", "Juniper audit records are retained for one hundred days.\n\nThe records custodian approves deletion.\n", collection="public")
        after = self.context("Juniper audit records retained deletion")
        self.assert_integrity(after)
        self.assertTrue(any(item["source_id"] == "records-guide" for item in after["items"]))
        self.assertFalse(old_revisions & {item["revision_id"] for item in after["items"]})
        self.assertEqual(self.store.validate_context(before, scope_ref="reader", destination="local_only"), "changed")

    def test_revocation_and_freshness_never_relaxed_for_coverage(self):
        self.store.revoke("recovery-guide")
        self.store.update_policy("release-guide", freshness="stale")
        response = self.context(self.data["cases"][1]["query"])
        self.assertFalse({"recovery-guide", "release-guide"} & {item["source_id"] for item in response["items"]})
        fresh = self.context("workshop library default", freshness_requirement="fresh_only")
        self.assertNotIn("workshop-notes", {item["source_id"] for item in fresh["items"]})
        self.assert_integrity(fresh)

    def test_unavailable_required_evidence_is_not_silently_omitted(self):
        refs = self.separate_required_refs()
        self.assertEqual(len(refs), 2)
        for ref in refs:
            self.store.revoke(ref["source_id"])
        result = self.store.context_required(request(self.data, "library kiosk"), required_refs=refs)
        self.assertEqual(result["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
        self.assertFalse(result["context"]["items"])
        self.assertEqual(len(result["required"]["missing"]), 2)

    def test_required_multi_fact_budget_failure_is_explicit(self):
        refs = self.separate_required_refs()
        self.assertEqual(len(refs), 2)
        query = request(self.data, "library kiosk", budget={"max_tokens": 8000, "max_bytes": 8000, "max_items": 1})
        result = self.store.context_required(query, required_refs=refs)
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertFalse(result["context"]["items"])
        self.assertEqual(len(result["required"]["missing"]), 2)


if __name__ == "__main__":
    unittest.main()
