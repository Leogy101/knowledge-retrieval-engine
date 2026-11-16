"""Scorer integrity tests use toy responses; held-out recall is not asserted."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("post96_transfer", ROOT / "scripts/evaluate_post96_transfer.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class TransferScoringTests(unittest.TestCase):
    def setUp(self):
        self.source = {"source_id": "toy-note", "text": "Introductory line\nFirst required fact\nSecond required fact",
                       "collection": "public", "freshness": "fresh", "state": "active",
                       "authority": "authoritative", "origin": "source_evidence"}
        self.fixture = {"sources": [self.source], "scope_definitions": {"reader": {"collections": ["public"]}}}
        self.case = {"id": "toy-case", "query": "toy facts", "scope": "reader", "destination": "local_only",
                     "purpose": "current_answer", "budget": {"max_tokens": 12000, "max_bytes": 12000, "max_items": 12},
                     "forbidden_sources": [], "gold": [{"source_id": "toy-note", "line_start": 2, "line_end": 3,
                                                          "quote": "First required fact\nSecond required fact"}]}
        self.registry = []
        for number, text in enumerate(self.source["text"].splitlines(), 1):
            self.registry.append({"source_id": "toy-note", "revision_id": "r-toy", "chunk_id": f"c-{number}",
                                  "text": text, "line_start": number, "line_end": number, "lifecycle": "active",
                                  "content_sha256": evaluation.sha256(text.encode())})

    def response(self, line_numbers, error=None):
        items = []
        for position, number in enumerate(line_numbers, 1):
            row = self.registry[number - 1]
            items.append({"citation_id": f"E{position}", "source_id": row["source_id"], "revision_id": row["revision_id"],
                          "chunk_id": row["chunk_id"], "text": row["text"], "content_sha256": row["content_sha256"],
                          "locator": {"line_start": number, "line_end": number}, "authority": self.source["authority"],
                          "origin": self.source["origin"], "freshness": self.source["freshness"], "lifecycle": "active",
                          "egress": {"restriction": "local_only"}})
        result = {"items": items, "context_text": evaluation.render(items), "status": "error" if error else "ok",
                  "error": {"code": error, "message": "toy error", "retryable": False} if error else None,
                  "omissions": {}, "warnings": [], "token_usage": {"counter_kind": "conservative_bytes",
                  "counter_id": "utf8_bytes", "includes_citations": True}}
        self.recount(result)
        return result

    @staticmethod
    def recount(response):
        response["context_text"] = evaluation.render(response["items"])
        size = len(response["context_text"].encode())
        response["token_usage"].update(context_bytes=size, estimated_tokens=size)

    def score(self, response):
        return evaluation.score_case(self.fixture, self.case, response, self.registry)

    def test_frozen_artifacts_and_exact_gold(self):
        fixture, _ = evaluation.load_frozen(ROOT / "evaluation/post96-transfer")
        self.assertEqual(len(fixture["cases"]), 8)
        self.assertEqual(len(fixture["sources"]), 37)

    def test_frozen_artifact_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "fixture"
            shutil.copytree(ROOT / "evaluation/post96-transfer", folder)
            path = folder / "offline-transfer-eight.v1.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "Frozen artifact changed"):
                evaluation.load_frozen(folder)

    def test_gold_can_cross_two_exact_chunks(self):
        result = self.score(self.response([2, 3]))
        self.assertEqual(result["gold_spans_covered"], 1)
        self.assertTrue(result["integrity_pass"])

    def test_same_source_and_partial_span_do_not_count_as_complete(self):
        self.assertEqual(self.score(self.response([1]))["gold_spans_covered"], 0)
        result = self.score(self.response([2]))
        self.assertEqual(result["gold_spans_covered"], 0)
        self.assertEqual(result["gold_lines_covered"], 1)

    def test_forged_text_hash_locator_and_identity_are_rejected(self):
        for key, value in (("text", "Altered fact"), ("content_sha256", "0" * 64),
                           ("chunk_id", "c-unknown"), ("locator", {"line_start": 1, "line_end": 1})):
            with self.subTest(key=key):
                response = self.response([2, 3])
                response["items"][0][key] = value
                self.recount(response)
                result = self.score(response)
                self.assertFalse(result["integrity_pass"])
                self.assertEqual(result["gold_spans_covered"], 0)

    def test_restricted_exact_evidence_cannot_supply_gold(self):
        for key, value in (("collection", "private"), ("state", "revoked"), ("freshness", "stale")):
            with self.subTest(key=key):
                saved = self.source[key]
                self.source[key] = value
                result = self.score(self.response([2, 3]))
                self.assertFalse(result["integrity"]["scope_lifecycle_freshness"])
                self.assertEqual(result["gold_spans_covered"], 0)
                self.source[key] = saved
        self.case["forbidden_sources"] = ["toy-note"]
        self.assertFalse(self.score(self.response([2, 3]))["integrity_pass"])

    def test_metadata_promotion_and_hidden_budget_overflow_fail_integrity(self):
        response = self.response([2, 3])
        self.source["authority"] = "unverified"
        self.assertFalse(self.score(response)["integrity_pass"])
        self.source["authority"] = "authoritative"
        self.case["budget"]["max_tokens"] = 100
        self.assertFalse(self.score(response)["integrity"]["budget"])
        response["token_usage"]["estimated_tokens"] = 1
        self.assertFalse(self.score(response)["integrity"]["token_accounting"])

    def test_request_errors_remain_zero_coverage_without_integrity_failure(self):
        result = self.score(self.response([], "BUDGET_TOO_SMALL"))
        self.assertTrue(result["integrity_pass"])
        self.assertEqual(result["gold_spans_covered"], 0)
        self.assertEqual(result["request_error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(result["item_checks"], [])


if __name__ == "__main__":
    unittest.main()
