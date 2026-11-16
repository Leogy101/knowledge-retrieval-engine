"""Offline raw-answer checks, separate from retrieval and semantic review.

Trusted inputs are frozen source snapshots and spans actually supplied by the
host. No model calls, answer rewriting, file access or arbitrary-schema engine.
"""
from __future__ import annotations

import hashlib
import re

from .quality import (MAX_BYTES, QualityError, _all, _bounded, _metric, answer_hash,
                      rubric_hash, score_trial, strict_loads)

# A small fixed response shape; not a claim to implement general JSON Schema.
ANSWER_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['status', 'answer', 'citations'],
    'properties': {
        'status': {'type': 'string', 'enum': ['answered', 'insufficient_evidence']},
        'answer': {'type': 'string', 'minLength': 1, 'pattern': r'\S'},
        'citations': {'type': 'array', 'maxItems': 64, 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['source_id', 'line_start', 'line_end', 'quote'],
            'properties': {'source_id': {'type': 'string', 'minLength': 1},
                           'line_start': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
                           'line_end': {'type': 'integer', 'minimum': 1, 'maximum': 100000},
                           'quote': {'type': 'string', 'minLength': 1, 'pattern': r'\S'}}}},
    },
}


def _schema_ok(answer):
    if (type(answer) is not dict or answer.keys() != {'status', 'answer', 'citations'}
            or type(answer['status']) is not str
            or answer['status'] not in {'answered', 'insufficient_evidence'}
            or type(answer['answer']) is not str or not answer['answer'].strip()
            or type(answer['citations']) is not list or len(answer['citations']) > 64):
        return False
    return all(type(c) is dict and c.keys() == {'source_id', 'line_start', 'line_end', 'quote'}
               and type(c['source_id']) is str and bool(c['source_id'])
               and type(c['quote']) is str and bool(c['quote'].strip())
               and type(c['line_start']) is int and type(c['line_end']) is int
               and 1 <= c['line_start'] <= c['line_end'] <= 100_000
               for c in answer['citations'])


def validate_output(raw, rubric, *, sources, evidence, known_unsupported_sentences=(), max_words=350):
    """Fail closed on syntax, exact quotes and missing supplied evidence.

    Passing mechanical checks never proves semantic support. Known unsupported
    sentences are an optional frozen test oracle, not a hallucination detector.
    Return only hashes, counts, indices and fixed diagnostic codes, not content.
    Malformed trusted measurement inputs raise a content-free QualityError.
    """
    digest = rubric_hash(rubric)
    if (not isinstance(known_unsupported_sentences, (list, tuple))
            or len(known_unsupported_sentences) > 32
            or any(type(s) is not str or not s.strip() or len(s) > 4096 for s in known_unsupported_sentences)
            or type(max_words) is not int or not 1 <= max_words <= 10_000):
        raise QualityError('invalid output validation policy')
    _bounded(list(known_unsupported_sentences))
    if type(raw) is not str or len(raw) > MAX_BYTES:
        raise QualityError('invalid raw output')
    try:
        raw_bytes = raw.encode('utf-8')
        if len(raw_bytes) > MAX_BYTES:
            raise QualityError('invalid raw output')
        raw_hash = hashlib.sha256(raw_bytes).hexdigest()
    except UnicodeError:
        raise QualityError('invalid raw output') from None
    # Reuse existing frozen source eligibility, hash and required-span checks.
    observation = {'format': 'task-quality-observation/1', 'task_id': rubric['task_id'],
                   'task_sha256': rubric['task_sha256'], 'rubric_sha256': digest,
                   'completion': 'completed', 'evidence': evidence}
    if evidence is None:
        observation.pop('evidence')
    baseline = score_trial(rubric, observation, sources)
    evidence_valid = baseline['evidence_validity']
    validity = (None if evidence is None else
                None if evidence_valid['unknown'] else evidence_valid['passed'] == evidence_valid['total'])
    coverage = baseline['evidence_recall']
    covered = (None if coverage['unknown'] else coverage['passed'] == coverage['total'])
    evidence_gate = _all([validity, covered])
    result = {'format': 'kre-output-check/1', 'task_id': rubric['task_id'],
              'task_sha256': rubric['task_sha256'], 'rubric_sha256': digest,
              'raw_output_sha256': raw_hash, 'answer_sha256': None,
              'json_valid': False, 'schema_valid': None, 'word_limit_pass': None,
              'evidence_validity': evidence_valid, 'required_evidence': coverage,
              'retrieval_evidence_gate': evidence_gate, 'citation_checks': [],
              'citation_exactness': _metric(None), 'citations_in_supplied_evidence': _metric(None),
              'known_unsupported_sentence_matches': [], 'semantic_support': None,
              'frozen_quality_without_semantic_review': None,
              'mechanical_gate': False, 'end_to_end_quality_pass': False, 'errors': []}
    try:
        answer = strict_loads(raw)
    except QualityError:
        result['errors'] = ['INVALID_JSON']
        return result
    result.update(json_valid=True, answer_sha256=answer_hash(answer), schema_valid=_schema_ok(answer))
    if not result['schema_valid']:
        result['errors'] = ['INVALID_ANSWER_SHAPE']
        return result
    parsed_score = score_trial(rubric, dict(observation, answer=answer), sources)
    result['frozen_quality_without_semantic_review'] = parsed_score['quality_pass']
    result['word_limit_pass'] = len(raw.split()) <= max_words
    source_map = rubric.get('sources', {})

    def eligible_source(source_id):
        entry = source_map.get(source_id)
        text = sources.get(source_id) if sources is not None else None
        if not entry or not entry['eligible']:
            return False
        if text is None:
            return None
        return hashlib.sha256(text.encode('utf-8')).hexdigest() == entry['sha256']

    exactness, supplied = [], []
    for index, citation in enumerate(answer['citations']):
        source_id = citation['source_id']
        valid = eligible_source(source_id)
        start, end = citation['line_start'], citation['line_end']
        exact = valid
        if valid is True:
            lines = sources[source_id].splitlines(keepends=True)
            exact = end <= len(lines) and citation['quote'] in ''.join(lines[start-1:end])
        # A correct quotation from the full source is insufficient if its cited
        # span was never included in the captured model input. Adjacent supplied
        # spans may jointly cover it; unseen gaps may not.
        present = None if evidence is None or valid is None else False
        if evidence is not None and valid is True:
            positions = set()
            for span in evidence:
                if (span['source_id'] == source_id and span['source_sha256'] == source_map[source_id]['sha256']
                        and span['line_end'] <= len(lines)):
                    positions.update(range(max(start, span['line_start']), min(end, span['line_end'])+1))
            present = len(positions) == end-start+1
        exactness.append(exact)
        supplied.append(present)
        result['citation_checks'].append({'index': index, 'exact_quote': exact, 'in_supplied_evidence': present})
    result['citation_exactness'] = _metric(exactness)
    result['citations_in_supplied_evidence'] = _metric(supplied)
    # Match only complete, explicitly frozen unsupported assertions in answer
    # prose. No keyword blacklist or inference that every other claim is true.
    normalize = lambda s: ' '.join(s.split()).casefold()
    sentences = {normalize(s) for s in re.split(r'(?<=[.!?])\s+', answer['answer'])}
    matches = [i for i, s in enumerate(known_unsupported_sentences) if normalize(s) in sentences]
    result['known_unsupported_sentence_matches'] = matches
    any_required = rubric.get('citations', {}).get('require_any', False)
    mechanical = _all([evidence_gate, result['word_limit_pass'],
                       bool(exactness) if any_required else True,
                       *exactness, *supplied, not matches])
    result['mechanical_gate'] = mechanical
    result['end_to_end_quality_pass'] = False if mechanical is False or parsed_score['quality_pass'] is False else None
    if parsed_score['quality_pass'] is False:
        result['errors'].append('FROZEN_CRITERION_FAILED')
    if evidence_gate is False:
        result['errors'].append('MISSING_OR_INVALID_SUPPLIED_EVIDENCE')
    if not result['word_limit_pass']:
        result['errors'].append('WORD_LIMIT_EXCEEDED')
    if any_required and not exactness:
        result['errors'].append('CITATIONS_REQUIRED')
    if False in exactness:
        result['errors'].append('QUOTE_NOT_EXACT')
    if False in supplied:
        result['errors'].append('CITATION_NOT_IN_SUPPLIED_EVIDENCE')
    if matches:
        result['errors'].append('KNOWN_UNSUPPORTED_ASSERTION')
    return result
