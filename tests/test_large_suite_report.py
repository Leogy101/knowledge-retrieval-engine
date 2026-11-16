"""Offline collector fixtures; no inference, transport or retrieval."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('large_suite_report',ROOT/'scripts/large_suite_report.py')
report=importlib.util.module_from_spec(spec);spec.loader.exec_module(report)


class LargeSuiteReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.run=self.root/'run';self.run.mkdir()
        self.fixture=self.root/'fixture';self.fixture.mkdir()
        self.text='The queue holds twelve jobs.\n';sha=report.suite.digest(self.text.encode())
        self.docs=[{'id':'manual','scope':'compact','status':'active','freshness':'fresh','authority':'authoritative','origin':'source_evidence','sha256':sha}]
        self.sources={'manual':self.text}
        self.tasks=[{'id':f'T{i:02}','category':'facts','scope':'compact','question':'What is the queue limit?',
                     'constraints':[],'expected_status':'answered','reference_answer':'Twelve jobs.',
                     'required_facts':[{'id':'capacity','text':'Twelve jobs.'}], 'forbidden_claims':[],
                     'required_evidence':[{'source_id':'manual','source_sha256':sha,'line_start':1,'line_end':1,'quote':self.text.rstrip()}]} for i in range(24)]
        self.protocol={'order_seed':1,'complete_document_scopes':['compact'],
             'options':{'num_ctx':32768,'num_predict':1024,'temperature':0},
             'selection_budget':{'max_bytes':4000,'max_items':8},'chat_template_reserve':1024,
             'models':[{'id':'a','name':'fictional-a','arm_deadline_seconds':60},
                       {'id':'b','name':'fictional-b','arm_deadline_seconds':120}]}
        report.suite.write(self.fixture/'protocol.json',self.protocol)
        self.loader=patch.object(report.suite,'load_fixture',return_value=(self.docs,self.tasks,self.sources));self.loader.start();self.addCleanup(self.loader.stop)
        self.plan=report.suite.schedule(self.tasks,self.protocol)

    def captured_arm(self,index=0):
        planned=self.plan[index];folder=self.run/f"arm-{planned['ordinal']:03}";folder.mkdir()
        item=report.suite.packet(self.docs[0],self.text,1,1)
        messages=[{'role':'user','content':report.suite.PREFIX+report.suite.render([item])+report.suite.SUFFIX},
                  {'role':'user','content':report.suite.task_message(next(t for t in self.tasks if t['id']==planned['task_id']))}]
        request={'model':planned['model'],'think':False,'messages':messages,'options':self.protocol['options'],'stream':False,'truncate':False,'shift':False}
        raw=json.dumps({'status':'answered','answer':'Twelve jobs.','citations':[{'source_id':'manual','line_start':1,'line_end':1,'quote':self.text.rstrip()}]})
        wire=report.suite.encoded(request);(folder/'request.json').write_bytes(wire);(folder/'answer.txt').write_text(raw)
        response={'message':{'content':raw},'prompt_eval_count':100,'eval_count':10,'prompt_eval_cached_count':0}
        report.suite.write(folder/'response.json',response)
        attempt={'state':'completed','usage_final':True,'retry':False,'input_tokens':100,'output_tokens':10,'cached_tokens':0,'submitted_message_bytes':sum(len(m['content'].encode()) for m in messages)}
        receipt={**planned,'state':'completed','attempts':[attempt],'completion_seconds':2,
                 'request_sha256':report.suite.digest(wire),'answer_sha256':report.suite.digest(raw.encode()),
                 'evidence':report.suite.evidence([item]),'submitted_message_text_bytes':attempt['submitted_message_bytes'],
                 'context_bytes':len(report.suite.render([item]).encode()),'http_json_body_bytes':len(wire),
                 'messages_serialized_bytes':len(report.suite.encoded(messages))}
        report.suite.write(folder/'receipt.json',receipt)
        return folder,receipt,raw

    def test_all_96_missing_arms_are_retained_without_network_or_retrieval(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')), \
             patch.object(report.suite,'contexts',side_effect=AssertionError('retrieval forbidden')):
            result=report.collect(self.run,self.fixture)
        self.assertEqual(result['scheduled_arms'],96)
        self.assertEqual(len(result['records']),96)
        self.assertTrue(all(r['state']=='not_started' for r in result['records']))
        self.assertTrue(all(r['quality_pass'] is None for r in result['records']))
        self.assertEqual(len(result['summary']['pairs']),48)

    def test_complete_native_usage_scored_but_no_semantics_invented(self):
        self.captured_arm();result=report.collect(self.run,self.fixture)
        captured=result['records'][0]
        self.assertTrue(captured['quality_score']['deterministic_gate'])
        self.assertIsNone(captured['quality_pass'])
        self.assertEqual(captured['measurement_errors'],[])
        self.assertEqual(len(result['records']),96)
        self.assertEqual(len(result['blind_records']),1)

    def test_tamper_is_retained_as_failure_and_incomplete_usage(self):
        folder,receipt,raw=self.captured_arm();(folder/'answer.txt').write_text(raw+' ')
        result=report.collect(self.run,self.fixture);row=result['records'][0]
        self.assertFalse(row['quality_pass']);self.assertIn('answer hash mismatch',row['measurement_errors'])
        self.assertFalse(row['attempts'][0]['usage_final'])
        self.assertEqual(row['attempts'][0]['input_tokens'],100)

    def test_private_key_mode_and_blind_metadata(self):
        self.captured_arm();output=self.root/'report'
        report.write_report(self.run,output,self.fixture)
        key=output/'private/unblinding-key.json'
        self.assertEqual(key.stat().st_mode & 0o777,0o600)
        public=(output/'blind-review.json').read_text()
        self.assertNotIn('fictional-a',public);self.assertNotIn('"condition"',public)
        self.assertTrue(json.loads(public)['packets'][0]['source_metadata'])
        self.assertTrue((output/'results.json').is_file())

    def change_prompt(self,folder,receipt,prompt):
        request=json.loads((folder/'request.json').read_text())
        request['messages'][1]['content']=prompt
        wire=report.suite.encoded(request);(folder/'request.json').write_bytes(wire)
        receipt['request_sha256']=report.suite.digest(wire)
        receipt['http_json_body_bytes']=len(wire)
        receipt['messages_serialized_bytes']=len(report.suite.encoded(request['messages']))
        receipt['submitted_message_text_bytes']=sum(len(m['content'].encode()) for m in request['messages'])
        receipt['attempts'][0]['submitted_message_bytes']=receipt['submitted_message_text_bytes']
        report.suite.write(folder/'receipt.json',receipt)

    def test_same_wrong_prompt_in_both_arms_is_not_comparable(self):
        for index in (0,1):
            folder,receipt,_=self.captured_arm(index)
            self.change_prompt(folder,receipt,'Identical but wrong frozen task')
        result=report.collect(self.run,self.fixture)
        for row in result['records'][:2]:
            self.assertIn('frozen task instruction mismatch',row['measurement_errors'])
            self.assertFalse(row['attempts'][0]['usage_final'])
        pair=next(p for p in result['summary']['pairs'] if p['pair_id']==self.plan[0]['pair_id'])
        self.assertIsNone(pair['total_tokens']['reduction_percent'])

    def test_paired_instruction_mismatch_blocks_comparable_percentage(self):
        self.captured_arm(0)
        folder,receipt,_=self.captured_arm(1)
        self.change_prompt(folder,receipt,'A changed treatment task')
        result=report.collect(self.run,self.fixture)
        for row in result['records'][:2]:
            self.assertIn('paired task instruction mismatch',row['measurement_errors'])
            self.assertFalse(row['attempts'][0]['usage_final'])
        pair=next(p for p in result['summary']['pairs'] if p['pair_id']==self.plan[0]['pair_id'])
        self.assertIsNone(pair['total_tokens']['reduction_percent'])

    def test_unscheduled_arms_are_not_silently_dropped(self):
        (self.run/'arm-999').mkdir()
        with self.assertRaisesRegex(ValueError,'Unscheduled'):
            report.collect(self.run,self.fixture)


if __name__=='__main__':unittest.main()
