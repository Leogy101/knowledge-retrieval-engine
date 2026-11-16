"""Synthetic-only measurement/review tests; none invoke a model or a network."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('large_suite_scoring', ROOT/'scripts/large_suite_scoring.py')
scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scoring)


class LargeSuiteScoringTests(unittest.TestCase):
    def setUp(self):
        self.text = 'The synthetic queue holds 12 jobs.\nOwners release queued jobs.\n'
        digest = hashlib.sha256(self.text.encode()).hexdigest()
        self.sources = {'queue': self.text}
        self.documents = [{'id': 'queue', 'sha256': digest, 'status': 'active', 'freshness': 'fresh'}]
        self.evidence = [{'source_id': 'queue', 'source_sha256': digest, 'line_start': 1, 'line_end': 2}]
        self.task = {'id': 'T01', 'category': 'multi_document', 'scope': 'compact',
                     'question': 'What is the capacity and who releases jobs?',
                     'reference_answer': '12 jobs; owners release them.',
                     'required_facts': [{'id': 'capacity', 'text': '12 jobs'}, {'id': 'owner', 'text': 'Owners release jobs'}],
                     'required_evidence': [dict(self.evidence[0], quote=self.text.rstrip())],
                     'expected_status': 'answered', 'forbidden_claims': ['Anyone may release jobs'],
                     'constraints': ['Do not run a command.']}
        self.answer = {'status': 'answered', 'answer': 'The queue holds 12 jobs; owners release them.',
                       'citations': [{'source_id': 'queue', 'line_start': 1, 'line_end': 2,
                                     'quote': self.text.rstrip()}]}
        self.raw = json.dumps(self.answer)

    def score(self, raw=None, **kwargs):
        return scoring.score_output(self.raw if raw is None else raw, self.task, self.documents,
                                    self.sources, kwargs.get('evidence', self.evidence), 'a'*64)

    def attempt(self, **kwargs):
        return dict({'state': 'completed', 'input_tokens': 100, 'output_tokens': 20,
                     'cached_tokens': 40, 'reasoning_tokens': 5, 'retry': False,
                     'submitted_message_bytes': 500}, **kwargs)

    def record(self, condition, **kwargs):
        return dict({'pair_id': 'pair-1', 'task_id': 'T01', 'category': 'multi_document',
                     'model': 'fictional-small', 'baseline_type': 'complete', 'condition': condition,
                     'attempts': [self.attempt()], 'completion_seconds': 2.0,
                     'retrieval_seconds': 0.001, 'quality_pass': None}, **kwargs)

    def human_review(self, score):
        return {'format': 'large-suite-human-review/1', 'task_id': 'T01',
                'raw_output_sha256': score['raw_output_sha256'], 'reviewer_id': 'human-fixture',
                'human': True, 'independent': True, 'blinded': True,
                'facts': {'capacity': True, 'owner': True}, 'constraints': {'constraint-1': True},
                'citation_support': [True], 'unsupported_claims': [], 'completion_correct': True}

    def test_correct_output_requires_semantic_review(self):
        result = self.score()
        self.assertTrue(result['deterministic_gate'])
        self.assertIsNone(result['overall_quality_pass'])
        self.assertIsNone(result['unsupported_claims'])

    def test_bad_format_is_not_repaired(self):
        for raw in ('```json\n'+self.raw+'\n```', '{"status":', '{"status":"answered","status":"answered"}'):
            with self.subTest(raw=raw):
                result = self.score(raw)
                self.assertFalse(result['json_valid'])
                self.assertFalse(result['overall_quality_pass'])

    def test_bad_quote_or_unseen_span_fails(self):
        bad = copy.deepcopy(self.answer); bad['citations'][0]['quote'] = 'The synthetic... 12 jobs.'
        self.assertFalse(self.score(json.dumps(bad))['deterministic_gate'])
        self.assertFalse(self.score(evidence=[dict(self.evidence[0], line_end=1)])['deterministic_gate'])

    def test_ineligible_source_fails(self):
        self.documents[0]['status'] = 'revoked'
        # Frozen gold citing ineligible material is an invalid task, not a pass.
        with self.assertRaises(scoring.QualityError):
            self.score()

    def test_exact_status_is_scored(self):
        self.answer['status'] = 'insufficient_evidence'
        result = self.score(json.dumps(self.answer))
        self.assertTrue(result['mechanical_gate'])
        self.assertFalse(result['deterministic_gate'])

    def test_missing_evidence_stays_unknown(self):
        result = self.score(evidence=None)
        self.assertIsNone(result['retrieval_evidence_gate'])
        self.assertIsNone(result['overall_quality_pass'])

    def test_abstention_without_required_evidence(self):
        self.task['expected_status'] = 'insufficient_evidence'
        self.task['required_evidence'] = []
        self.task['required_facts'] = []
        raw = json.dumps({'status': 'insufficient_evidence', 'answer': 'The sources do not establish this.', 'citations': []})
        result = self.score(raw, evidence=[])
        self.assertTrue(result['deterministic_gate'])
        self.assertIsNone(result['overall_quality_pass'])

    def test_frozen_evidence_alternatives_keep_canonical_metric_separate(self):
        alternate='The capacity is 12.\n\nOnly owners release jobs.\n'
        digest=hashlib.sha256(alternate.encode()).hexdigest()
        self.sources['alternate']=alternate
        self.documents.append({'id':'alternate','sha256':digest,'status':'active','freshness':'fresh'})
        first={'source_id':'alternate','source_sha256':digest,'line_start':1,'line_end':1,'quote':'The capacity is 12.'}
        second=dict(first,line_start=3,line_end=3,quote='Only owners release jobs.')
        self.task['evidence_groups']=[{'id':'facts','alternatives':[
            {'spans':self.task['required_evidence']},{'spans':[first,second]}]}]
        answer={'status':'answered','answer':'12 jobs; owners release them.',
                'citations':[{'source_id':'alternate','line_start':1,'line_end':1,'quote':'The capacity is 12.'}]}
        raw=json.dumps(answer)
        result=self.score(raw,evidence=[{k:v for k,v in x.items() if k!='quote'} for x in (first,second)])
        self.assertTrue(result['deterministic_gate'])
        self.assertEqual(result['canonical_required_evidence']['passed'],0)
        self.assertEqual(result['required_evidence_groups']['passed'],1)
        partial=self.score(raw,evidence=[{k:v for k,v in first.items() if k!='quote'}])
        self.assertFalse(partial['deterministic_gate'])
        self.assertEqual(partial['required_evidence_groups']['passed'],0)
        answer['citations'][0]['quote']='The capacity ... 12.'
        self.assertFalse(self.score(json.dumps(answer),evidence=[{k:v for k,v in x.items() if k!='quote'} for x in (first,second)])['deterministic_gate'])

    def test_blind_packet_contains_alternatives_and_scope_metadata(self):
        self.task['evidence_groups']=[{'id':'g','alternatives':[{'spans':self.task['required_evidence']}]}]
        self.documents[0]['scope']='compact'
        records=[{'run_id':'r','task_id':'T01','raw_output':self.raw,'model':'hidden','condition':'enabled'}]
        bundle=scoring.make_blind_bundle(records,{'T01':self.task},self.sources,'private-seed-0001',documents=self.documents)
        packet=bundle['public']['packets'][0]
        self.assertEqual(packet['source_metadata'],self.documents)
        self.assertEqual(packet['evidence_groups'],self.task['evidence_groups'])

    def test_no_double_counting_cache_and_reasoning(self):
        totals = scoring.aggregate_attempts([self.attempt(), self.attempt(retry=True)])
        self.assertEqual(totals['total_tokens']['value'], 240)
        self.assertEqual(totals['cached_tokens']['value'], 80)
        self.assertEqual(totals['reasoning_tokens']['value'], 10)
        self.assertEqual(totals['model_requests'], 2)
        self.assertEqual(totals['retry_count'], 1)
        self.assertEqual(totals['submitted_message_bytes']['value'], 1000)

    def test_missing_usage_not_zero(self):
        totals = scoring.aggregate_attempts([self.attempt(), self.attempt(output_tokens=None, state='failed')])
        self.assertIsNone(totals['total_tokens']['value'])
        self.assertEqual(totals['total_tokens']['known_sum'], 120)
        self.assertEqual(totals['total_tokens']['coverage'], 'partially_measured')
        self.assertIsNone(totals['billed_charge']['value'])
        self.assertEqual(totals['billed_charge']['coverage'], 'unknown')

    def test_incomplete_usage_never_promoted_to_complete(self):
        for state in ('started', 'cancelled', 'timeout', 'failed'):
            with self.subTest(state=state):
                totals = scoring.aggregate_attempts([self.attempt(state=state)])
                self.assertIsNone(totals['total_tokens']['value'])
                self.assertEqual(totals['total_tokens']['known_sum'], 120)
                self.assertEqual(totals['model_requests'], 1)
        final = scoring.aggregate_attempts([self.attempt(state='cancelled', usage_final=True)])
        self.assertEqual(final['total_tokens']['value'], 120)

    def test_native_usage_and_invalid_counts(self):
        native = scoring.aggregate_attempts([{'state': 'completed', 'prompt_eval_count': 7, 'eval_count': 3}])
        self.assertEqual(native['total_tokens']['value'], 10)
        for bad in (True, -1, 2.5, float('nan')):
            self.assertIsNone(scoring.aggregate_attempts([self.attempt(input_tokens=bad)])['total_tokens']['value'])

    def test_actual_and_estimated_money_separate(self):
        totals = scoring.aggregate_attempts([self.attempt(billed_charge=0.03, estimated_cost=0.02)])
        self.assertEqual(totals['billed_charge']['value'], 0.03)
        self.assertEqual(totals['estimated_cost']['value'], 0.02)
        self.assertIsNone(scoring.aggregate_attempts([])['total_tokens']['value'])

    def test_blind_packet_hides_identity_and_does_not_repair(self):
        records = [{'run_id': 'run-secret-a', 'task_id': 'T01', 'raw_output': '```json\n'+self.raw+'\n```',
                    'model': 'private-model-marker', 'condition': 'enabled', 'tokens': 999, 'order': 2},
                   {'run_id': 'run-secret-b', 'task_id': 'T01', 'raw_output': self.raw,
                    'model': 'private-model-marker', 'condition': 'disabled'}]
        frozen = copy.deepcopy(records)
        bundle = scoring.make_blind_bundle(records, {'T01': self.task}, self.sources, 'private-seed-0001')
        public = json.dumps(bundle['public'])
        for marker in ('private-model-marker', 'run-secret-a', 'run-secret-b', '"condition"', '"tokens"', '"order"'):
            self.assertNotIn(marker, public)
        self.assertEqual({p['raw_output'] for p in bundle['public']['packets']}, {r['raw_output'] for r in records})
        self.assertEqual(records, frozen)
        self.assertEqual(bundle, scoring.make_blind_bundle(records, {'T01': self.task}, self.sources, 'private-seed-0001'))
        self.assertEqual(len(bundle['private_key']['mapping']), 2)
        self.assertEqual(bundle['public']['source_snapshots'], self.sources)

    def test_blind_reference_integrity_and_duplicate_ids(self):
        records = [{'run_id': 'r', 'task_id': 'T01', 'raw_output': self.raw, 'model': 'm', 'condition': 'enabled'}]
        with self.assertRaises(scoring.ReviewError):
            scoring.make_blind_bundle(records*2, {'T01': self.task}, self.sources, 'private-seed-0001')
        with self.assertRaises(scoring.ReviewError):
            scoring.make_blind_bundle(records, {'T01': self.task}, {'queue': 'changed'}, 'private-seed-0001')

    def test_only_independent_human_review_can_qualify(self):
        score = self.score(); review = self.human_review(score)
        self.assertTrue(scoring.apply_review(score, review, self.task)['overall_quality_pass'])
        for field in ('human', 'independent', 'blinded'):
            bad = dict(review, **{field: False})
            with self.assertRaises(scoring.ReviewError):
                scoring.apply_review(score, bad, self.task)
        with self.assertRaises(scoring.ReviewError):
            scoring.apply_review(score, dict(review, raw_output_sha256='b'*64), self.task)

    def test_missing_review_verdict_and_unsupported_claim(self):
        score = self.score(); review = self.human_review(score)
        self.assertIsNone(scoring.apply_review(score, None, self.task)['overall_quality_pass'])
        review['facts']['owner'] = None
        self.assertIsNone(scoring.apply_review(score, review, self.task)['overall_quality_pass'])
        review['unsupported_claims'] = ['The model invented an override.']
        self.assertFalse(scoring.apply_review(score, review, self.task)['overall_quality_pass'])

    def test_missing_constraint_or_wrong_citation_count_rejected(self):
        score = self.score(); review = self.human_review(score)
        with self.assertRaises(scoring.ReviewError):
            scoring.apply_review(score, dict(review, constraints={}), self.task)
        with self.assertRaises(scoring.ReviewError):
            scoring.apply_review(score, dict(review, citation_support=[]), self.task)

    def test_failed_mechanical_gate_cannot_be_rescued_by_review(self):
        bad = copy.deepcopy(self.answer); bad['citations'][0]['quote'] = 'wrong'
        score = self.score(json.dumps(bad))
        self.assertFalse(scoring.apply_review(score, self.human_review(score), self.task)['overall_quality_pass'])

    def test_quality_regression_blocks_positive_savings_claim(self):
        records = [self.record('disabled', quality_pass=True),
                   self.record('enabled', quality_pass=False, attempts=[self.attempt(input_tokens=40)])]
        report = scoring.summarize_pairs(records)
        self.assertGreater(report['pairs'][0]['total_tokens']['reduction_percent'], 0)
        self.assertFalse(report['pairs'][0]['quality_preserving_eligible'])
        self.assertEqual(report['groups'][0]['quality_preserving_pairs'], 0)
        self.assertIsNone(report['groups'][0]['quality_preserving_total_tokens']['reduction_percent'])

    def test_negative_savings_and_baseline_strata(self):
        records = [self.record('disabled', quality_pass=True),
                   self.record('enabled', quality_pass=True, attempts=[self.attempt(input_tokens=200)])]
        records += [self.record(a, pair_id='p2', baseline_type='lexical', quality_pass=True) for a in ('disabled', 'enabled')]
        report = scoring.summarize_pairs(records)
        self.assertLess(next(p for p in report['pairs'] if p['pair_id']=='pair-1')['total_tokens']['reduction_percent'], 0)
        top = [g for g in report['groups'] if 'category' not in g]
        self.assertEqual({g['baseline_type'] for g in top}, {'complete','lexical'})
        self.assertTrue(all(g['pairs']==1 for g in top))

    def test_incomplete_pair_and_mismatched_identity(self):
        report = scoring.summarize_pairs([self.record('disabled')])
        self.assertEqual(report['pairs'][0]['arms_present'], 1)
        self.assertIsNone(report['pairs'][0]['total_tokens']['reduction_percent'])
        self.assertEqual(report['groups'][0]['quality_counts']['enabled']['unknown'], 1)
        with self.assertRaises(ValueError):
            scoring.summarize_pairs([self.record('disabled'), self.record('enabled', model='different')])
        with self.assertRaises(ValueError):
            scoring.summarize_pairs([self.record('disabled'), self.record('disabled')])

    def test_unknown_usage_blocks_group_aggregate_and_quality_subset(self):
        records = [self.record('disabled', quality_pass=True),
                   self.record('enabled', quality_pass=True, attempts=[self.attempt(output_tokens=None)])]
        report = scoring.summarize_pairs(records)
        self.assertFalse(report['pairs'][0]['usage_complete'])
        self.assertEqual(report['groups'][0]['fully_measured_pairs'], 0)
        self.assertIsNone(report['groups'][0]['observed_total_tokens']['reduction_percent'])
        self.assertEqual(report['groups'][0]['quality_preserving_pairs'], 0)


if __name__ == '__main__':
    unittest.main()
