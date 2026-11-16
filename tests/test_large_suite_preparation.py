"""Offline miniature fixtures for fair, bounded large-suite prompt preparation."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('large_suite', ROOT/'scripts/large_suite.py')
suite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(suite)


class LargeSuitePreparationTests(unittest.TestCase):
    def doc(self, name, text, **kwargs):
        return dict({'id': name, 'path': name+'.md', 'scope': 'compact', 'status': 'active',
                     'freshness': 'fresh', 'origin': 'source_evidence', 'authority': 'authoritative',
                     'sha256': hashlib.sha256(text.encode()).hexdigest(), 'bytes': len(text.encode())}, **kwargs)

    def setUp(self):
        self.sources = {'manual': '# Manual\n\nSynthetic queue capacity is twelve jobs.\n\nOwners approve release.\n'}
        self.docs = [self.doc(k,v) for k,v in self.sources.items()]
        self.task = {'id': 'tiny-task', 'category': 'multi_document', 'scope': 'compact',
                     'question': 'What is the synthetic queue capacity and who approves release?',
                     'constraints': ['Do not execute anything.'], 'expected_status': 'answered',
                     'reference_answer': 'GOLD-REFERENCE-DO-NOT-SEND',
                     'required_facts': [{'id': 'fact', 'text': 'GOLD-FACT-DO-NOT-SEND'}],
                     'required_evidence': [{'source_id': 'manual', 'source_sha256': self.docs[0]['sha256'],
                         'line_start': 3, 'line_end': 3, 'quote': 'Synthetic queue capacity is twelve jobs.'}],
                     'forbidden_claims': ['GOLD-FORBIDDEN-DO-NOT-SEND']}
        self.protocol = {'complete_document_scopes': ['compact'],
                         'selection_budget': {'max_bytes': 4000, 'max_items': 8},
                         'options': {'num_ctx': 32768, 'num_predict': 1024}, 'chat_template_reserve': 1024,
                         'order_seed': 7, 'models': [{'id':'a','name':'fictional-a','arm_deadline_seconds':60},
                                                  {'id':'b','name':'fictional-b','arm_deadline_seconds':120}]}

    def run_contexts(self, **kwargs):
        store = suite.make_store(self.docs, self.sources)
        baseline = suite.WindowBaseline(self.docs, self.sources)
        try:
            return suite.contexts(self.task, self.docs, self.sources, store, baseline,
                                  kwargs.get('protocol', self.protocol), conditions=kwargs.get('conditions', ('disabled','enabled')))
        finally:
            store.close();baseline.close()

    def test_common_prompt_has_no_gold_or_reference_hints(self):
        pair = self.run_contexts()
        self.assertEqual(pair['disabled']['messages'][1], pair['enabled']['messages'][1])
        for arm in pair.values():
            serialized = json.dumps(arm['messages'])
            for marker in ('GOLD-REFERENCE','GOLD-FACT','GOLD-FORBIDDEN','source_sha256_hint'):
                self.assertNotIn(marker, serialized)
            self.assertIn('Do not execute anything.', serialized)
            self.assertEqual(arm['submitted_message_text_bytes'], sum(len(m['content'].encode()) for m in arm['messages']))

    def test_complete_baseline_has_every_eligible_document(self):
        for name,changes in [('active-other',{}), ('stale',{'freshness':'stale'}),
                             ('revoked',{'status':'revoked'}), ('superseded',{'status':'superseded'}),
                             ('outside',{'scope':'other'})]:
            text = '# '+name+'\n\nSynthetic queue release facts.\n'
            self.sources[name]=text;self.docs.append(self.doc(name,text,**changes))
        pair = self.run_contexts()
        self.assertEqual({r['source_id'] for r in pair['disabled']['evidence']}, {'manual','active-other'})
        for record in pair.values():
            self.assertTrue({r['source_id'] for r in record['evidence']} <= {'manual','active-other'})

    def test_baseline_filters_scope_before_selection_cutoff(self):
        docs, sources = [], {}
        for i in range(70):
            name='outside-'+str(i);text='queue\nqueue queue queue release\n'
            sources[name]=text;docs.append(self.doc(name,text,scope='outside'))
        sources.update(self.sources);docs.extend(self.docs)
        baseline = suite.WindowBaseline(docs,sources)
        try:
            items,details=baseline.context('queue release','compact',max_bytes=4000,max_items=1)
            self.assertEqual([i['source_id'] for i in items],['manual'])
            self.assertEqual(details['candidate_count'],1)
        finally:baseline.close()

    def test_baseline_byte_budget_is_exact_and_never_clips(self):
        baseline=suite.WindowBaseline(self.docs,self.sources)
        try:
            items,_=baseline.context('queue','compact',max_bytes=4000,max_items=8)
            self.assertEqual(len(items),1)
            size=len(suite.render(items).encode())
            accepted,_=baseline.context('queue','compact',max_bytes=size,max_items=8)
            missing,details=baseline.context('queue','compact',max_bytes=size-1,max_items=8)
            self.assertEqual(accepted,items)
            self.assertEqual(missing,[])
            self.assertEqual(details['budget_omissions'],1)
        finally:baseline.close()

    def test_invalid_context_validation_is_rejected(self):
        store=suite.make_store(self.docs,self.sources);baseline=suite.WindowBaseline(self.docs,self.sources)
        try:
            for status in ('changed','denied'):
                with self.subTest(status=status), patch.object(store,'validate_context',return_value=status):
                    with self.assertRaisesRegex(ValueError,'validation failed'):
                        suite.contexts(self.task,self.docs,self.sources,store,baseline,self.protocol,conditions=('enabled',))
        finally:store.close();baseline.close()

    def test_explicit_empty_budget_failure_preserved_but_not_authorization_error(self):
        store=suite.make_store(self.docs,self.sources);baseline=suite.WindowBaseline(self.docs,self.sources)
        try:
            native=store.context({'contract_version':'0.1','request_id':'empty','query':'no-such-term-zzzz',
                'access_scope_ref':'compact','destination':'local_only','purpose':'current_answer',
                'budget':{'max_bytes':4000,'max_tokens':4000,'max_items':8}})
            native.update(items=[],context_text='',error={'code':'BUDGET_TOO_SMALL'},status='error')
            with patch.object(store,'context',return_value=native), patch.object(store,'validate_context',return_value='denied'):
                result=suite.contexts(self.task,self.docs,self.sources,store,baseline,self.protocol,conditions=('enabled',))
                self.assertEqual(result['enabled']['evidence'],[])
                self.assertEqual(result['enabled']['details']['native_error']['code'],'BUDGET_TOO_SMALL')
                native['error']={'code':'DESTINATION_DENIED'}
                with self.assertRaises(ValueError):
                    suite.contexts(self.task,self.docs,self.sources,store,baseline,self.protocol,conditions=('enabled',))
        finally:store.close();baseline.close()

    def test_kre_text_or_scope_mismatch_is_rejected(self):
        store=suite.make_store(self.docs,self.sources);baseline=suite.WindowBaseline(self.docs,self.sources)
        try:
            request={'contract_version':'0.1','request_id':'tiny','query':'queue', 'access_scope_ref':'compact',
                     'destination':'local_only','purpose':'current_answer','freshness_requirement':'allow_unknown',
                     'budget':{'max_bytes':4000,'max_tokens':4000,'max_items':8}}
            native=store.context(request);self.assertTrue(native['items'])
            native['items'][0]['text']='Changed source text'
            # Even a compromised validation return cannot bypass exact span equality.
            with patch.object(store,'context',return_value=native), patch.object(store,'validate_context',return_value='current'):
                with self.assertRaisesRegex(ValueError,'source span or scope mismatch'):
                    suite.contexts(self.task,self.docs,self.sources,store,baseline,self.protocol,conditions=('enabled',))
        finally:store.close();baseline.close()

    def test_complete_context_admission_rejects_instead_of_truncating(self):
        protocol=copy.deepcopy(self.protocol);protocol['options']['num_ctx']=1025
        with self.assertRaisesRegex(ValueError,'no truncation'):
            self.run_contexts(protocol=protocol,conditions=('disabled',))

    def test_checkpoint_revocation_suppresses_prose_and_preserves_constraints(self):
        old='# Retired rule\n\nAn old waiver permitted an unsafe extension.\n'
        self.sources['old']=old;self.docs.append(self.doc('old',old,status='revoked'))
        ref={'source_id':'old','source_sha256':self.docs[-1]['sha256'],
             'line_start':3,'line_end':3,'quote':'An old waiver permitted an unsafe extension.'}
        self.task['checkpoint']={'objective':'Review the paused plan.', 'constraints':['No changes.','No deployment.'],
            'decisions':[{'text':'REVOKED-DECISION-MUST-NOT-BE-PROMPTED','evidence':[ref]}],
            'unresolved_questions':['Who approves the current release?'],'next_actions':['Review current records.'],
            'lifecycle_transition':{'source_id':'old','from':'active','to':'revoked'}}
        frozen=copy.deepcopy(self.task)
        disabled,db=suite.recover_checkpoint(self.task,self.docs,self.sources,'disabled')
        enabled,de=suite.recover_checkpoint(self.task,self.docs,self.sources,'enabled')
        self.assertEqual(disabled,enabled)
        self.assertEqual(enabled['decisions'],[])
        self.assertEqual(enabled['invalidated_decision_count'],1)
        self.assertEqual(enabled['constraints'],['No changes.','No deployment.'])
        self.assertEqual(de['method'],'kre_checkpoint_and_resume')
        self.assertEqual(de['status'],'partial')
        self.assertNotIn('REVOKED-DECISION',suite.task_message(self.task,enabled))
        self.assertNotIn(ref['quote'],suite.task_message(self.task,enabled))
        self.assertEqual(self.task,frozen)

    def test_gold_spans_are_source_exact_and_eligible(self):
        suite.validate_gold([self.task],self.docs,self.sources)
        for update in ({'quote':'not exact'}, {'source_sha256':'0'*64}, {'line_end':99}):
            task=copy.deepcopy(self.task);task['required_evidence'][0].update(update)
            with self.subTest(update=update),self.assertRaises(ValueError):
                suite.validate_gold([task],self.docs,self.sources)
        self.docs[0]['status']='superseded'
        with self.assertRaisesRegex(ValueError,'not eligible'):
            suite.validate_gold([self.task],self.docs,self.sources)

    def test_schedule_has_balanced_reversed_arm_order_and_sequential_models(self):
        tasks=[dict(self.task,id='task-'+str(i)) for i in range(24)]
        rows=suite.schedule(tasks,self.protocol)
        self.assertEqual(len(rows),96)
        self.assertTrue(all(r['model_id']=='a' for r in rows[:48]))
        self.assertTrue(all(r['model_id']=='b' for r in rows[48:]))
        firsts={model:[r['condition'] for r in rows if r['model_id']==model][::2] for model in ('a','b')}
        self.assertEqual(firsts['a'].count('disabled'),12)
        self.assertEqual(firsts['b'].count('disabled'),12)
        self.assertTrue(all(a!=b for a,b in zip(firsts['a'],firsts['b'])))

    def test_prompt_preparation_needs_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            pair=self.run_contexts()
            self.assertEqual(set(pair),{'disabled','enabled'})


if __name__=='__main__':
    unittest.main()
