import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kre import Store, StartupError, evidence_ref


def request(query="rollback", **changes):
    value = {"contract_version": "0.1", "request_id": "k2-test", "query": query,
             "access_scope_ref": "read", "destination": "local_only", "purpose": "current_answer",
             "budget": {"max_tokens": 20000, "max_bytes": 24000, "max_items": 16}}
    value.update(changes)
    return value


def assertion(text):
    return {"text": text, "origin": "user_assertion", "refs": []}


def card(item):
    return {"objective": assertion("Prepare a synthetic release."),
            "constraints": [assertion("Stay offline.")],
            "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [evidence_ref(item)]}],
            "questions": [assertion("Who approves the release?")],
            "next_actions": [assertion("Request explicit approval.")]}


class K2Tests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / ".scratch"
        root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "index.sqlite3")
        self.store = Store(self.path, principal="host", scopes={"read": {"public"}, "all": {"public", "private"}})
        self.addCleanup(self.store.close)
        self.store.ingest_text("guide", "rollback requires synthetic blue snapshot", collection="public")
        self.item = self.store.context(request())["items"][0]
        self.ref = evidence_ref(self.item)

    def test_policy_invalidation_freshness_and_authority_are_separate(self):
        prior = self.store.context(request())
        changed = self.store.update_policy("guide", freshness="stale")
        self.assertTrue(changed["changed"])
        self.assertEqual(changed["policy"]["authority"], "unverified")
        self.assertEqual(self.store.validate_context(prior, scope_ref="read", destination="local_only"), "changed")
        self.assertEqual(self.store.context(request())["items"], [])
        self.assertEqual(self.store.context(request(purpose="historical_evidence"))["items"][0]["freshness"], "stale")
        self.store.update_policy("guide", freshness="fresh", origin="model_inference")
        revision = self.store.ingest_text("guide", "new rollback version", collection="public")
        item = self.store.context(request())["items"][0]
        self.assertEqual((item["authority"], item["origin"], item["freshness"]), ("unverified", "model_inference", "fresh"))
        self.assertNotEqual(revision, self.ref["revision_id"])
        self.store.update_policy("guide", authority="authoritative")
        self.assertEqual(self.store.context(request())["items"][0]["authority"], "authoritative")

    def test_noop_policy_does_not_invalidate_or_mutate_revision(self):
        before = self.store._generation()
        result = self.store.update_policy("guide", freshness="unknown")
        self.assertFalse(result["changed"])
        self.assertEqual(before, self.store._generation())
        self.assertEqual(self.ref["revision_id"], self.store.context(request())["items"][0]["revision_id"])

    def test_policy_validation_and_rollback(self):
        before = self.store.status()
        for changes in ({}, {"authority": "newer"}, {"freshness": []}, {"collection": "forbidden"}):
            with self.assertRaises((ValueError, PermissionError)):
                self.store.update_policy("guide", **changes)
        self.assertEqual(before, self.store.status())
        with patch.object(self.store, "_changed", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.store.update_policy("guide", freshness="stale")
        self.assertEqual(before, self.store.status())

    def test_move_requires_existing_and_destination_grants(self):
        self.store.update_policy("guide", collection="private")
        self.assertEqual(self.store.context(request())["items"], [])
        with Store(self.path, principal="limited", scopes={"read": {"public"}}) as limited:
            with self.assertRaises(PermissionError):
                limited.update_policy("guide", freshness="fresh")
        self.assertEqual(len(self.store.context(request(access_scope_ref="all"))["items"]), 1)

    def test_policy_cannot_reactivate_revoked_source(self):
        self.store.revoke("guide")
        with self.assertRaises(ValueError):
            self.store.update_policy("guide", freshness="fresh")

    def test_required_unmatched_evidence_delivered_and_exactly_revalidated(self):
        result = self.store.context_required(request("unmatchedzebra"), required_refs=[self.ref])
        self.assertIsNone(result["error"])
        self.assertEqual(result["required"]["delivered"], [self.ref])
        self.assertEqual(result["context"]["items"][0]["text"], self.item["text"])
        self.assertEqual(self.store.validate_context(result["context"], scope_ref="read", destination="local_only"), "current")
        size = len(result["context"]["context_text"].encode())
        self.assertEqual(result["context"]["token_usage"]["estimated_tokens"], size)

    def test_required_missing_hash_and_private_fail_without_any_payload(self):
        self.store.ingest_text("secret", "private sentinel", collection="private")
        secret = self.store.context(request("sentinel", access_scope_ref="all"))["items"][0]
        forged = dict(self.ref, content_sha256="0" * 64)
        for missing in (evidence_ref(secret), forged, dict(self.ref, source_id="absent")):
            result = self.store.context_required(request(), required_refs=[self.ref, missing])
            self.assertEqual(result["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
            self.assertEqual(result["context"]["context_text"], "")
            self.assertEqual(result["required"]["delivered"], [])
            self.assertEqual(result["required"]["missing"], [{"ref": missing, "reason": "unavailable"}])
            self.assertNotIn("private sentinel", json.dumps(result))

    def test_required_budgets_are_all_or_error_including_exact_boundary(self):
        exact = self.store.context_required(request("unmatched"), required_refs=[self.ref])["context"]["token_usage"]["context_bytes"]
        tight = request(budget={"max_tokens": exact, "max_bytes": exact, "max_items": 1})
        self.assertIsNone(self.store.context_required(tight, required_refs=[self.ref])["error"])
        tight["budget"]["max_bytes"] -= 1
        failed = self.store.context_required(tight, required_refs=[self.ref])
        self.assertEqual(failed["error"]["code"], "BUDGET_TOO_SMALL")
        self.assertEqual(failed["context"]["items"], [])
        self.assertEqual(failed["required"]["missing"][0]["reason"], "budget")
        self.store.ingest_text("second", "rollback companion", collection="public")
        refs = [evidence_ref(i) for i in self.store.context(request())["items"]]
        result = self.store.context_required(request(budget={"max_tokens": 20000, "max_bytes": 20000, "max_items": 1}), required_refs=refs)
        self.assertEqual(result["error"]["code"], "BUDGET_TOO_SMALL")

    def test_required_refs_reject_duplicates_shapes_and_wire_extension(self):
        for refs in (None, {}, [self.ref, self.ref], [dict(self.ref, extra=1)], [dict(self.ref, chunk_id=True)], [dict(self.ref, content_sha256="bad")]):
            result = self.store.context_required(request(), required_refs=refs)
            self.assertEqual(result["error"]["code"], "INVALID_REQUIRED_REFS")
        self.assertEqual(self.store.context(request(required_refs=[self.ref]))["error"]["code"], "INVALID_REQUEST")

    def test_required_reference_non_utf8_identifier_returns_validation_error(self):
        surrogate = json.loads('"\\ud800"')
        result = self.store.context_required(request(), required_refs=[dict(self.ref, source_id=surrogate)])
        self.assertEqual(result["error"]["code"], "INVALID_REQUIRED_REFS")
        self.assertEqual(result["context"]["items"], [])

    def test_normal_request_non_utf8_source_id_returns_validation_error(self):
        surrogate = json.loads('"\\ud800"')
        result = self.store.context(request(source_ids=[surrogate]))
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(result["items"], [])

    def test_required_filters_and_lifecycle_current_historical(self):
        self.store.update_policy("guide", freshness="stale")
        self.assertEqual(self.store.context_required(request(), required_refs=[self.ref])["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
        self.assertIsNone(self.store.context_required(request(purpose="historical_evidence"), required_refs=[self.ref])["error"])
        for changes in ({"source_ids": ["other"]}, {"freshness_requirement": "fresh_only"}):
            self.assertEqual(self.store.context_required(request(purpose="historical_evidence", **changes), required_refs=[self.ref])["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
        self.store.update_policy("guide", freshness="fresh")
        self.store.lifecycle("guide", "supersede")
        self.assertEqual(self.store.context_required(request(), required_refs=[self.ref])["error"]["code"], "REQUIRED_EVIDENCE_MISSING")
        self.assertIsNone(self.store.context_required(request(purpose="historical_evidence"), required_refs=[self.ref])["error"])
        self.store.revoke("guide")
        self.assertEqual(self.store.context_required(request(purpose="historical_evidence"), required_refs=[self.ref])["error"]["code"], "REQUIRED_EVIDENCE_MISSING")

    def test_required_empty_and_invalid_request_stay_explicit(self):
        self.assertEqual(self.store.context_required(request(), required_refs=[])["context"]["items"][0]["text"], self.item["text"])
        result = self.store.context_required(request(query=" ".join("term%d" % i for i in range(65))), required_refs=[self.ref])
        self.assertEqual(result["error"]["code"], "INVALID_REQUEST")
        self.assertEqual(result["context"]["items"], [])

    def test_task_roundtrip_preserves_all_fields_and_exact_evidence(self):
        expected = card(self.item)
        self.store.checkpoint_task("release", scope_ref="read", card=expected)
        generation = self.store._generation()
        self.assertFalse(self.store.checkpoint_task("release", scope_ref="read", card=expected)["changed"])
        self.assertEqual(generation, self.store._generation())
        result = self.store.resume_task("release", scope_ref="read")
        self.assertEqual(result["card"], expected)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(evidence_ref(result["evidence"][0]), self.ref)
        self.assertEqual(result["evidence"][0]["authority"], "unverified")
        with Store(self.path, principal="host", scopes={"read": {"public"}}) as reopened:
            self.assertEqual(reopened.resume_task("release", scope_ref="read")["card"], expected)

    def test_task_revoked_dependent_prose_is_not_returned_even_as_assertion(self):
        saved = card(self.item)
        saved["next_actions"] = [{"text": "dependent secret action", "origin": "user_assertion", "refs": [self.ref]}]
        self.store.checkpoint_task("release", scope_ref="read", card=saved)
        self.store.revoke("guide")
        result = self.store.resume_task("release", scope_ref="read")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["card"]["decisions"], [])
        self.assertEqual(result["card"]["next_actions"], [])
        self.assertEqual(result["evidence"], [])
        self.assertNotIn(self.item["text"], json.dumps(result))
        self.assertNotIn("dependent secret action", json.dumps(result))
        self.assertEqual(result["card"]["objective"], saved["objective"])
        self.assertEqual(len(result["invalidated"]), 2)

    def test_task_stale_superseded_or_scope_lost_dependencies_excluded(self):
        self.store.checkpoint_task("release", scope_ref="read", card=card(self.item))
        self.store.update_policy("guide", freshness="stale")
        self.assertEqual(self.store.resume_task("release", scope_ref="read")["evidence"], [])
        self.store.update_policy("guide", freshness="fresh")
        self.store.ingest_text("guide", "rollback updated version", collection="public")
        self.assertEqual(self.store.resume_task("release", scope_ref="read")["evidence"], [])
        fresh_item = self.store.context(request())["items"][0]
        self.store.checkpoint_task("release", scope_ref="read", card=card(fresh_item))
        with Store(self.path, principal="host", scopes={"read": {"other"}}) as reduced:
            result = reduced.resume_task("release", scope_ref="read")
            self.assertEqual(result["card"]["decisions"], [])
            self.assertNotIn(fresh_item["text"], json.dumps(result))

    def test_task_other_principal_or_binding_denied(self):
        self.store.checkpoint_task("release", scope_ref="read", card=card(self.item))
        with Store(self.path, principal="stranger", scopes={"read": {"public"}}) as outsider:
            with self.assertRaises(PermissionError):
                outsider.resume_task("release", scope_ref="read")
            with self.assertRaises(PermissionError):
                outsider.checkpoint_task("release", scope_ref="read", card=card(self.item))
        with self.assertRaises(PermissionError):
            self.store.resume_task("release", scope_ref="all")

    def test_task_bounds_and_invalid_dependencies_preserve_previous_card(self):
        original = card(self.item)
        self.store.checkpoint_task("release", scope_ref="read", card=original)
        malformed = []
        changed = copy.deepcopy(original); changed["decisions"][0]["text"] = "invented summary"; malformed.append(changed)
        changed = copy.deepcopy(original); changed["decisions"][0]["refs"][0]["content_sha256"] = "0" * 64; malformed.append(changed)
        changed = copy.deepcopy(original); changed["objective"] = assertion("x" * 8193); malformed.append(changed)
        changed = copy.deepcopy(original); changed["constraints"] = [assertion("x")] * 17; malformed.append(changed)
        changed = copy.deepcopy(original); changed["decisions"][0] = {"text": "guess", "origin": "model_inference", "refs": []}; malformed.append(changed)
        changed = copy.deepcopy(original); changed["questions"] = [assertion("x" * 8000)] * 5; malformed.append(changed)
        for value in malformed:
            with self.assertRaises(ValueError):
                self.store.checkpoint_task("release", scope_ref="read", card=value)
        self.assertEqual(self.store.resume_task("release", scope_ref="read")["card"], original)

    def test_task_checkpoint_failure_rolls_back_prose_and_generation(self):
        before = self.store._generation()
        with patch.object(self.store, "_changed", side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.store.checkpoint_task("release", scope_ref="read", card=card(self.item))
        self.assertEqual(before, self.store._generation())
        with self.assertRaises(PermissionError):
            self.store.resume_task("release", scope_ref="read")

    def test_task_corrupted_extractive_text_cannot_resume_as_evidence(self):
        value = card(self.item)
        self.store.checkpoint_task("release", scope_ref="read", card=value)
        value["decisions"][0]["text"] = "fabricated replacement"
        with self.store.db:
            self.store.db.execute("UPDATE task_cards SET card_json=?", (json.dumps(value),))
        result = self.store.resume_task("release", scope_ref="read")
        self.assertEqual(result["card"]["decisions"], [])
        self.assertNotIn("fabricated replacement", json.dumps(result))

    def test_task_cannot_promote_derived_origin_and_revalidates_origin_changes(self):
        for origin in ("model_inference", "user_assertion"):
            self.store.update_policy("guide", origin=origin)
            with self.assertRaises(ValueError):
                self.store.checkpoint_task("release", scope_ref="read", card=card(self.item))
        self.store.update_policy("guide", origin="source_evidence")
        self.store.checkpoint_task("release", scope_ref="read", card=card(self.item))
        self.store.update_policy("guide", origin="model_inference")
        resumed = self.store.resume_task("release", scope_ref="read")
        self.assertEqual(resumed["status"], "partial")
        self.assertEqual(resumed["card"]["decisions"], [])
        self.assertEqual(resumed["evidence"], [])
        self.assertNotIn(self.item["text"], json.dumps(resumed))


class MigrationTests(unittest.TestCase):
    def make_k1(self, path):
        connection = sqlite3.connect(path)
        connection.executescript((Path(__file__).parent / "fixtures/k1_schema.sql").read_text())
        text = "rollback K1 preserved"
        digest = hashlib.sha256(text.encode()).hexdigest()
        connection.execute("INSERT INTO sources VALUES ('legacy','public','unverified','source_evidence','unknown','local_only','active','')")
        for revision, lifecycle in (("r-before", "superseded"), ("r-current", "active")):
            connection.execute("INSERT INTO revisions VALUES (?, 'legacy', ?, ?, '2026-11-14T00:00:00Z', ?, ?, 'text-lines-v1')", (revision, text, digest, lifecycle, digest))
            cursor = connection.execute("INSERT INTO chunks(revision_id,text,line_start,line_end) VALUES (?,?,1,1)", (revision, text))
            connection.execute("INSERT INTO chunk_fts(rowid,text) VALUES (?,?)", (cursor.lastrowid, text))
        connection.execute("INSERT INTO tasks VALUES ('legacy-task','host','read',?)", (json.dumps([["legacy", "r-current", "c-2"]]),))
        connection.commit()
        before = {table: connection.execute("SELECT * FROM " + table).fetchall() for table in ("sources", "revisions", "chunks", "tasks")}
        connection.close()
        return before

    def test_actual_committed_k1_schema_migrates_preserving_revisions_and_legacy_tasks(self):
        root = Path(__file__).resolve().parents[1] / ".scratch"; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = str(Path(directory) / "old.sqlite3")
            before = self.make_k1(path)
            with Store(path, principal="host", scopes={"read": {"public"}}) as store:
                self.assertEqual(store.status()["schema_version"], 2)
                for table, rows in before.items():
                    self.assertEqual(rows, [tuple(r) for r in store.db.execute("SELECT * FROM " + table)])
                self.assertEqual(store.resume_refs("legacy-task", scope_ref="read"), [("legacy", "r-current", "c-2")])
                item = store.context(request())["items"][0]
                self.assertEqual(item["revision_id"], "r-current")
                self.assertEqual(item["locator"]["line_start"], 1)
                store.checkpoint_task("new-task", scope_ref="read", card=card(item))
                self.assertEqual(store.resume_task("new-task", scope_ref="read")["status"], "ok")
            with Store(path, principal="host", scopes={"read": {"public"}}) as reopened:
                self.assertEqual(reopened.status()["schema_version"], 2)

    def test_migration_failure_rolls_back_schema_and_keeps_k1_readable(self):
        class FailMigration(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql == "PRAGMA user_version=2":
                    raise sqlite3.OperationalError("injected migration failure")
                return super().execute(sql, *args)
        root = Path(__file__).resolve().parents[1] / ".scratch"; root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path = str(Path(directory) / "old.sqlite3")
            before = self.make_k1(path)
            connect = sqlite3.connect
            with patch("kre.store.sqlite3.connect", side_effect=lambda *a, **k: connect(*a, factory=FailMigration, **k)):
                with self.assertRaises(StartupError):
                    Store(path, principal="host", scopes={"read": {"public"}})
            connection = connect(path)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='task_cards'").fetchone())
            self.assertEqual(connection.execute("SELECT * FROM revisions").fetchall(), before["revisions"])
            connection.close()


if __name__ == "__main__":
    unittest.main()
