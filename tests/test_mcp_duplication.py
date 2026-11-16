"""Offline investigation: redundant text and the existing validation contract."""
import copy
import io
import json
import unittest

from kre import Store, evidence_ref
from kre._stdio import serve
from kre.mcp import KnowledgeTools


SENTINEL = "SYNTHETIC_DUPLICATION_SENTINEL_7C9A"


class DuplicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:", principal="fixture", scopes={"scope": {"shared"}},
                           destinations=frozenset({"approved_remote"}))
        self.addCleanup(self.store.close)
        self.store.ingest_text("fixture-source", SENTINEL + " is a fictional project code.",
                               collection="shared", egress="approved_remote", freshness="fresh")
        self.handler = KnowledgeTools(self.store, scope_ref="scope", destination="approved_remote")

    def retrieve(self, **extra):
        return self.handler.call("kre_retrieve", {"query": SENTINEL, **extra})

    def test_text_only_wire_contains_two_equal_evidence_representations(self):
        result = self.retrieve()
        context = result["context"]
        self.assertEqual(json.loads(context["context_text"]), context["items"])
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "synthetic", "version": "1"}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": "kre_retrieve", "arguments": {"query": SENTINEL}}},
        ]
        incoming = io.BytesIO(b"".join(json.dumps(x).encode() + b"\n" for x in messages))
        outgoing = io.BytesIO()
        serve("kre", "test", self.handler.definitions(), lambda name, args: result,
              incoming=incoming, outgoing=outgoing)
        wire = json.loads(outgoing.getvalue().splitlines()[-1])["result"]
        self.assertNotIn("structuredContent", wire)
        self.assertEqual(len(wire["content"]), 1)
        text = wire["content"][0]["text"]
        self.assertEqual(text.count(SENTINEL), 2)
        self.assertEqual(json.loads(text), result)

    def test_deleting_either_representation_breaks_current_validation(self):
        context = self.retrieve()["context"]
        self.assertEqual(self.handler.call("kre_validate", {"context": context})["validation"], "current")
        for field in ("items", "context_text"):
            candidate = copy.deepcopy(context)
            del candidate[field]
            self.assertEqual(self.handler.call("kre_validate", {"context": candidate})["validation"], "denied")

    def test_reconstruction_is_lossless_but_does_not_restore_revoked_evidence(self):
        context = self.retrieve()["context"]
        candidate = copy.deepcopy(context)
        del candidate["context_text"]
        # Diagnostic only: this is not a new accepted wire format or a runtime adapter.
        candidate["context_text"] = Store._render(candidate["items"])
        self.assertEqual(candidate, context)
        self.assertEqual(self.handler.call("kre_validate", {"context": candidate})["validation"], "current")
        ref = evidence_ref(candidate["items"][0])
        self.store.revoke("fixture-source")
        self.assertEqual(self.handler.call("kre_validate", {"context": candidate})["validation"], "changed")
        result = self.retrieve(required_refs=[ref])
        self.assertEqual(result["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
        self.assertEqual(result["context"]["items"], [])
        self.assertEqual(result["context"]["context_text"], "")

    def test_required_evidence_is_not_dropped_to_make_wire_smaller(self):
        ref = evidence_ref(self.retrieve()["context"]["items"][0])
        result = self.retrieve(max_bytes=80, required_refs=[ref])
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(result["context"]["items"], [])
        self.assertEqual(result["context"]["context_text"], "")


if __name__ == "__main__":
    unittest.main()
