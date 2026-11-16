"""Readiness regression examples, separate from the now-used tuning corpus."""
import unittest

from kre import Store, evidence_ref


def request(query, *, max_items=5, max_bytes=6000, historical=False):
    return {"contract_version": "0.1", "request_id": "heading-packing", "query": query,
            "access_scope_ref": "read", "destination": "local_only",
            "purpose": "historical_evidence" if historical else "current_answer",
            "budget": {"max_tokens": max_bytes, "max_bytes": max_bytes, "max_items": max_items}}


class HeadingPackingTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:", principal="synthetic", scopes={"read": {"notes"}})
        self.addCleanup(self.store.close)

    def add(self, source, text):
        # These cases exercise standalone headings in paragraph-sized chunks.
        # Short sources now stay whole, so keep this fixture above that bound.
        text += "\n\n" + "unrelated-padding " * 100 + "\n"
        return self.store.ingest_text(source, text, collection="notes")

    def test_two_sources_body_evidence_not_displaced_by_redundant_headings(self):
        self.add("east", "# Eastwind\n\nEastwind needs the synthetic copper switch.\n")
        self.add("west", "# Westwind\n\nWestwind needs the synthetic silver switch.\n")
        context = self.store.context(request("Eastwind Westwind", max_items=2))
        self.assertEqual({item["source_id"] for item in context["items"]}, {"east", "west"})
        self.assertTrue(all(item["locator"]["line_start"] == 3 for item in context["items"]))
        self.assertEqual(self.store.validate_context(context, scope_ref="read", destination="local_only"), "current")

    def test_heading_with_unique_query_word_is_preserved(self):
        self.add("guide", "# Quartz controls\n\nSafety requires an operator.\n")
        items = self.store.context(request("quartz safety"))["items"]
        self.assertEqual(len(items), 2)
        self.assertIn("# Quartz controls", [item["text"] for item in items])

    def test_standalone_heading_and_required_heading_are_preserved(self):
        self.add("heading-only", "# Quartz\n\nUnrelated body content.\n")
        heading = self.store.context(request("quartz"))["items"][0]
        self.assertEqual(heading["text"], "# Quartz")
        self.add("body", "# Magnet\n\nMagnet uses a synthetic coil.\n")
        row = self.store.db.execute("SELECT c.* FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id WHERE r.source_id='body' AND c.line_start=1").fetchone()
        revision = row["revision_id"]
        import hashlib
        ref = {"source_id": "body", "revision_id": revision, "chunk_id": f"c-{row['id']}",
               "content_sha256": hashlib.sha256(row["text"].encode()).hexdigest()}
        result = self.store.context_required(request("magnet"), required_refs=[ref])
        self.assertEqual(result["required"]["delivered"], [ref])
        self.assertEqual(len(result["context"]["items"]), 2)

    def test_heading_fallback_when_covering_body_exceeds_budget(self):
        self.add("guide", "# Quartz\n\nQuartz " + "x" * 1200)
        context = self.store.context(request("quartz", max_bytes=600))
        self.assertEqual([item["text"] for item in context["items"]], ["# Quartz"])
        self.assertLessEqual(context["token_usage"]["context_bytes"], 600)
        self.assertEqual(context["status"], "partial")

    def test_equal_text_across_revisions_keeps_each_provenance(self):
        first = self.add("guide", "# Quartz\n\nQuartz count is seven.\n")
        second = self.add("guide", "# Quartz revised\n\nQuartz count is seven.\n")
        items = self.store.context(request("quartz", historical=True))["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual({item["revision_id"] for item in items}, {first, second})
        self.assertTrue(all(item["text"] == "Quartz count is seven." for item in items))
        self.assertNotEqual(evidence_ref(items[0]), evidence_ref(items[1]))


if __name__ == "__main__":
    unittest.main()
