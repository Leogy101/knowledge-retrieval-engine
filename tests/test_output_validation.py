"""Offline raw-output boundary tests; source fidelity is separate from semantics."""
import copy
import hashlib
import json
import unittest

from kre.output_validation import validate_output
from kre.quality import QualityError



class OutputValidationTests(unittest.TestCase):
    def setUp(self):
        self.text = 'The fictional tools are fetch and validate.\nIngestion uses the owner CLI.\nLiteral source punctuation: wait... then proceed… safely.\nA wrapped quotation begins\nand continues without rewriting.\n'
        self.digest = hashlib.sha256(self.text.encode()).hexdigest()
        self.sources = {'manual': self.text}
        self.span = {'source_id': 'manual', 'source_sha256': self.digest,
                     'line_start': 1, 'line_end': 5}
        self.rubric = {
            'format': 'task-quality-rubric/1', 'task_id': 'synthetic-output',
            'task_sha256': 'a' * 64,
            'criteria': [{'id': 'status', 'category': 'correctness', 'critical': True,
                          'method': 'exact', 'path': ['status'], 'expected': 'answered'}],
            'sources': {'manual': {'sha256': self.digest, 'eligible': True}},
            'citations': {'require_any': True, 'required_claims': []},
            'required_evidence': [dict(self.span, line_end=2)],
        }
        self.answer = {'status': 'answered', 'answer': 'The tools are fetch and validate. Ingestion uses the owner CLI.',
                       'citations': [{'source_id': 'manual', 'line_start': 1, 'line_end': 2,
                                      'quote': 'The fictional tools are fetch and validate.\nIngestion uses the owner CLI.'}]}

    def validate(self, *, raw=None, **kwargs):
        values = {'sources': self.sources, 'evidence': [self.span]}
        values.update(kwargs)
        return validate_output(json.dumps(self.answer) if raw is None else raw, self.rubric, **values)

    def test_exact_source_quote_and_all_mechanical_checks_do_not_prove_semantics(self):
        before = copy.deepcopy((self.answer, self.rubric, self.sources, self.span))
        result = self.validate()
        self.assertTrue(result['json_valid'])
        self.assertTrue(result['schema_valid'])
        self.assertTrue(result['mechanical_gate'])
        self.assertTrue(result['retrieval_evidence_gate'])
        self.assertEqual(result['citation_exactness']['score'], 1)
        self.assertIsNone(result['semantic_support'])
        self.assertIsNone(result['end_to_end_quality_pass'])
        self.assertEqual(result, self.validate())
        self.assertEqual(before, (self.answer, self.rubric, self.sources, self.span))

    def test_known_frozen_criterion_failure_remains_false_not_unknown(self):
        self.answer['status'] = 'insufficient_evidence'
        result = self.validate()
        self.assertTrue(result['mechanical_gate'])
        self.assertFalse(result['frozen_quality_without_semantic_review'])
        self.assertFalse(result['end_to_end_quality_pass'])
        self.assertIn('FROZEN_CRITERION_FAILED', result['errors'])

    def test_oversized_raw_input_fails_before_hashing(self):
        from unittest.mock import patch
        from kre.quality import MAX_BYTES
        for raw in ('x' * (MAX_BYTES + 1), '界' * (MAX_BYTES // 3 + 1)):
            with self.subTest(characters=len(raw)):
                # Raw input is rejected without trying JSON parse or returning it.
                with patch('kre.output_validation.strict_loads', side_effect=AssertionError('unbounded parse')):
                    with self.assertRaises(QualityError):
                        self.validate(raw=raw)

    def test_inserted_ascii_and_unicode_ellipses_fail_even_with_correct_facts(self):
        for quote in ('The fictional tools... fetch and validate.',
                      'The fictional tools… fetch and validate.'):
            with self.subTest(quote=quote):
                self.answer['citations'][0]['quote'] = quote
                result = self.validate()
                self.assertFalse(result['mechanical_gate'])
                self.assertFalse(result['end_to_end_quality_pass'])
                self.assertEqual(result['citation_exactness']['score'], 0)
                self.assertIn('QUOTE_NOT_EXACT', result['errors'])
                self.assertTrue(result['retrieval_evidence_gate'])

    def test_literal_source_ellipses_are_allowed(self):
        self.answer['citations'][0].update(line_start=3, line_end=3,
                                          quote='wait... then proceed… safely.')
        self.assertTrue(self.validate()['mechanical_gate'])

    def test_json_newline_escape_decodes_to_exact_quote(self):
        self.answer['citations'][0].update(line_start=4, line_end=5,
            quote='A wrapped quotation begins\nand continues without rewriting.')
        raw = json.dumps(self.answer)
        self.assertIn('\\n', raw)
        self.assertTrue(self.validate(raw=raw)['mechanical_gate'])
        self.answer['citations'][0]['quote'] = self.answer['citations'][0]['quote'].replace('\n', ' ')
        self.assertFalse(self.validate()['mechanical_gate'])

    def test_markdown_fences_are_not_stripped_or_repaired(self):
        raw = '```json\n' + json.dumps(self.answer) + '\n```'
        result = self.validate(raw=raw)
        self.assertFalse(result['json_valid'])
        self.assertFalse(result['end_to_end_quality_pass'])
        self.assertEqual(result['errors'], ['INVALID_JSON'])
        self.assertEqual(result['raw_output_sha256'], hashlib.sha256(raw.encode()).hexdigest())
        self.assertIsNone(result['answer_sha256'])
        self.assertEqual(result['citation_checks'], [])

    def test_malformed_duplicate_key_and_nonfinite_json_rejected(self):
        for raw in ('{', '{"status":"answered",}',
                    '{"status":"answered","status":"insufficient_evidence"}',
                    '{"status":"answered","answer":NaN,"citations":[]}',
                    '{"status":"answered","answer":Infinity,"citations":[]}',
                    json.dumps(self.answer) + ' trailing prose'):
            with self.subTest(raw=raw):
                result = self.validate(raw=raw)
                self.assertFalse(result['json_valid'])
                self.assertEqual(result['errors'], ['INVALID_JSON'])

    def test_schema_rejects_boolean_lines_extra_fields_and_wrong_types(self):
        changes = [
            lambda a: a.update(extra='unapproved'),
            lambda a: a.update(answer=[]),
            lambda a: a.update(status='complete'),
            lambda a: a.update(citations={}),
            lambda a: a.update(answer='  '),
            lambda a: a['citations'][0].update(line_start=True),
            lambda a: a['citations'][0].update(line_end=2.0),
            lambda a: a['citations'][0].update(line_start=2, line_end=1),
            lambda a: a['citations'][0].update(extra='unapproved'),
            lambda a: a['citations'][0].update(quote=' '),
            lambda a: a['citations'][0].update(source_id=42),
        ]
        for i, change in enumerate(changes):
            with self.subTest(case=i):
                answer = copy.deepcopy(self.answer)
                change(answer)
                result = self.validate(raw=json.dumps(answer))
                self.assertTrue(result['json_valid'])
                self.assertFalse(result['schema_valid'])
                self.assertEqual(result['errors'], ['INVALID_ANSWER_SHAPE'])

    def test_changed_source_snapshot_cannot_validate_hash_or_quote(self):
        result = self.validate(sources={'manual': self.text + 'Changed.'})
        self.assertFalse(result['retrieval_evidence_gate'])
        self.assertEqual(result['citation_exactness']['score'], 0)
        self.assertFalse(result['end_to_end_quality_pass'])

    def test_ineligible_source_is_not_usable_even_if_quote_is_exact(self):
        self.rubric['sources']['manual']['eligible'] = False
        self.rubric['required_evidence'] = []
        result = self.validate()
        self.assertFalse(result['retrieval_evidence_gate'])
        self.assertFalse(result['citation_checks'][0]['exact_quote'])
        self.assertFalse(result['mechanical_gate'])

    def test_exact_quote_outside_supplied_evidence_is_not_accepted(self):
        self.answer['citations'][0].update(line_start=3, line_end=3, quote='wait... then proceed… safely.')
        result = self.validate(evidence=[dict(self.span, line_end=2)])
        self.assertTrue(result['retrieval_evidence_gate'])
        self.assertEqual(result['citation_exactness']['score'], 1)
        self.assertEqual(result['citations_in_supplied_evidence']['score'], 0)
        self.assertIn('CITATION_NOT_IN_SUPPLIED_EVIDENCE', result['errors'])
        self.assertFalse(result['end_to_end_quality_pass'])

    def test_missing_required_evidence_fails_despite_valid_answer_and_quote(self):
        self.answer['citations'][0].update(line_end=1, quote='The fictional tools are fetch and validate.')
        result = self.validate(evidence=[dict(self.span, line_end=1)])
        self.assertTrue(result['json_valid'])
        self.assertEqual(result['citation_exactness']['score'], 1)
        self.assertFalse(result['retrieval_evidence_gate'])
        self.assertIn('MISSING_OR_INVALID_SUPPLIED_EVIDENCE', result['errors'])
        self.assertFalse(result['end_to_end_quality_pass'])

    def test_adjacent_supplied_spans_can_cover_but_gap_cannot(self):
        supplied = [dict(self.span, line_end=1), dict(self.span, line_start=2, line_end=2)]
        self.assertTrue(self.validate(evidence=supplied)['mechanical_gate'])
        self.answer['citations'][0].update(line_end=3)
        result = self.validate(evidence=[dict(self.span, line_end=1), dict(self.span, line_start=3, line_end=3)])
        self.assertFalse(result['retrieval_evidence_gate'])
        self.assertEqual(result['citations_in_supplied_evidence']['score'], 0)

    def test_unknown_evidence_or_source_is_not_promoted_to_success(self):
        for arguments in ({'evidence': None}, {'sources': None}):
            with self.subTest(arguments=arguments):
                result = self.validate(**arguments)
                self.assertIsNone(result['retrieval_evidence_gate'])
                self.assertIsNone(result['mechanical_gate'])
                self.assertIsNone(result['end_to_end_quality_pass'])

    def test_frozen_unsupported_assertion_is_detected_without_keyword_blacklist(self):
        unsupported = 'The owner CLI handles approval flags.'
        self.answer['answer'] += ' THE OWNER CLI handles   approval flags.'
        result = self.validate(known_unsupported_sentences=[unsupported])
        self.assertEqual(result['known_unsupported_sentence_matches'], [0])
        self.assertIn('KNOWN_UNSUPPORTED_ASSERTION', result['errors'])
        self.assertFalse(result['mechanical_gate'])
        self.answer['answer'] = 'The documents do not establish whether the owner CLI handles approval flags.'
        result = self.validate(known_unsupported_sentences=[unsupported])
        self.assertEqual(result['known_unsupported_sentence_matches'], [])
        self.assertTrue(result['mechanical_gate'])
        self.assertIsNone(result['semantic_support'])
        self.assertIsNone(result['end_to_end_quality_pass'])

    def test_unknown_other_claim_stays_semantically_unreviewed(self):
        self.answer['answer'] = 'The fictional station can travel through time.'
        result = self.validate(known_unsupported_sentences=['The owner CLI handles approval flags.'])
        self.assertTrue(result['mechanical_gate'])
        self.assertIsNone(result['end_to_end_quality_pass'])
        self.assertIsNone(result['semantic_support'])

    def test_word_limit_and_required_citation_list_fail_closed(self):
        result = self.validate(max_words=2)
        self.assertFalse(result['word_limit_pass'])
        self.assertIn('WORD_LIMIT_EXCEEDED', result['errors'])
        self.answer['citations'] = []
        result = self.validate()
        self.assertIn('CITATIONS_REQUIRED', result['errors'])
        self.assertFalse(result['mechanical_gate'])

    def test_result_and_errors_do_not_echo_private_answer_content(self):
        sentinel = 'PRIVATE_SENTINEL_38f2_not_for_diagnostics'
        self.answer['answer'] = sentinel
        self.answer['citations'][0]['quote'] = sentinel
        serialized = json.dumps(self.validate())
        self.assertNotIn(sentinel, serialized)
        self.assertNotIn(self.text, serialized)
        invalid = self.validate(raw='{"answer":' + sentinel)
        self.assertNotIn(sentinel, json.dumps(invalid))
        self.assertEqual(invalid['errors'], ['INVALID_JSON'])

    def test_invalid_policy_is_content_free_quality_error(self):
        for policy in (None, 'private-policy', [None], [''], ['x'] * 33):
            with self.subTest(policy_type=type(policy).__name__):
                with self.assertRaises(QualityError) as caught:
                    self.validate(known_unsupported_sentences=policy)
                self.assertNotIn('private-policy', str(caught.exception))
        for maximum in (True, 0, 10001, '350'):
            with self.subTest(maximum=maximum):
                with self.assertRaises(QualityError):
                    self.validate(max_words=maximum)




if __name__ == '__main__':
    unittest.main()

# Two archived private-payload tests remain in the private history.
# All20 deterministic output validation tests remain; see PUBLIC_TEST_SCOPE.md.
