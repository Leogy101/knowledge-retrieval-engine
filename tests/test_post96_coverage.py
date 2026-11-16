"""Known post-96 retrieval failures remain an offline, source-exact regression.

These are diagnostic regression cases, not fresh held-out quality evidence.
No model is loaded and no inference is performed.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('post96_suite', ROOT / 'scripts/large_suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)
FROZEN_HASH = '31b82cd9480ce16a3b394fcbbd78eda994fb6731ff3509c70acea887d84acb8d'
ORIGINAL_MISSES = {'LS02', 'LS04', 'LS05', 'LS06', 'LS22', 'LS23', 'LS24'}


def evidence_groups(task, supplied):
    def covered(span):
        positions = set()
        for ref in supplied:
            if ref['source_id'] == span['source_id'] and ref['source_sha256'] == span['source_sha256']:
                positions.update(range(max(span['line_start'], ref['line_start']),
                                       min(span['line_end'], ref['line_end']) + 1))
        return set(range(span['line_start'], span['line_end'] + 1)) <= positions
    groups = task.get('evidence_groups') or [
        {'alternatives': [{'spans': [span]}]} for span in task['required_evidence']]
    return [any(all(covered(span) for span in alternative['spans'])
                for alternative in group['alternatives']) for group in groups]


class Post96CoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents, cls.tasks, cls.sources = suite.load_fixture()
        cls.protocol = suite.read(suite.FIXTURE / 'protocol.json')
        cls.contexts = {}
        store = suite.make_store(cls.documents, cls.sources)
        baseline = suite.WindowBaseline(cls.documents, cls.sources)
        try:
            with patch('socket.socket', side_effect=AssertionError('No network in retrieval regression')):
                for task in cls.tasks:
                    cls.contexts[task['id']] = suite.contexts(
                        task, cls.documents, cls.sources, store, baseline, cls.protocol)
        finally:
            store.close()
            baseline.close()

    def test_frozen_fixture_and_baseline_remain_unchanged(self):
        self.assertEqual(hashlib.sha256((suite.FIXTURE / 'freeze.json').read_bytes()).hexdigest(), FROZEN_HASH)
        self.assertEqual(len(self.tasks), 24)
        self.assertEqual(self.protocol['selection_budget'], {'max_bytes': 16000, 'max_items': 16})
        baseline = [value for task in self.tasks for value in evidence_groups(
            task, self.contexts[task['id']]['disabled']['evidence'])]
        self.assertEqual((sum(baseline), len(baseline)), (60, 63))

    def test_all_63_groups_including_seven_original_failures_are_supplied(self):
        outcomes = {}
        for task in self.tasks:
            outcomes[task['id']] = evidence_groups(task, self.contexts[task['id']]['enabled']['evidence'])
            with self.subTest(task=task['id']):
                self.assertTrue(all(outcomes[task['id']]))
        self.assertEqual((sum(map(sum, outcomes.values())), sum(map(len, outcomes.values()))), (63, 63))
        self.assertTrue(ORIGINAL_MISSES <= outcomes.keys())
        self.assertTrue(all(all(outcomes[task]) for task in ORIGINAL_MISSES))

    def test_exact_current_citations_policies_and_original_budgets(self):
        documents = {doc['id']: doc for doc in self.documents}
        for task in self.tasks:
            with self.subTest(task=task['id']):
                pair = self.contexts[task['id']]
                context = pair['enabled']
                self.assertEqual(pair['disabled']['messages'][1], context['messages'][1])
                self.assertEqual(context['details']['validation'], 'current')
                self.assertIsNone(context['details']['native_error'])
                self.assertLessEqual(context['details']['native_context_bytes'], 16000)
                self.assertLessEqual(context['context_bytes'], 16000)
                self.assertLessEqual(len(context['evidence']), 16)
                packets = json.loads(context['messages'][0]['content'][len(suite.PREFIX):-len(suite.SUFFIX)])
                self.assertEqual(suite.evidence(packets), context['evidence'])
                for item in packets:
                    doc = documents[item['source_id']]
                    self.assertTrue(suite.eligible(doc, task['scope']))
                    expected = '\n'.join(self.sources[doc['id']].split('\n')[item['line_start']-1:item['line_end']])
                    self.assertEqual(item['text'], expected)
                    self.assertEqual(item['source_sha256'], doc['sha256'])
                    self.assertEqual(item['content_sha256'], hashlib.sha256(expected.encode()).hexdigest())
                    for key, source_key in [('lifecycle', 'status'), ('freshness', 'freshness'),
                                             ('authority', 'authority'), ('origin', 'origin')]:
                        self.assertEqual(item[key], doc[source_key])


if __name__ == '__main__':
    unittest.main()
