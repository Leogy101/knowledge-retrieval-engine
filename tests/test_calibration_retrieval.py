"""Public synthetic K1 regression; original private calibration stays unchanged."""
import copy
import hashlib
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from kre import Store, evidence_ref

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / 'tests/fixtures/calibration'
QUERY = ('Which tools does KRE expose by default, and can those tools ingest a new '
         'document? If not, identify the documented source-management interface.')
FILES = (
    ('pilot-kre-mcp', 'kre-mcp.md', '04d5294dfdd23b5c153278c1f622193e78c29e3d3ccf633fb482b14fcb3d5a43'),
    ('pilot-gcb-mcp', 'gcb-mcp.md', 'bd8661404b69e9bf04964236914e8dd34e16ee22cc7c3abb78e6e653f1d7b165'),
    ('pilot-kre-security', 'kre-security.md', '92ed853b905320fb67e0b401521c7aa75f0b248348f7c3883312bca999bc2a48'),
)


def request(query=QUERY):
    return {'contract_version': '0.1', 'request_id': 'local-k1', 'query': query,
            'access_scope_ref': 'approved', 'destination': 'local_only',
            'purpose': 'current_answer', 'freshness_requirement': 'allow_unknown',
            'budget': {'max_tokens': 8000, 'max_bytes': 8000, 'max_items': 5}}


def coverage(context):
    return {line for line in (11, 13) if any(
        item['source_id'] == 'pilot-kre-mcp'
        and item['locator']['line_start'] <= line <= item['locator']['line_end']
        for item in context['items'])}


class CalibrationRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:', principal='local-calibration',
                           scopes={'approved': {'approved-docs'}})
        self.addCleanup(self.store.close)
        self.originals = {}
        for source, filename, digest in FILES:
            raw = (CORPUS / filename).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
            self.originals[source] = raw.decode('utf-8')
            self.store.ingest_text(source, self.originals[source], collection='approved-docs')

    def test_exact_frozen_failure_and_corrected_evidence_with_same_budget(self):
        req = request()
        original = copy.deepcopy(req)
        # Re-enable just the original lexical query, keeping all other stages
        # identical. This must continue to expose the original missed passages.
        with patch('kre.store._query_terms', lambda q: list(dict.fromkeys(re.findall(r'\w+', q)))):
            before = self.store.context(req)
        self.assertEqual(coverage(before), set())
        self.assertEqual(before['token_usage']['context_bytes'], 4470)
        after = self.store.context(req)
        self.assertEqual(coverage(after), {11, 13})
        self.assertEqual(req, original)
        self.assertLessEqual(after['token_usage']['context_bytes'], 8000)
        self.assertLessEqual(len(after['items']), 5)
        self.assertEqual(after['context_text'], Store._render(after['items']))
        self.assertEqual(self.store.validate_context(after, scope_ref='approved', destination='local_only'), 'current')
        for item in after['items']:
            loc = item['locator']
            exact = '\n'.join(self.originals[item['source_id']].split('\n')[loc['line_start']-1:loc['line_end']])
            self.assertEqual(item['text'], exact)
            self.assertEqual(item['content_sha256'], hashlib.sha256(exact.encode()).hexdigest())

    def test_related_multi_part_questions_preserve_both_passages(self):
        for query in (
            'What is the default tool surface and the source management interface?',
            'Which default tools retrieve and validate evidence, and how is source management performed?',
            'Does the default tool surface support ingestion, and which CLI manages sources?',
        ):
            with self.subTest(query=query):
                self.assertEqual(coverage(self.store.context(request(query))), {11, 13})

    def test_item_cutoff_is_reported_without_claiming_answer_sufficiency(self):
        context = self.store.context(request())
        self.assertEqual(context['status'], 'partial')
        self.assertEqual(context['coverage'], 'partial')
        self.assertGreater(context['omissions']['item_limit'], 0)
        self.assertNotIn('budget', context['omissions'])

    def test_required_evidence_missing_or_unfit_never_becomes_partial_success(self):
        context = self.store.context(request())
        refs = [evidence_ref(item) for item in context['items']
                if item['source_id'] == 'pilot-kre-mcp' and item['locator']['line_start'] in (11, 13)]
        tiny = request()
        tiny['budget']['max_items'] = 1
        self.assertEqual(self.store.context_required(tiny, required_refs=refs)['error']['code'], 'BUDGET_TOO_SMALL')
        self.store.revoke('pilot-kre-mcp')
        result = self.store.context_required(request(), required_refs=refs)
        self.assertEqual(result['error']['code'], 'REQUIRED_EVIDENCE_MISSING')
        self.assertEqual(result['context']['items'], [])
        self.assertEqual(len(result['required']['missing']), 2)

    def test_literal_function_word_and_negation_queries_remain_searchable(self):
        for query in ('if', 'not'):
            with self.subTest(query=query):
                self.assertTrue(self.store.context(request(query))['items'])
        absent = self.store.context(request('Where is zephyrquartz?'))
        self.assertEqual(absent['items'], [])
        self.assertIn('NO_EVIDENCE', absent['warnings'])
        self.assertEqual(absent['coverage'], 'unknown')

    def test_capitalized_names_and_acronyms_are_not_discarded(self):
        with Store(':memory:', principal='test', scopes={'approved': {'notes'}}) as store:
            for source, text in (
                ('june', 'June access code is amber.'),
                ('will', 'Will access code is blue.'),
                ('hr', 'HR access code is green.'),
                ('it', 'IT access code is silver.'),
            ):
                store.ingest_text(source, text, collection='notes')
            for name, source in (('Will', 'will'), ('IT', 'it')):
                req = request(name + ' access code')
                req['budget']['max_items'] = 1
                self.assertEqual([item['source_id'] for item in store.context(req)['items']], [source])


if __name__ == '__main__':
    unittest.main()
