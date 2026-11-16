"""Offline transport-only execution guards for the frozen large benchmark.

Every test forbids HTTP connections and OS process reads. The fake transport is
not model evidence and never sends a real load, unload or inference request.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import large_suite_run as runner


class FakeTransport:
    def __init__(self, model, *, content=None, content_error=None, load_error=None,
                 tags_override=None, show_override=None, resident_before=None):
        self.model = copy.deepcopy(model)
        self.content = content
        self.content_error = content_error
        self.load_error = load_error
        self.calls = []
        self.resident = copy.deepcopy(resident_before or [])
        self.tags_override = tags_override or {}
        self.show_override = show_override or {}

    def call(self, method, path, payload=None, *, timeout=3, receipt=None, raw_path=None):
        self.calls.append((method, path, copy.deepcopy(payload), timeout))
        if method == 'GET' and path == '/api/version':
            return {'version': '0.40.15'}
        if method == 'GET' and path == '/api/tags':
            row = {'name': self.model['name'], 'digest': self.model['digest'],
                   'details': {'runner': self.model['runner'], 'format': self.model['format'],
                               'quantization_level': self.model['quantization']}}
            row.update(self.tags_override)
            return {'models': [row]}
        if method == 'POST' and path == '/api/show':
            value = {'thinking': {'values': [False, True], 'default': True},
                     'details': {'runner': self.model['runner'], 'format': self.model['format'],
                                 'quantization_level': self.model['quantization']},
                     'capabilities': ['completion', 'thinking']}
            value.update(self.show_override)
            return value
        if method == 'GET' and path == '/api/ps':
            return {'models': copy.deepcopy(self.resident)}
        if (method, path) != ('POST', '/api/chat'):
            raise AssertionError('Unplanned fake operation')
        if payload['messages'] == []:
            kind = 'unload' if payload['keep_alive'] == 0 else 'load'
            if kind == 'load' and self.load_error is not None:
                raise self.load_error
            self.resident = ([] if kind == 'unload' else [{
                'name': self.model['name'], 'digest': self.model['digest'],
                'context_length': 32768}])
            response = {'model': self.model['name'], 'done': True,
                        'done_reason': kind, 'message': {'content': ''}}
        else:
            if self.content_error is not None:
                raise self.content_error
            response = copy.deepcopy(self.content if self.content is not None else {
                'model': self.model['name'], 'done': True, 'done_reason': 'stop',
                'message': {'content': '{"status":"answered","answer":"fixture","citations":[]}'},
                'prompt_eval_count': 100, 'eval_count': 20,
                'prompt_eval_cached_count': 0, 'load_duration': 10,
                'total_duration': 100, 'prompt_eval_duration': 30, 'eval_duration': 60})
        if receipt is not None:
            receipt.update(peer={'address': '127.0.0.1', 'port': 11434}, http_status=200)
        if raw_path is not None:
            Path(raw_path).write_text(json.dumps(response))
        return response

    def generated(self):
        return [c for c in self.calls if c[1] == '/api/chat' and c[2]['messages']]

    def lifecycle_kinds(self):
        return [('unload' if c[2]['keep_alive'] == 0 else 'load')
                for c in self.calls if c[1] == '/api/chat' and c[2]['messages'] == []]


class LargeSuiteRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.network = patch.object(runner.http.client, 'HTTPConnection',
                                    side_effect=AssertionError('Real network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)
        self.process = patch.object(runner.subprocess, 'check_output',
                                    side_effect=AssertionError('OS reads forbidden'))
        self.process.start()
        self.addCleanup(self.process.stop)
        self.prior_stop = runner.STOP_REQUESTED
        runner.STOP_REQUESTED = False
        self.addCleanup(setattr, runner, 'STOP_REQUESTED', self.prior_stop)
        self.model = {'id': 'A', 'name': 'fixture-local:1', 'digest': 'a' * 64,
                      'runner': 'ggml', 'format': 'gguf', 'quantization': 'Q4_K_M',
                      'minimum_free_memory_percent': 30, 'arm_deadline_seconds': 5}
        self.protocol = {'options': {'num_ctx': 32768, 'num_predict': 1536, 'temperature': 0},
                         'minimum_loaded_free_memory_percent': 10, 'cleanup_deadline_seconds': 5}
        self.row = {'ordinal': 1, 'task_id': 'fixture-task', 'condition': 'disabled', 'model_id': 'A'}
        self.context = {'messages': [{'role': 'user', 'content': 'frozen context'},
                                     {'role': 'user', 'content': 'frozen question'}],
                        'submitted_message_text_bytes': len('frozen contextfrozen question'.encode()),
                        'retrieval_seconds': 0, 'context_bytes': len('frozen context')}
        self.headroom = []

    def guard(self, minimum):
        self.headroom.append(minimum)
        return 90

    def execute(self, fake=None, *, name='arm', prepare=None, row=None):
        fake = fake or FakeTransport(self.model)
        result = runner.execute_arm(row or self.row, self.model, self.protocol,
                                    self.folder / name, prepare or (lambda: copy.deepcopy(self.context)),
                                    fake, guard=self.guard)
        return fake, result

    def response(self, **changes):
        value = {'model': self.model['name'], 'done': True, 'done_reason': 'stop',
                 'message': {'content': '{}'}, 'prompt_eval_count': 100,
                 'eval_count': 20, 'prompt_eval_cached_count': 0}
        value.update(changes)
        return value

    def test_pair_has_two_content_calls_four_lifecycle_operations_and_matched_settings(self):
        fake = FakeTransport(self.model)
        first = self.execute(fake, name='disabled')[1]
        treatment = dict(self.row, ordinal=2, condition='enabled')
        second = self.execute(fake, name='enabled', row=treatment)[1]
        self.assertEqual([first['state'], second['state']], ['completed', 'completed'])
        self.assertTrue(first['restored'] and second['restored'])
        self.assertEqual(len(fake.generated()), 2)
        self.assertEqual(fake.lifecycle_kinds(), ['load', 'unload', 'load', 'unload'])
        self.assertEqual(fake.resident, [])
        for _, _, payload, _ in fake.generated():
            self.assertIs(payload['think'], False)
            self.assertEqual(payload['options'], self.protocol['options'])
            self.assertNotIn('format', payload)
            self.assertNotIn('tools', payload)
            self.assertIs(payload['truncate'], False)
            self.assertIs(payload['shift'], False)
        self.assertEqual(self.headroom, [30, 10, 30, 10])
        self.assertEqual(first['retries'], 0)
        self.assertEqual(second['repairs'], 0)
        self.assertEqual(first['attempts'][0]['cached_tokens'], 0)
        self.assertIsNone(first['attempts'][0]['reasoning_tokens'])
        self.assertIsNone(first['actual_billed_charge'])

    def test_reserved_arm_cannot_be_replayed(self):
        fake, _ = self.execute()
        count = len(fake.calls)
        with self.assertRaises(FileExistsError):
            self.execute(fake)
        self.assertEqual(len(fake.calls), count)

    def test_missing_usage_stops_after_one_terminal_attempt_and_restores(self):
        response = self.response()
        del response['eval_count']
        fake, result = self.execute(FakeTransport(self.model, content=response))
        self.assertEqual(result['state'], 'stopped')
        self.assertIn('Missing usage', result['error'])
        self.assertTrue(result['terminal_observed'])
        self.assertTrue(result['restored'])
        self.assertEqual(len(fake.generated()), 1)
        self.assertIsNone(result['attempts'][0]['output_tokens'])
        self.assertEqual(result['attempts'][0]['input_tokens'], 100)
        self.assertEqual(fake.lifecycle_kinds(), ['load', 'unload'])

    def test_timeout_after_dispatch_keeps_usage_unknown_and_does_not_unload(self):
        fake, result = self.execute(FakeTransport(self.model, content_error=TimeoutError('fake timeout')))
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['error_type'], 'TimeoutError')
        self.assertFalse(result['restored'])
        self.assertFalse(result['terminal_observed'])
        self.assertEqual(len(fake.generated()), 1)
        self.assertEqual(fake.lifecycle_kinds(), ['load'])
        self.assertFalse(result['attempts'][0]['usage_final'])
        self.assertIsNone(result['attempts'][0]['input_tokens'])
        self.assertIsNone(result['attempts'][0]['output_tokens'])

    def test_interrupt_after_dispatch_is_not_retried_or_assumed_stopped_remotely(self):
        fake, result = self.execute(FakeTransport(self.model, content_error=KeyboardInterrupt()))
        self.assertEqual(result['attempts'][0]['state'], 'cancelled')
        self.assertEqual(len(fake.generated()), 1)
        self.assertEqual(fake.lifecycle_kinds(), ['load'])
        self.assertFalse(result['restored'])

    def test_stop_after_known_preload_does_not_dispatch_and_restores(self):
        runner.STOP_REQUESTED = True
        fake, result = self.execute()
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['attempts'], [])
        self.assertEqual(fake.generated(), [])
        self.assertEqual(fake.lifecycle_kinds(), ['load', 'unload'])
        self.assertTrue(result['restored'])

    def test_stop_during_preparation_does_not_dispatch(self):
        def prepare():
            runner.request_stop()
            return copy.deepcopy(self.context)
        fake, result = self.execute(prepare=prepare)
        self.assertEqual(fake.generated(), [])
        self.assertEqual(result['attempts'], [])
        self.assertEqual(result['state'], 'stopped')
        self.assertTrue(result['restored'])

    def test_preparation_failure_after_confirmed_load_restores_without_content(self):
        def prepare():
            raise ValueError('fake context refusal')
        fake, result = self.execute(prepare=prepare)
        self.assertEqual(fake.generated(), [])
        self.assertEqual(fake.lifecycle_kinds(), ['load', 'unload'])
        self.assertTrue(result['restored'])

    def test_unknown_load_completion_stops_without_content_or_unload(self):
        fake, result = self.execute(FakeTransport(self.model, load_error=TimeoutError('fake load timeout')))
        self.assertEqual(fake.generated(), [])
        self.assertEqual(fake.lifecycle_kinds(), ['load'])
        self.assertFalse(result['restored'])
        self.assertEqual(result['attempts'], [])

    def test_nonterminal_content_response_stops_without_cleanup(self):
        fake, result = self.execute(FakeTransport(self.model, content=self.response(done=False)))
        self.assertEqual(result['attempts'][0]['input_tokens'], 100)
        self.assertEqual(result['attempts'][0]['output_tokens'], 20)
        self.assertFalse(result['attempts'][0]['usage_final'])
        self.assertEqual(result['state'], 'stopped')
        self.assertFalse(result['terminal_observed'])
        self.assertFalse(result['restored'])
        self.assertEqual(fake.lifecycle_kinds(), ['load'])
        self.assertEqual(len(fake.generated()), 1)

    def test_length_termination_is_retained_incomplete_without_retry(self):
        fake, result = self.execute(FakeTransport(self.model, content=self.response(done_reason='length', eval_count=1536)))
        self.assertEqual(result['state'], 'output_limit')
        self.assertTrue(result['restored'])
        self.assertEqual(result['attempts'][0]['output_tokens'], 1536)
        self.assertEqual(len(fake.generated()), 1)
        self.assertEqual((self.folder / 'arm' / 'answer.txt').read_text(), '{}')

    def test_malformed_answer_is_preserved_without_repair_or_retry(self):
        raw = '```json\n{"broken":\n```'
        fake, result = self.execute(FakeTransport(self.model, content=self.response(message={'content': raw})))
        self.assertEqual(result['state'], 'completed')
        self.assertEqual((self.folder / 'arm' / 'answer.txt').read_text(), raw)
        self.assertEqual(len(fake.generated()), 1)
        self.assertEqual(result['repairs'], 0)

    def test_optional_cache_and_reasoning_telemetry_stays_unknown(self):
        response = self.response()
        del response['prompt_eval_cached_count']
        fake, result = self.execute(FakeTransport(self.model, content=response))
        self.assertEqual(result['state'], 'completed')
        self.assertIsNone(result['attempts'][0]['cached_tokens'])
        self.assertIsNone(result['attempts'][0]['reasoning_tokens'])
        self.assertTrue(result['restored'])
        self.assertEqual(len(fake.generated()), 1)

    def test_failed_provider_request_is_counted_with_unknown_usage_and_no_retry(self):
        fake, result = self.execute(FakeTransport(self.model, content_error=ValueError('fake HTTP failure')))
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(len(result['attempts']), 1)
        self.assertEqual(len(fake.generated()), 1)
        self.assertIsNone(result['attempts'][0]['input_tokens'])
        self.assertFalse(result['attempts'][0]['usage_final'])
        self.assertFalse(result['restored'])
        self.assertEqual(fake.lifecycle_kinds(), ['load'])

    def test_content_transport_timeout_uses_remaining_arm_budget_after_preload(self):
        clock = [100.0]
        fake = FakeTransport(self.model)
        original = fake.call
        def timed_call(method, path, payload=None, **kwargs):
            response = original(method, path, payload, **kwargs)
            if path == '/api/chat' and payload['messages'] == [] and payload['keep_alive'] != 0:
                clock[0] += 2.0
            return response
        fake.call = timed_call
        with patch.object(runner.time, 'monotonic', side_effect=lambda: clock[0]):
            _, result = self.execute(fake)
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(fake.generated()[0][3], 3.0)
        self.assertEqual(result['completion_seconds'], 2.0)

    def test_explicit_stop_callback_after_preparation_prevents_dispatch(self):
        prepared = [False]
        def prepare():
            prepared[0] = True
            return copy.deepcopy(self.context)
        fake = FakeTransport(self.model)
        result = runner.execute_arm(self.row, self.model, self.protocol, self.folder / 'callback',
                                    prepare, fake, guard=self.guard,
                                    should_stop=lambda: prepared[0])
        self.assertEqual(fake.generated(), [])
        self.assertEqual(result['state'], 'stopped')
        self.assertTrue(result['restored'])
        self.assertEqual(fake.lifecycle_kinds(), ['load', 'unload'])

    def test_wrong_returned_model_stops_after_counted_attempt(self):
        fake, result = self.execute(FakeTransport(self.model, content=self.response(model='other-model')))
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(len(fake.generated()), 1)
        self.assertTrue(result['restored'])

    def test_declared_output_ceiling_violation_stops_and_retains_actual_usage(self):
        fake, result = self.execute(FakeTransport(self.model, content=self.response(eval_count=1537)))
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['attempts'][0]['output_tokens'], 1537)
        self.assertTrue(result['restored'])
        self.assertEqual(len(fake.generated()), 1)

    def test_unexpected_thinking_or_tool_calls_stop_without_repairs(self):
        for extra in ({'thinking': 'unapproved'}, {'tool_calls': [{'function': {'name': 'unexpected'}}]}):
            with self.subTest(extra=extra):
                fake, result = self.execute(FakeTransport(self.model, content=self.response(message={'content': '{}', **extra})),
                                            name='thinking' if 'thinking' in extra else 'tools')
                self.assertEqual(result['state'], 'stopped')
                self.assertTrue(result['restored'])
                self.assertEqual(len(fake.generated()), 1)

    def test_existing_residency_refuses_all_model_operations(self):
        fake, result = self.execute(FakeTransport(self.model, resident_before=[{'name': 'unrelated-model'}]))
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(fake.lifecycle_kinds(), [])
        self.assertEqual(fake.generated(), [])
        self.assertEqual(fake.resident, [{'name': 'unrelated-model'}])

    def test_remote_identity_or_missing_think_false_refuses_before_load(self):
        cases = [('tag-remote', {'tags_override': {'remote_host': 'remote.invalid'}}),
                 ('show-remote', {'show_override': {'remote_model': 'remote-model'}}),
                 ('digest', {'tags_override': {'digest': 'b' * 64}}),
                 ('thinking', {'show_override': {'thinking': {'values': [True]}}})]
        for name, kwargs in cases:
            with self.subTest(name=name):
                fake, result = self.execute(FakeTransport(self.model, **kwargs), name=name)
                self.assertEqual(result['state'], 'stopped')
                self.assertEqual(fake.lifecycle_kinds(), [])
                self.assertEqual(fake.generated(), [])

    def test_backend_format_and_quantization_drift_refused_before_load(self):
        for key, bad in [('runner', 'mlx'), ('format', 'safetensors'), ('quantization_level', 'different')]:
            details = {'runner': self.model['runner'], 'format': self.model['format'],
                       'quantization_level': self.model['quantization']}
            details[key] = bad
            with self.subTest(key=key):
                fake, result = self.execute(FakeTransport(self.model, tags_override={'details': details}), name=key)
                self.assertEqual(result['state'], 'stopped')
                self.assertEqual(fake.lifecycle_kinds(), [])
                self.assertEqual(fake.generated(), [])

    def test_pending_approval_wrong_scope_and_wrong_freeze_refused(self):
        freeze = {'files': {}}
        raw = runner.suite.encoded(freeze)
        approved = {'status': 'approved', 'execution_freeze_sha256': runner.suite.digest(raw),
                    'maximum_content_calls': 96, 'quiet_window_confirmed': True}
        runner.verify_approval(approved, freeze, raw)
        changes = [{'status': 'pending'}, {'maximum_content_calls': 97},
                   {'maximum_content_calls': 95}, {'quiet_window_confirmed': False},
                   {'execution_freeze_sha256': '0' * 64}]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    runner.verify_approval(dict(approved, **change), freeze, raw)

    def test_frozen_file_edit_and_outside_scope_path_refused(self):
        root = (self.folder / 'fixture-root').resolve()
        root.mkdir()
        source = root / 'source.txt'
        source.write_text('frozen')
        freeze = {'files': {'source.txt': runner.suite.digest(source.read_bytes())}}
        raw = runner.suite.encoded(freeze)
        approved = {'status': 'approved', 'execution_freeze_sha256': runner.suite.digest(raw),
                    'maximum_content_calls': 96, 'quiet_window_confirmed': True}
        with patch.object(runner.suite, 'ROOT', root):
            runner.verify_approval(approved, freeze, raw)
            source.write_text('changed')
            with self.assertRaises(ValueError):
                runner.verify_approval(approved, freeze, raw)
            outside = self.folder / 'outside.txt'
            outside.write_text('outside')
            escaped = {'files': {'../outside.txt': runner.suite.digest(outside.read_bytes())}}
            escaped_raw = runner.suite.encoded(escaped)
            escaped_approval = dict(approved, execution_freeze_sha256=runner.suite.digest(escaped_raw))
            with self.assertRaises(ValueError):
                runner.verify_approval(escaped_approval, escaped, escaped_raw)


if __name__ == '__main__':
    unittest.main()
