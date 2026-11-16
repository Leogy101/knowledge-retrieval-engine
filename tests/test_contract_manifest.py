"""Shared contract fixtures remain stable without installing the companion."""
import hashlib
import json
from pathlib import Path
import unittest
from kre import Store

CONTRACT = Path(__file__).resolve().parents[1] / 'contracts/context/0.1'

class InteroperabilityTests(unittest.TestCase):
    def test_shared_schema_and_fixture_hashes(self):
        for line in (CONTRACT / 'MANIFEST.sha256').read_text().splitlines():
            digest, name = line.split()
            self.assertEqual(hashlib.sha256((CONTRACT / name).read_bytes()).hexdigest(), digest)

    def test_shared_request_supported_without_companion(self):
        req = json.loads((CONTRACT / 'fixtures/request.json').read_text())
        schema = json.loads((CONTRACT / 'context.response.schema.json').read_text())
        with Store(':memory:', principal='fixture-owner', scopes={'demo-read': {'demo'}}) as store:
            store.ingest_text('release-notes', 'Rollback requires the previous snapshot.', collection='demo')
            result = store.context(req)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(set(result), set(schema['required']))
            self.assertEqual(result['contract_version'], '0.1')
            self.assertEqual(result['coverage'], 'unknown')
            for item in result['items']:
                self.assertEqual(set(item), set(schema['$defs']['item']['required']))
            self.assertEqual(store.validate_context(result, scope_ref='demo-read', destination='local_only'), 'current')
            req['model_provider'] = 'untrusted-extra-field'
            rejected = store.context(req)
            self.assertEqual(rejected['error']['code'], 'INVALID_REQUEST')
            self.assertEqual(rejected['items'], [])
