"""Offline context-attribution contracts; no installed host is required by KRE."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'tests/fixtures/context-attribution/context-evidence.json'


class ContextAttributionEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE.read_text())

    def test_generic_inference_tool_output_retains_nested_copies(self):
        receipt = self.evidence
        self.assertTrue(receipt['context_fields_equivalent'])
        self.assertEqual(receipt['mcp_text_bytes'], receipt['projected_agent_text_bytes'])
        for request in receipt['requests']:
            self.assertTrue(request['exact_projected_text_preserved'])
            self.assertEqual(request['sentinel_occurrences_in_tool_output'], 2)
            self.assertEqual(request['model_visible_tool_text_bytes'], receipt['mcp_text_bytes'])
            self.assertGreater(request['serialized_request_body_bytes'], request['serialized_request_input_bytes'])
            self.assertGreater(request['serialized_request_input_bytes'], request['model_visible_text_bytes'])

    def test_retransmitted_history_is_counted_per_request(self):
        receipt = self.evidence
        self.assertEqual(receipt['aggregate']['request_count'], len(receipt['requests']))
        self.assertEqual(receipt['aggregate']['transmitted_tool_text_bytes'],
                         sum(request['model_visible_tool_text_bytes'] for request in receipt['requests']))
        self.assertEqual(receipt['aggregate']['transmitted_sentinel_occurrences'], 4)
        self.assertGreater(receipt['requests'][1]['model_visible_text_bytes'],
                           receipt['requests'][0]['model_visible_text_bytes'])

    def test_fake_usage_is_separate_from_bytes_and_unknown_real_billing(self):
        receipt = self.evidence
        self.assertEqual(receipt['evidence_kind'], 'synthetic_offline_public_source_replay')
        self.assertFalse(receipt['native_host_final_request_verified'])
        self.assertIsNone(receipt['actual_provider_input_tokens'])
        self.assertIsNone(receipt['actual_billed_usage'])
        totals = receipt['aggregate']
        self.assertIsNone(totals['actual_provider_tokens'])
        self.assertIsNone(totals['actual_billed_charge'])
        usage = [request['synthetic_terminal_usage'] for request in receipt['requests']]
        self.assertEqual(totals['synthetic_total_tokens'], sum(item['total_tokens'] for item in usage))
        self.assertEqual(totals['synthetic_total_tokens'],
                         totals['synthetic_input_tokens'] + totals['synthetic_output_tokens'])
        self.assertGreater(totals['synthetic_cached_tokens_included_in_input'], 0)
        self.assertGreater(totals['synthetic_reasoning_tokens_included_in_output'], 0)

    def test_preserved_validation_and_lifecycle_contract(self):
        self.assertEqual(self.evidence['validation'], {
            'complete': 'current', 'without_items': 'denied', 'without_context_text': 'denied',
            'reconstructed': 'current', 'revoked': 'changed',
            'required_revoked_error': 'REQUIRED_EVIDENCE_MISSING',
        })

    @unittest.skipUnless(os.environ.get('OPENCLAW_PUBLIC_ROOT'),
                         'optional pinned public-source replay; runtime package needs no OpenClaw/Node')
    def test_optional_public_source_replay_matches_recorded_evidence(self):
        # This calls only the fictional fixture generator and isolated source VM.
        # It cannot create an OpenClaw instance, session, network call, or database file.
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        actual = json.loads(subprocess.check_output([
            sys.executable, str(ROOT / 'tests/fixtures/context-attribution/context-probe.py'),
            '--openclaw-root', os.environ['OPENCLAW_PUBLIC_ROOT'],
        ], cwd=ROOT, env=env, text=True, timeout=20))
        expected = dict(self.evidence)
        # Node patch/minor version is recorded metadata, not a result requirement.
        actual.pop('node_version')
        expected.pop('node_version')
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
