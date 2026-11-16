import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CLITests(unittest.TestCase):
    def test_k2_policy_required_checkpoint_resume_and_demo(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            base = Path(directory)
            db = base / "k2.sqlite3"
            path = base / "guide.md"
            path.write_text("rollback synthetic approval\n")
            def run(*args, expected=0):
                result = subprocess.run([sys.executable, "-m", "kre", "--db", str(db), *args], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                return json.loads(result.stdout)
            ingested = run("ingest", str(path), "--root", str(base))["files"][0]
            run("update-policy", ingested["source_id"], "--freshness", "fresh")
            item = run("context", "rollback")["items"][0]
            ref = {key: item[key] for key in ("source_id", "revision_id", "chunk_id", "content_sha256")}
            refs_file = base / "refs.json"; refs_file.write_text(json.dumps([ref]))
            self.assertEqual(run("context", "irrelevant", "--required", str(refs_file))["required"]["delivered"], [ref])
            self.assertEqual(run("context", "irrelevant", "--required", str(refs_file), "--budget", "1", expected=2)["error"]["code"], "BUDGET_TOO_SMALL")
            value = {"objective": {"text": "Prepare review", "origin": "user_assertion", "refs": []},
                     "constraints": [], "decisions": [{"text": item["text"], "origin": "source_evidence", "refs": [ref]}],
                     "questions": [], "next_actions": []}
            card_file = base / "card.json"; card_file.write_text(json.dumps(value))
            self.assertEqual(run("task-checkpoint", "release", "--card", str(card_file))["status"], "checkpointed")
            self.assertEqual(run("task-resume", "release")["card"], value)
            run("lifecycle", ingested["source_id"], "--action", "revoke")
            resumed = run("task-resume", "release")
            self.assertEqual(resumed["status"], "partial")
            self.assertEqual(resumed["evidence"], [])
            demo = run("demo-k2", "--json")
            self.assertEqual(demo["initial_context"]["items"][0]["revision_id"], demo["first_revision"])
            self.assertEqual(demo["initial_context"]["items"][0]["text"], "# Fictional rollout\n\nRollback uses the amber snapshot.")
            self.assertEqual(demo["initial_context"]["items"][0]["locator"],
                             {"label": "lines 1-3", "line_start": 1, "line_end": 3})
            self.assertEqual(demo["initial_context_validation_after_update"], "changed")
            self.assertEqual(demo["prior_revision_lifecycle"], "superseded")
            self.assertEqual(len(demo["after_revocation"]["items"]), 1)
            self.assertEqual(demo["after_revocation"]["items"][0]["revision_id"], demo["current_revision"])
            self.assertEqual(demo["resume"]["status"], "partial")
            self.assertEqual(demo["required_revoked"]["error"]["code"], "REQUIRED_EVIDENCE_MISSING")

    def test_offline_lifecycle_and_demo_in_real_subprocesses(self):
        scratch = Path(__file__).resolve().parents[1] / ".scratch"
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            base = Path(directory)
            db = base / "index.sqlite3"
            path = base / "guide.md"
            path.write_text("# Test\n\nrollback by restoring the synthetic snapshot\n")
            def run(*args, expected=0):
                result = subprocess.run([sys.executable, "-m", "kre", "--db", str(db), *args], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                return result
            self.assertTrue(json.loads(run("init").stdout)["fts5"])
            ingested = json.loads(run("ingest", str(path), "--root", str(base)).stdout)["files"][0]
            response = json.loads(run("context", "rollback").stdout)
            self.assertEqual(response["items"][0]["source_id"], ingested["source_id"])
            self.assertIn("snapshot", run("search", "rollback").stdout)
            inspect = json.loads(run("inspect", ingested["revision_id"]).stdout)
            self.assertIn("rollback", inspect["text"])
            run("lifecycle", ingested["source_id"], "--action", "revoke")
            self.assertEqual(json.loads(run("context", "rollback", "--historical").stdout)["items"], [])
            self.assertIn("No model or network call", run("demo").stdout)
            self.assertEqual(len(json.loads(run("status").stdout)["sources"]), 2)
            run("context", "rollback", "--budget", "0", expected=2)
            request = base / "request.json"
            request.write_text('{"contract_version":"99"}')
            run("context", "--request", str(request), expected=2)


if __name__ == "__main__":
    unittest.main()
