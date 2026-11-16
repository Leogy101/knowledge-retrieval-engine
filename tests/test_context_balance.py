"""Frozen fragmented-evidence regressions, separate from generated answer quality."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from kre import Store
from kre.ingestion import chunks

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'evaluation/context-balance-v1'
FIXTURE = STUDY / 'heldout/fragmented-evidence-v2.frozen.json'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextBalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())
        cls.sources = {s['source_id']: s for s in cls.fixture['sources']}
        cls.responses = {}
        with Store(':memory:', principal='offline-test',
                   scopes={'reader': {'public'}, 'owner': {'public', 'private'}},
                   destinations=frozenset({'local_only', 'approved_remote'})) as store:
            for source in cls.sources.values():
                store.ingest_text(source['source_id'], source['text'], collection=source['collection'],
                                  freshness={'current': 'fresh', 'stale': 'stale'}[source['freshness']],
                                  authority='authoritative' if source['authority'] == 'primary' else 'unverified',
                                  origin='source_evidence',
                                  egress='approved_remote' if 'public' in source['allowed_destinations'] else 'local_only',
                                  _display_uri=source['origin'])
                if source['state'] in {'revoked', 'superseded'}:
                    store.lifecycle(source['source_id'], {'revoked': 'revoke', 'superseded': 'supersede'}[source['state']])
            with patch('socket.socket', side_effect=AssertionError('No network in offline regression')):
                for case in cls.fixture['cases']:
                    req = {'contract_version': '0.1', 'request_id': case['id'], 'query': case['query'],
                           'access_scope_ref': case['scope'], 'purpose': 'current_answer',
                           'destination': {'public': 'approved_remote', 'local': 'local_only'}[case['destination']],
                           'budget': case['budget']}
                    result = store.context(req)
                    cls.responses[case['id']] = (result, store.validate_context(result, scope_ref=case['scope'], destination=req['destination']))
                explicit = dict(req, query='visitor planting tips', access_scope_ref='reader',
                                destination='approved_remote', source_ids=['seed-tips'])
                cls.unverified = store.context(explicit)

    def test_frozen_algorithm_fixture_and_author_mapping_identity(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), '40c653a4d5a6f745f18444385cb872450259dd8ca41ad889ab2d4c292845fa2f')
        mapping = STUDY / 'heldout/fragmented-evidence-v2.native-mapping.json'
        self.assertEqual(hashlib.sha256(mapping.read_bytes()).hexdigest(), 'e5cfbc89c3ad8cb44b10f725d6e226e0e1f0fc2854c1173219ad0bdbc2049c1c')
        lock = json.loads((STUDY / 'EXPERIMENT_LOCK.json').read_text())
        for name, expected in lock['files'].items():
            self.assertEqual(hashlib.sha256((STUDY / name).read_bytes()).hexdigest(), expected)
        for source in self.sources.values():
            self.assertEqual(hashlib.sha256(source['text'].encode()).hexdigest(), source['sha256'])
        for case in self.fixture['cases']:
            for gold in case['gold']:
                self.assertEqual(gold['quote'], '\n'.join(self.sources[gold['source_id']]['text'].split('\n')[gold['line_start']-1:gold['line_end']]))

    def test_fixture_really_exercises_changed_chunk_boundaries(self):
        legacy = load(STUDY / 'legacy_ingestion.py', 'context_balance_legacy')
        changed = [s for s in self.sources.values() if chunks(s['text']) != legacy.chunks(s['text'])]
        self.assertEqual(len(changed), 18)
        self.assertTrue(all(len(s['text'].encode()) <= 1200 and len(chunks(s['text'])) == 1 for s in changed))
        self.assertTrue(any(len(s['text'].encode()) > 1200 for s in self.sources.values()))

    def test_exact_citations_supported_policies_and_budget_accounting(self):
        for case in self.fixture['cases']:
            with self.subTest(case=case['id']):
                result, validity = self.responses[case['id']]
                if result['error']:
                    self.assertEqual(case['id'], 'fragmented-08')
                    self.assertEqual(result['error']['code'], 'DESTINATION_DENIED')
                    self.assertEqual(result['items'], [])
                    continue
                self.assertEqual(validity, 'current')
                size = len(result['context_text'].encode())
                self.assertEqual(size, result['token_usage']['context_bytes'])
                self.assertEqual(size, result['token_usage']['estimated_tokens'])
                self.assertLessEqual(size, min(case['budget']['max_bytes'], case['budget']['max_tokens']))
                self.assertLessEqual(len(result['items']), case['budget']['max_items'])
                for item in result['items']:
                    source = self.sources[item['source_id']]
                    self.assertIn(source['state'], {'active', 'reference_only'})
                    self.assertNotEqual(source['freshness'], 'stale')
                    self.assertIn(case['destination'], source['allowed_destinations'])
                    self.assertIn(source['collection'], self.fixture['access_policy'][case['scope']])
                    self.assertEqual(item['text'], '\n'.join(source['text'].split('\n')[item['locator']['line_start']-1:item['locator']['line_end']]))
                    self.assertEqual(item['content_sha256'], hashlib.sha256(item['text'].encode()).hexdigest())

    def test_previously_supplied_gold_is_not_lost_but_improvement_is_allowed(self):
        first = json.loads((ROOT / 'tests/fixtures/history/fragmented-accepted-gold.json').read_text())
        expected = {r['case_id']: r for r in first['cases'] if r['variant'] == 'accepted_89f115c'}
        for case in self.fixture['cases']:
            supplied = self.responses[case['id']][0]['items']
            for gold in expected[case['id']]['gold']:
                if not gold['covered']:
                    continue
                found = set()
                for item in supplied:
                    if item['source_id'] == gold['source_id']:
                        found.update(range(item['locator']['line_start'], item['locator']['line_end']+1))
                self.assertTrue(set(range(gold['line_start'], gold['line_end']+1)) <= found)

    def test_unverified_authority_is_not_fabricated_revocation(self):
        self.assertIsNone(self.unverified['error'])
        self.assertEqual(len(self.unverified['items']), 1)
        item = self.unverified['items'][0]
        self.assertEqual((item['source_id'], item['authority'], item['lifecycle']), ('seed-tips', 'unverified', 'active'))
        self.assertIn('seed-tips', self.fixture['cases'][3]['forbidden_sources'])
        # This author expectation is unsupported as an access rule. It must not
        # be silently injected into source grants or treated as model truth.


if __name__ == '__main__':
    unittest.main()
