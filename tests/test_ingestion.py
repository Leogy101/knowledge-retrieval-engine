import copy
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kre import Store, IngestError, StartupError
from kre.ingestion import chunks, normalize, MAX_FILE_BYTES


def request(query="rollback", **changes):
    result = {"contract_version": "0.1", "request_id": "file-test", "query": query,
              "access_scope_ref": "read", "destination": "local_only", "purpose": "current_answer",
              "budget": {"max_tokens": 32768, "max_items": 32, "max_bytes": 262144}}
    result.update(changes)
    return result


class FileTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.root = self.home / "allowed"
        self.root.mkdir()
        self.store = Store(str(self.home / "test.sqlite3"), principal="reader", scopes={"read": {"docs"}}, permitted_roots=[self.root])
        self.addCleanup(self.store.close)

    def write(self, name, raw):
        target = self.root / name
        target.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        return target

    def test_markdown_original_lines_bom_crlf_and_exact_hash(self):
        raw = b'\xef\xbb\xbf# Guide\r\n\r\n  rollback first  \r\nrollback second\r\n\r\n# End\r\n'
        path = self.write("guide.md", raw)
        result = self.store.ingest_file(path, collection="docs")
        items = self.store.context(request())["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["locator"]["line_start"], 1)
        self.assertEqual(item["locator"]["line_end"], 6)
        original_lines = raw.decode("utf-8-sig").replace("\r\n", "\n").split("\n")
        self.assertEqual(item["text"], "\n".join(original_lines[:6]))
        revision = self.store.revision(result["revision_id"], scope_ref="read")
        self.assertEqual(revision["original_hash"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(item["content_sha256"], hashlib.sha256(item["text"].encode()).hexdigest())

    def test_repeat_file_idempotent_and_byte_change_preserves_old_revision(self):
        path = self.write("guide.txt", "rollback\r\n")
        first = self.store.ingest_file(path, collection="docs")
        generation = self.store._generation()
        self.assertEqual(first, self.store.ingest_file(path, collection="docs"))
        self.assertEqual(generation, self.store._generation())
        path.write_text("rollback\n")
        second = self.store.ingest_file(path, collection="docs")
        self.assertEqual(first["source_id"], second["source_id"])
        self.assertNotEqual(first["revision_id"], second["revision_id"])
        self.assertEqual(self.store.revision(first["revision_id"], scope_ref="read")["lifecycle"], "superseded")

    def test_citation_resolves_after_mutable_file_changes(self):
        path = self.write("guide.md", "heading\n\nrollback original\n")
        first = self.store.ingest_file(path, collection="docs")
        item = self.store.context(request())["items"][0]
        path.write_text("unrelated changed file")
        stored = self.store.revision(first["revision_id"], scope_ref="read")
        self.assertEqual(item["locator"], {"label": "lines 1-3", "line_start": 1, "line_end": 3})
        self.assertEqual("\n".join(stored["text"].split("\n")[:3]), item["text"])
        self.assertIn("rollback original", item["text"])

    def test_outside_root_and_parent_traversal_rejected(self):
        outside = self.home / "outside.txt"
        outside.write_text("private rollback")
        for path in (outside, self.root / ".." / "outside.txt"):
            with self.assertRaises(IngestError):
                self.store.ingest_file(path, collection="docs")
        self.assertEqual(self.store.status()["sources"], [])

    def test_symlink_file_and_directory_escape_rejected(self):
        outside = self.home / "outside.txt"
        outside.write_text("private rollback")
        link = self.root / "link.txt"
        link.symlink_to(outside)
        directory = self.root / "linked-dir"
        directory.symlink_to(self.home, target_is_directory=True)
        for path in (link, directory / "outside.txt"):
            with self.assertRaises(IngestError):
                self.store.ingest_file(path, collection="docs")
        self.assertEqual(self.store.context(request())["items"], [])

    def test_symlinks_within_root_are_also_rejected(self):
        path = self.write("actual.txt", "rollback")
        link = self.root / "alias.txt"
        link.symlink_to(path)
        with self.assertRaises(IngestError):
            self.store.ingest_file(link, collection="docs")

    def test_trusted_root_alias_maps_to_canonical_root_without_following_descendants(self):
        path = self.write("guide.txt", "rollback")
        alias = self.home / "root-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        outside = self.home / "private.txt"
        outside.write_text("secret rollback")
        (self.root / "escape.txt").symlink_to(outside)
        with Store(":memory:", principal="reader", scopes={"read": {"docs"}}, permitted_roots=[alias]) as aliased:
            first = aliased.ingest_file(alias / "guide.txt", collection="docs")
            self.assertEqual(first["path"], str(path.resolve()))
            self.assertEqual(first, aliased.ingest_file(path.resolve(), collection="docs"))
            with self.assertRaises(IngestError):
                aliased.ingest_file(alias / "escape.txt", collection="docs")

    def test_requires_explicit_root_and_supported_extension(self):
        path = self.write("guide.txt", "rollback")
        with Store(":memory:", principal="reader", scopes={"read": {"docs"}}) as no_roots:
            with self.assertRaises(IngestError):
                no_roots.ingest_file(path, collection="docs")
        with self.assertRaises(IngestError):
            self.store.ingest_file(self.write("guide.py", "rollback"), collection="docs")

    def test_invalid_encoding_empty_binary_large_and_long_line_leave_no_sources(self):
        for raw in (b"\xff", b"", b"rollback\x00binary", b"x" * 8193):
            path = self.write("invalid.txt", raw)
            with self.assertRaises(IngestError):
                self.store.ingest_file(path, collection="docs")
        path = self.root / "large.txt"
        with path.open("wb") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        with self.assertRaises(IngestError):
            self.store.ingest_file(path, collection="docs")
        self.assertEqual(self.store.status()["sources"], [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "POSIX FIFO fixture")
    def test_special_file_rejected_without_blocking(self):
        path = self.root / "pipe.txt"
        os.mkfifo(path)
        with self.assertRaises(IngestError):
            self.store.ingest_file(path, collection="docs")

    def test_parse_failure_leaves_existing_revision_and_timestamp(self):
        path = self.write("guide.txt", "rollback intact")
        first = self.store.ingest_file(path, collection="docs")
        before = self.store.context(request())
        path.write_bytes(b"\xff")
        with self.assertRaises(IngestError):
            self.store.ingest_file(path, collection="docs")
        after = self.store.context(request())
        self.assertEqual(before["items"], after["items"])
        self.assertEqual(before["context_revision"], after["context_revision"])
        self.assertEqual(first["revision_id"], after["items"][0]["revision_id"])

    def test_deterministic_paragraph_splitting_preserves_lines(self):
        text = "# Title\n\n" + "\n".join("line %d " % i + "é" * 150 for i in range(10))
        normalized = normalize(text)
        result = chunks(normalized)
        self.assertEqual(result, chunks(normalized))
        self.assertGreater(len(result), 2)
        lines = normalized.split("\n")
        for start, end, excerpt in result:
            self.assertEqual(excerpt, "\n".join(lines[start-1:end]))

    def test_deleted_tombstone_excludes_history_and_inspection(self):
        result = self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        self.store.lifecycle(result["source_id"], "delete")
        self.assertEqual(self.store.status()["sources"][0]["state"], "deleted")
        self.assertEqual(self.store.context(request(purpose="historical_evidence"))["items"], [])
        with self.assertRaises(PermissionError):
            self.store.revision(result["revision_id"], scope_ref="read")
        with self.assertRaises(ValueError):
            self.store.ingest_file(self.root / "guide.txt", collection="docs")

    def test_explicit_supersede_retains_only_history(self):
        result = self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        self.store.lifecycle(result["source_id"], "supersede")
        self.assertEqual(self.store.context(request())["items"], [])
        self.assertEqual(self.store.context(request(purpose="historical_evidence"))["items"][0]["lifecycle"], "superseded")

    def test_status_lifecycle_and_revision_respect_caller_collections(self):
        result = self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        with Store(str(self.home / "test.sqlite3"), principal="outsider", scopes={"read": {"other"}}) as outsider:
            self.assertEqual(outsider.status()["sources"], [])
            with self.assertRaises(PermissionError):
                outsider.lifecycle(result["source_id"], "revoke")
            with self.assertRaises(PermissionError):
                outsider.revision(result["revision_id"], scope_ref="read")
            with self.assertRaises(PermissionError):
                outsider.ingest_text("injected", "rollback", collection="docs")

    def test_corrupt_context_item_and_accounting_denied(self):
        self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        response = self.store.context(request())
        for key, value in (("chunk_id", []), ("content_sha256", "0" * 64), ("locator", {})):
            mutated = copy.deepcopy(response)
            mutated["items"][0][key] = value
            mutated["context_text"] = self.store._render(mutated["items"])
            self.assertEqual(self.store.validate_context(mutated, scope_ref="read", destination="local_only"), "denied")
        response["token_usage"]["context_bytes"] = 1
        self.assertEqual(self.store.validate_context(response, scope_ref="read", destination="local_only"), "denied")

    def test_bad_usage_container_is_denied(self):
        self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        for value in (None, []):
            response = self.store.context(request())
            response["token_usage"] = value
            self.assertEqual(self.store.validate_context(response, scope_ref="read", destination="local_only"), "denied")

    def test_boolean_line_locator_is_not_equal_to_integer(self):
        self.store.ingest_file(self.write("guide.txt", "rollback"), collection="docs")
        response = self.store.context(request())
        response["items"][0]["locator"]["line_start"] = True
        response["context_text"] = self.store._render(response["items"])
        size = len(response["context_text"].encode())
        response["token_usage"].update(context_bytes=size, estimated_tokens=size)
        self.assertEqual(self.store.validate_context(response, scope_ref="read", destination="local_only"), "denied")


class StartupTests(unittest.TestCase):
    def test_new_database_private_permissions_existing_permissions_unchanged(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "private.sqlite3"
            with Store(str(path), principal="host", scopes={"read": {"docs"}}):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            path.chmod(0o640)
            with Store(str(path), principal="host", scopes={"read": {"docs"}}):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_missing_essential_column_fails_at_startup(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "broken.sqlite3"
            with Store(str(path), principal="host", scopes={"read": {"docs"}}) as store:
                store.db.execute("ALTER TABLE sources DROP COLUMN authority")
                store.db.commit()
            before = path.read_bytes()
            with self.assertRaises(StartupError):
                Store(str(path), principal="host", scopes={"read": {"docs"}})
            self.assertEqual(before, path.read_bytes())

    def test_foreign_and_future_databases_are_rejected_without_mutation(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path = Path(directory) / "foreign.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE personal(value TEXT)")
            connection.execute("INSERT INTO personal VALUES ('untouched')")
            connection.commit()
            connection.close()
            before = path.read_bytes()
            with self.assertRaises(StartupError):
                Store(str(path), principal="host", scopes={"read": {"docs"}})
            self.assertEqual(before, path.read_bytes())
            path.unlink()
            with Store(str(path), principal="host", scopes={"read": {"docs"}}) as owned:
                owned.db.execute("PRAGMA user_version=99")
                owned.db.commit()
            with self.assertRaises(StartupError):
                Store(str(path), principal="host", scopes={"read": {"docs"}})

    def test_missing_fts_runtime_has_explicit_startup_error(self):
        class NoFTS(sqlite3.Connection):
            def execute(self, sql, *args):
                if "CREATE VIRTUAL TABLE" in sql:
                    raise sqlite3.OperationalError("no such module: fts5")
                return super().execute(sql, *args)
        real_connect = sqlite3.connect
        with patch("kre.store.sqlite3.connect", side_effect=lambda *a, **k: real_connect(*a, factory=NoFTS, **k)):
            with self.assertRaises(StartupError):
                Store(":memory:", principal="host", scopes={"read": {"docs"}})


if __name__ == "__main__":
    unittest.main()
