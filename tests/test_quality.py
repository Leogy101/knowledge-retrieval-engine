"""Synthetic frozen quality checks; no live sources or model judge."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from kre.quality import QualityError, answer_hash, citation_hash, rubric_hash, score_trial, strict_loads


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.text = 'The fictional package exposes fetch and validate.\nIngestion uses the owner CLI.\n'
        self.source_hash = hashlib.sha256(self.text.encode()).hexdigest()
        self.sources = {'manual': self.text}
        self.span = {'source_id': 'manual', 'source_sha256': self.source_hash,
                     'line_start': 1, 'line_end': 2}
        self.rubric = {
            'format': 'task-quality-rubric/1', 'task_id': 'synthetic-quality-1', 'task_sha256': 'a' * 64,
            'criteria': [
                {'id': 'facts', 'category': 'facts', 'critical': True, 'method': 'exact',
                 'path': ['tools'], 'expected': ['fetch', 'validate']},
                {'id': 'constraint', 'category': 'constraints', 'critical': True, 'method': 'exact',
                 'path': ['changed_system'], 'expected': False},
                {'id': 'semantic', 'category': 'correctness', 'critical': True, 'method': 'review',
                 'expectation': 'The answer states both documented tools and contains no unsupported material claim.'},
            ],
            'sources': {'manual': {'sha256': self.source_hash, 'eligible': True}},
            'citations': {'require_any': True, 'required_claims': ['tools']},
            'required_evidence': [self.span],
        }
        self.observation = {
            'format': 'task-quality-observation/1', 'task_id': 'synthetic-quality-1',
            'task_sha256': 'a' * 64, 'rubric_sha256': rubric_hash(self.rubric),
            'completion': 'completed',
            'answer': {'tools': ['fetch', 'validate'], 'changed_system': False},
            'citations': [dict(self.span, line_end=1, claim_id='tools', quote='exposes fetch and validate')],
            'evidence': [self.span], 'errors': 0, 'recovery': 'not_needed', 'unnecessary_information': 0,
        }
        self.attest()

    def attest(self, semantic=True, support=True, independent=True):
        review = {'verdict': semantic, 'independent': independent,
                  'reviewer_ref': 'blind-human-1', 'answer_sha256': answer_hash(self.observation['answer'])}
        self.observation['reviews'] = [dict(review, criterion_id='semantic')]
        self.observation['citation_reviews'] = [dict(review, verdict=support, citation_index=0,
                                                   citation_sha256=citation_hash(self.observation['citations'][0]))]

    def score(self):
        return score_trial(self.rubric, self.observation, self.sources)

    def test_frozen_pass_is_reproducible(self):
        before = copy.deepcopy((self.rubric, self.observation, self.sources))
        result = self.score()
        self.assertEqual(result, self.score())
        self.assertEqual(before, (self.rubric, self.observation, self.sources))
        self.assertTrue(result['quality_pass'])
        self.assertEqual(result['citation_exactness']['score'], 1)
        self.assertEqual(result['citation_support']['score'], 1)
        self.assertEqual(result['evidence_recall']['score'], 1)
        self.assertEqual(result['answer_sha256'], answer_hash(self.observation['answer']))

    def test_missing_critical_fact_fails(self):
        original_answer_hash = self.score()['answer_sha256']
        self.observation['answer']['tools'] = ['fetch']
        self.attest()
        result = self.score()
        self.assertFalse(result['critical_pass'])
        self.assertFalse(result['quality_pass'])
        self.assertNotEqual(result['answer_sha256'], original_answer_hash)

    def test_exact_matching_preserves_bool_integer_and_float_types(self):
        for value in (0, 0.0, 'false', None):
            with self.subTest(value=value):
                self.observation['answer']['changed_system'] = value
                self.attest()
                self.assertFalse(self.score()['critical_pass'])

    def test_review_is_unknown_not_automatic_semantic_match(self):
        self.observation['reviews'] = []
        result = self.score()
        self.assertIsNone(result['quality_pass'])
        self.assertEqual(result['criteria']['correctness']['unknown'], 1)

    def test_review_expected_standard_is_frozen_and_required(self):
        initial = rubric_hash(self.rubric)
        criterion = self.rubric['criteria'][2]
        criterion['expectation'] = 'A different human evaluation standard.'
        self.assertNotEqual(rubric_hash(self.rubric), initial)
        with self.assertRaises(QualityError):
            self.score()
        for value in (None, '', '  ', 1):
            criterion['expectation'] = value
            with self.assertRaises(QualityError):
                rubric_hash(self.rubric)
        criterion.pop('expectation')
        with self.assertRaises(QualityError):
            rubric_hash(self.rubric)

    def test_nonindependent_review_stays_unknown(self):
        self.attest(independent=False)
        self.assertIsNone(self.score()['critical_pass'])

    def test_old_answer_or_citation_review_is_rejected(self):
        self.observation['answer']['tools'] = ['fetch']
        with self.assertRaises(QualityError):
            self.score()
        self.attest()
        self.observation['citations'][0]['quote'] = 'validate'
        with self.assertRaises(QualityError):
            self.score()

    def test_wrong_source_hash_line_and_quote_fail_exactness(self):
        original = copy.deepcopy(self.observation)
        for change in ({'source_id': 'other'}, {'source_sha256': 'b' * 64},
                       {'line_start': 2, 'line_end': 2}, {'quote': 'imaginary quote'}):
            with self.subTest(change=change):
                self.observation = copy.deepcopy(original)
                self.observation['citations'][0].update(change)
                self.attest()
                self.assertEqual(self.score()['citation_exactness']['score'], 0)
                self.assertFalse(self.score()['critical_pass'])

    def test_exact_but_irrelevant_citation_fails_support(self):
        self.attest(support=False)
        result = self.score()
        self.assertEqual(result['citation_exactness']['score'], 1)
        self.assertEqual(result['citation_support']['score'], 0)
        self.assertFalse(result['quality_pass'])

    def test_required_claim_missing_even_with_other_valid_citation(self):
        self.observation['citations'][0]['claim_id'] = 'other'
        self.attest()
        self.assertFalse(self.score()['critical_pass'])

    def test_missing_citations_are_unknown_but_empty_required_list_fails(self):
        self.observation.pop('citations')
        self.observation['citation_reviews'] = []
        self.assertIsNone(self.score()['quality_pass'])
        self.observation['citations'] = []
        self.assertFalse(self.score()['quality_pass'])

    def test_wrong_source_snapshot_fails_and_unavailable_snapshot_unknown(self):
        result = score_trial(self.rubric, self.observation, {'manual': self.text + 'tampered'})
        self.assertFalse(result['quality_pass'])
        result = score_trial(self.rubric, self.observation)
        self.assertIsNone(result['quality_pass'])

    def test_frozen_ineligible_source_cannot_pass_quote_check(self):
        self.rubric['sources']['manual']['eligible'] = False
        self.rubric['required_evidence'] = []
        self.observation['rubric_sha256'] = rubric_hash(self.rubric)
        self.assertFalse(self.score()['critical_pass'])

    def test_required_evidence_coverage_is_not_inferred_from_final_citation(self):
        self.observation['evidence'] = []
        result = self.score()
        self.assertEqual(result['evidence_recall']['score'], 0)
        self.assertFalse(result['quality_pass'])
        self.observation.pop('evidence')
        self.assertIsNone(self.score()['evidence_recall']['score'])

    def test_evidence_spans_can_jointly_cover_a_required_span(self):
        self.observation['evidence'] = [dict(self.span, line_end=1), dict(self.span, line_start=2)]
        self.assertEqual(self.score()['evidence_recall']['score'], 1)

    def test_invalid_extra_evidence_cannot_hide_behind_empty_gold(self):
        self.rubric['required_evidence'] = []
        self.observation['rubric_sha256'] = rubric_hash(self.rubric)
        self.observation['evidence'].append(dict(self.span, source_id='outside-scope'))
        result = self.score()
        self.assertIsNone(result['evidence_recall']['score'])
        self.assertEqual(result['evidence_validity']['score'], 0.5)
        self.assertFalse(result['critical_pass'])

    def test_documented_fixtures_reproduce_expected_scores(self):
        directory = Path(__file__).resolve().parents[1] / 'docs/examples/efficiency'
        read = lambda name: strict_loads((directory / name).read_text())
        rubric, sources = read('quality-rubric.json'), read('sources.json')
        for name in ('pass', 'missing'):
            actual = score_trial(rubric, read('quality-' + name + '.json'), sources)
            self.assertEqual(actual, read('quality-' + name + '-score.json'))

    def test_absent_gold_has_null_recall_and_citation_denominator(self):
        rubric = {'format': 'task-quality-rubric/1', 'task_id': 'absent', 'task_sha256': 'c' * 64,
                  'criteria': [{'id': 'abstain', 'category': 'missing_evidence', 'critical': True,
                                'method': 'exact', 'path': [], 'expected': {'status': 'insufficient_evidence'}}],
                  'citations': {'require_any': False, 'required_claims': []}, 'required_evidence': []}
        observation = {'format': 'task-quality-observation/1', 'task_id': 'absent', 'task_sha256': 'c' * 64,
                       'rubric_sha256': rubric_hash(rubric), 'completion': 'completed',
                       'answer': {'status': 'insufficient_evidence'}, 'citations': [], 'evidence': []}
        result = score_trial(rubric, observation)
        self.assertTrue(result['quality_pass'])
        self.assertIsNone(result['evidence_recall']['score'])
        self.assertIsNone(result['citation_exactness']['score'])

    def test_incomplete_cancelled_and_unknown_completion(self):
        for completion in ('incomplete', 'cancelled', 'error', 'unknown'):
            self.observation['completion'] = completion
            result = self.score()
            self.assertIsNone(result['quality_pass']) if completion == 'unknown' else self.assertFalse(result['quality_pass'])

    def test_unnecessary_information_and_unrecovered_error_remain_visible(self):
        self.observation['unnecessary_information'] = 2
        result = self.score()
        self.assertFalse(result['quality_pass'])
        self.assertTrue(result['critical_pass'])
        self.assertEqual(result['unnecessary_information'], 2)
        self.observation['unnecessary_information'] = 0
        self.observation['errors'] = 1
        self.observation['recovery'] = 'recovered'
        self.assertTrue(self.score()['quality_pass'])
        self.observation['recovery'] = 'unrecovered'
        self.assertFalse(self.score()['critical_pass'])

    def test_identity_and_rubric_mutation_rejected(self):
        for key in ('task_id', 'task_sha256', 'rubric_sha256'):
            original = self.observation[key]
            self.observation[key] = 'different'
            with self.assertRaises(QualityError):
                self.score()
            self.observation[key] = original
        self.rubric['criteria'][0]['expected'] = ['changed']
        with self.assertRaises(QualityError):
            self.score()

    def test_duplicate_attestations_and_invalid_counts_rejected(self):
        self.observation['reviews'] *= 2
        with self.assertRaises(QualityError):
            self.score()
        self.attest()
        for value in (True, -1, 1.5, '1'):
            self.observation['errors'] = value
            with self.assertRaises(QualityError):
                self.score()

    def test_private_content_and_reviewer_identity_not_exported(self):
        secret = 'PRIVATE-content-sentinel-9f'
        self.observation['answer']['private'] = secret
        self.attest()
        self.observation['reviews'][0]['reviewer_ref'] = 'private-reviewer-name'
        output = json.dumps(self.score())
        for value in (secret, 'private-reviewer-name', self.text, 'exposes fetch and validate'):
            self.assertNotIn(value, output)
        self.observation['private_path'] = '/Users/private-secret'
        with self.assertRaises(QualityError) as caught:
            self.score()
        self.assertNotIn('private-secret', str(caught.exception))

    def test_strict_json_rejects_duplicate_nonfinite_depth_and_large_input(self):
        for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '[' * 40 + '0' + ']' * 40,
                     '"' + 'a' * (2 * 1024 * 1024) + '"'):
            with self.subTest(text=text[:30]), self.assertRaises(QualityError):
                strict_loads(text)
        self.assertEqual(strict_loads('{"ok":1}'), {'ok': 1})

    def test_exact_quotes_do_not_normalize_line_endings(self):
        text = self.text.replace('\n', '\r\n')
        digest = hashlib.sha256(text.encode()).hexdigest()
        self.sources['manual'] = text
        self.rubric['sources']['manual']['sha256'] = digest
        self.rubric['required_evidence'][0]['source_sha256'] = digest
        self.observation['evidence'][0]['source_sha256'] = digest
        self.observation['citations'][0].update(source_sha256=digest, line_end=2,
                                             quote='validate.\nIngestion')
        self.observation['rubric_sha256'] = rubric_hash(self.rubric)
        self.attest()
        self.assertEqual(self.score()['citation_exactness']['score'], 0)

    def test_no_source_file_access_or_empty_rubric_shortcut(self):
        self.rubric['sources']['manual']['path'] = '/must/not/read'
        with self.assertRaises(QualityError):
            self.score()
        rubric = {'format': 'task-quality-rubric/1', 'task_id': 'empty', 'task_sha256': 'a' * 64, 'criteria': []}
        with self.assertRaises(QualityError):
            rubric_hash(rubric)
        rubric['citations'] = {'require_any': False, 'required_claims': []}
        with self.assertRaises(QualityError):
            rubric_hash(rubric)

    def test_unrequested_wrong_citation_cannot_escape_quality_gate(self):
        del self.rubric['citations']
        self.observation['rubric_sha256'] = rubric_hash(self.rubric)
        self.observation['citations'][0]['source_id'] = 'unknown-source'
        self.attest()
        result = self.score()
        self.assertEqual(result['citation_exactness']['score'], 0)
        self.assertFalse(result['critical_pass'])

    def test_missing_answer_cannot_pass_a_citation_only_rubric(self):
        self.rubric['criteria'] = []
        self.observation['rubric_sha256'] = rubric_hash(self.rubric)
        del self.observation['answer']
        self.observation['reviews'] = []
        self.observation['citation_reviews'] = []
        self.assertIsNone(self.score()['quality_pass'])


if __name__ == '__main__':
    unittest.main()
