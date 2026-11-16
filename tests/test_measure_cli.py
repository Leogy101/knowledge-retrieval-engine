"""Exercise the public measurement entry point without inventory/network access."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from kre.quality import rubric_hash

PACKAGE = "kre"


class MeasurementCLITests(unittest.TestCase):
    def test_score_dispatch_does_not_open_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rubric = {"format": "task-quality-rubric/1", "task_id": "cli-fixture",
                      "task_sha256": hashlib.sha256(b"fixture question").hexdigest(),
                      "criteria": [{"id": "answer", "category": "correctness", "critical": True,
                                    "method": "exact", "path": [], "expected": {"value": 42}}]}
            observation = {"format": "task-quality-observation/1", "task_id": rubric["task_id"],
                           "task_sha256": rubric["task_sha256"], "rubric_sha256": rubric_hash(rubric),
                           "completion": "completed", "answer": {"value": 42}}
            (root / "rubric.json").write_text(json.dumps(rubric))
            (root / "observation.json").write_text(json.dumps(observation))
            for prefix in ([], ["--db", str(root / "must-not-open.db")]):
                result = subprocess.run([sys.executable, "-B", "-m", PACKAGE, *prefix, "measure", "score",
                                         str(root / "rubric.json"), str(root / "observation.json")],
                                        cwd=root, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(json.loads(result.stdout)["quality_pass"])
                self.assertFalse((root / "must-not-open.db").exists())
                self.assertFalse((root / ".kre").exists())
                self.assertFalse((root / "gcb.sqlite3").exists())

    def test_bad_measurement_does_not_echo_private_content_or_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private = root / "PRIVATE_PATH_CANARY.json"
            private.write_text('{"private":"PRIVATE_BODY_CANARY", "private":1}')
            result = subprocess.run([sys.executable, "-B", "-m", PACKAGE, "measure", "summarize", str(private)],
                                    cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("PRIVATE_", result.stdout + result.stderr)
            self.assertNotIn(str(root), result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_measure_help_names_only_offline_operations(self):
        result = subprocess.run([sys.executable, "-B", "-m", PACKAGE, "measure", "--help"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        for word in ("summarize", "compare", "score"):
            self.assertIn(word, result.stdout)

    def test_raw_output_check_is_offline_and_fails_without_echoing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            text = 'The fictional answer is amber.\n'
            digest = hashlib.sha256(text.encode()).hexdigest()
            rubric = {'format': 'task-quality-rubric/1', 'task_id': 'cli-output', 'task_sha256': 'a'*64,
                      'criteria': [{'id': 'status', 'category': 'correctness', 'critical': True,
                                    'method': 'exact', 'path': ['status'], 'expected': 'answered'}],
                      'sources': {'manual': {'sha256': digest, 'eligible': True}},
                      'citations': {'require_any': True, 'required_claims': []}}
            evidence = [{'source_id': 'manual', 'source_sha256': digest, 'line_start': 1, 'line_end': 1}]
            for name, value in [('rubric', rubric), ('sources', {'manual': text}), ('evidence', evidence)]:
                (root/(name+'.json')).write_text(json.dumps(value))
            answer = {'status': 'answered', 'answer': 'The answer is amber.',
                      'citations': [{'source_id': 'manual', 'line_start': 1, 'line_end': 1, 'quote': 'The fictional answer is amber.'}]}
            base = [sys.executable, '-B', '-m', PACKAGE, '--db', str(root/'not-opened.db'), 'measure', 'check-output',
                    str(root/'answer.txt'), str(root/'rubric.json'), '--sources', str(root/'sources.json'),
                    '--evidence', str(root/'evidence.json')]
            for raw, expected in ((json.dumps(answer), 0), ('```json\nPRIVATE_CANARY\n```', 1),
                                  (json.dumps(dict(answer, status='insufficient_evidence')), 1)):
                (root/'answer.txt').write_text(raw)
                result = subprocess.run(base, cwd=root, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertNotIn('PRIVATE_CANARY', result.stdout+result.stderr)
                self.assertNotIn('The fictional answer', result.stdout+result.stderr)
                check = json.loads(result.stdout)
                self.assertIsNot(check['end_to_end_quality_pass'], True)
            self.assertFalse((root/'not-opened.db').exists())
            self.assertFalse((root/'.kre').exists())


if __name__ == "__main__":
    unittest.main()
