"""Small offline scoring, blind human review and paired-report helpers.

No inference, network, answer repair, retrieval tuning or semantic model judge.
Every attempt is retained. Unknown usage and human judgments stay unknown.
See public function docstrings for the deliberately small record formats.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from typing import Any

from kre.output_validation import validate_output
from kre.quality import QualityError


class ReviewError(ValueError):
    """Malformed or mismatched trusted review record; no answer text in errors."""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def build_rubric(task: dict, documents: list[dict], prompt_sha256: str) -> dict:
    """Bind frozen task expectations to the actual transmitted shared prompt.

    Callers provide same-scope document metadata with optional explicit eligible
    flags. Default eligibility excludes revoked/superseded/stale documents.
    Required spans use immutable source IDs and hashes, never mutable paths.
    """
    required = [{k: span[k] for k in ('source_id', 'source_sha256', 'line_start', 'line_end')}
                for span in task['required_evidence']]
    return {
        'format': 'task-quality-rubric/1', 'task_id': task['id'],
        'task_sha256': prompt_sha256,
        'criteria': [{'id': 'status', 'category': 'correctness', 'critical': True,
                      'method': 'exact', 'path': ['status'], 'expected': task['expected_status']}],
        'sources': {d['id']: {'sha256': d['sha256'],
                    'eligible': d.get('eligible', d.get('status', 'active') == 'active'
                                      and d.get('freshness', 'unknown') != 'stale')}
                    for d in documents},
        'required_evidence': required,
        'citations': {'require_any': bool(required), 'required_claims': []},
    }


def score_output(raw: str, task: dict, documents: list[dict], sources: dict[str, str],
                 supplied_evidence: list[dict] | None, prompt_sha256: str,
                 *, max_words: int = 600) -> dict:
    """Deterministic validation only; factual/semantic verdicts require review.

    Reference forbidden_claims are review questions, not fragile keyword bans.
    Schema, required evidence and exact quotations reuse accepted KRE checks.
    """
    rubric = build_rubric(task, documents, prompt_sha256)
    canonical = validate_output(raw, rubric, sources=sources, evidence=supplied_evidence,
                                max_words=max_words)
    result = canonical
    groups = task.get('evidence_groups')
    if groups is not None:
        selected = []
        for group in groups:
            alternatives = group['alternatives']
            if not alternatives:
                raise QualityError('empty evidence alternatives')
            def covered(alternative):
                if supplied_evidence is None:
                    return False
                for required in alternative['spans']:
                    positions = set()
                    for supplied in supplied_evidence:
                        if all(supplied[k] == required[k] for k in ('source_id','source_sha256')):
                            positions.update(range(max(supplied['line_start'],required['line_start']),
                                                   min(supplied['line_end'],required['line_end'])+1))
                    if not set(range(required['line_start'],required['line_end']+1)) <= positions:
                        return False
                return True
            chosen = next((a for a in alternatives if covered(a)), alternatives[0])
            selected.extend(chosen['spans'])
        chosen_task = dict(task, required_evidence=selected)
        result = validate_output(raw, build_rubric(chosen_task, documents, prompt_sha256),
                                 sources=sources, evidence=supplied_evidence, max_words=max_words)
    result['canonical_required_evidence'] = canonical['required_evidence']
    # Group totals are reported independently of canonical span totals.
    groups = groups if groups is not None else [
        {'id': str(i), 'alternatives': [{'spans': [span]}]} for i,span in enumerate(task['required_evidence'])]
    outcomes=[]
    for group in groups:
        if supplied_evidence is None:
            outcomes.append(None);continue
        alternatives=[]
        for alternative in group['alternatives']:
            checks=[]
            for required in alternative['spans']:
                check_task=dict(task,required_evidence=[required])
                check=validate_output(raw,build_rubric(check_task,documents,prompt_sha256),
                                      sources=sources,evidence=supplied_evidence,max_words=max_words)
                recall=check['required_evidence']
                checks.append(None if recall['unknown'] else recall['passed']==recall['total'])
            alternatives.append(False if False in checks else None if None in checks else True)
        outcomes.append(True if True in alternatives else None if None in alternatives else False)
    result['required_evidence_groups']={'passed':outcomes.count(True),'total':len(outcomes),
        'unknown':outcomes.count(None),'score':outcomes.count(True)/len(outcomes) if outcomes and None not in outcomes else None}
    deterministic = (False if result['end_to_end_quality_pass'] is False
                     else result['mechanical_gate'])
    result.update(deterministic_gate=deterministic, semantic_review=None,
                  overall_quality_pass=False if deterministic is False else None,
                  required_fact_ids=[fact['id'] for fact in task['required_facts']],
                  constraint_ids=[f'constraint-{i+1}' for i in range(len(task['constraints']))],
                  unsupported_claims=None, completion_correct=None)
    return result


def _count(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _metric(values: list[Any], final: list[bool]) -> dict:
    known = [value for value in values if _count(value)]
    complete = bool(values) and len(known) == len(values) and all(final)
    measured = sum(_count(value) and end for value, end in zip(values, final))
    coverage = ('fully_measured' if complete else 'unknown' if not known else 'partially_measured')
    return {'value': sum(known) if complete else None, 'known_sum': sum(known) if known else None,
            'coverage': coverage, 'attempts': len(values), 'final_measured_attempts': measured}


def aggregate_attempts(attempts: list[dict]) -> dict:
    """Aggregate all content attempts, including retries/failures/cancellations.

    Each attempt has state; input_tokens/output_tokens (native counters also
    accepted); optional cached_tokens/reasoning_tokens, billed_charge,
    estimated_cost, submitted_message_bytes, retry. usage_final explicitly
    indicates terminal usage, otherwise only state=='completed' is final.
    Missing categories stay unknown. Cached/reasoning tokens are never added
    to input+output totals. Lifecycle load/unload records belong separately.
    """
    if not isinstance(attempts, list) or any(not isinstance(a, dict) for a in attempts):
        raise ValueError('invalid attempt records')
    final = [a.get('usage_final', a.get('state') == 'completed') is True for a in attempts]
    inputs = [a.get('input_tokens', a.get('prompt_eval_count')) for a in attempts]
    outputs = [a.get('output_tokens', a.get('eval_count')) for a in attempts]
    inputs = [v if type(v) is int and v >= 0 else None for v in inputs]
    outputs = [v if type(v) is int and v >= 0 else None for v in outputs]
    totals = [i + o if _count(i) and _count(o) else None for i, o in zip(inputs, outputs)]
    result = {'model_requests': len(attempts), 'input_tokens': _metric(inputs, final),
              'output_tokens': _metric(outputs, final), 'total_tokens': _metric(totals, final),
              'states': {state: sum(a.get('state', 'unknown') == state for a in attempts)
                         for state in sorted({a.get('state', 'unknown') for a in attempts})},
              'retry_count': (sum(a['retry'] for a in attempts)
                              if all(type(a.get('retry')) is bool for a in attempts) else None)}
    for key in ('cached_tokens', 'reasoning_tokens', 'billed_charge', 'estimated_cost'):
        values = [a.get(key, a.get('prompt_eval_cached_count') if key == 'cached_tokens' else None) for a in attempts]
        if key in ('cached_tokens', 'reasoning_tokens'):
            values = [v if type(v) is int and v >= 0 else None for v in values]
        result[key] = _metric(values, final)
    # Bytes can be known even when an inference times out. Count repeats when
    # each transmitted attempt supplies the same context again.
    result['submitted_message_bytes'] = _metric(
        [a.get('submitted_message_bytes') for a in attempts], [True] * len(attempts))
    return result


def make_blind_bundle(records: list[dict], tasks: dict[str, dict], sources: dict[str, str],
                      seed: str, documents: list[dict] | None = None) -> dict:
    """Return separate public review material and a PRIVATE unblinding key.

    Records: run_id, task_id, raw_output, model, condition; other fields ignored.
    Keep seed and private_key away from reviewers. The public packet omits all
    model/condition/chronology/usage/context-selection fields. Raw answers are
    never edited; output style may still reveal clues, which must be disclosed.
    Reviewer sees the same reference answer and gold spans for either arm.
    """
    if not isinstance(seed, str) or len(seed) < 16:
        raise ReviewError('blind seed must be at least 16 characters')
    if len({r['run_id'] for r in records}) != len(records):
        raise ReviewError('duplicate trial identity')
    order = list(records)
    random.Random(seed).shuffle(order)
    packets, mapping = [], {}
    for r in order:
        task = tasks[r['task_id']]
        token = _sha(seed + '\x00' + r['run_id'])[:24]
        raw = r['raw_output']
        if not isinstance(raw, str):
            raise ReviewError('raw output must be a string')
        gold = []
        for span in task['required_evidence']:
            text = sources[span['source_id']]
            if _sha(text) != span['source_sha256']:
                raise ReviewError('reference source hash mismatch')
            lines = text.splitlines(keepends=True)
            if not 1 <= span['line_start'] <= span['line_end'] <= len(lines):
                raise ReviewError('invalid reference source span')
            selected = ''.join(lines[span['line_start']-1:span['line_end']])
            if not span.get('quote') or span['quote'] not in selected:
                raise ReviewError('invalid frozen reference quote')
            gold.append({**span, 'source_text': selected})
        packets.append({'blind_id': token, 'task_id': task['id'], 'question': task['question'],
                        'raw_output': raw, 'raw_output_sha256': _sha(raw),
                        'reference_answer': task['reference_answer'],
                        'required_facts': task['required_facts'], 'constraints': task['constraints'],
                        'forbidden_claims': task['forbidden_claims'], 'expected_status': task['expected_status'],
                        'reference_evidence': gold,
                        'evidence_groups': task.get('evidence_groups'),
                        'source_metadata': [d for d in (documents or []) if d.get('scope') == task.get('scope')],
                        'review_template': {'format': 'large-suite-human-review/1',
                            'blind_id': token, 'task_id': task['id'], 'raw_output_sha256': _sha(raw),
                            'reviewer_id': None, 'human': True, 'independent': True, 'blinded': True,
                            'facts': {f['id']: None for f in task['required_facts']},
                            'constraints': {f'constraint-{i+1}': None for i in range(len(task['constraints']))},
                            'citation_support': None, 'unsupported_claims': None,
                            'completion_correct': None, 'notes': ''}})
        mapping[token] = {key: r[key] for key in ('run_id', 'task_id', 'model', 'condition')}
    return {'public': {'format': 'large-suite-blind-review/1',
                       'instructions': 'Human review only. True/false/null verdicts. Preserve raw answers. '
                        'Judge every factual addition and citation against the frozen sources. '
                        'Record uncertainty; do not infer a pass from a correct keyword. '
                        'Output style may reveal condition clues despite concealed labels.',
                       'packets': packets,
                       'source_snapshots': dict(sources)},
            'private_key': {'format': 'large-suite-private-unblinding/1', 'seed': seed, 'mapping': mapping}}


def apply_review(score: dict, review: dict | None, task: dict) -> dict:
    """Combine mechanical checks with hash-bound independent human review.

    No review yields unknown semantics. Review shape is the blind template;
    citation_support must contain one bool/null for every emitted citation.
    Reviewer facts/constraints must exactly match the frozen required IDs.
    """
    result = dict(score)
    if review is None:
        return result
    if (review.get('format') != 'large-suite-human-review/1'
            or review.get('task_id') != task['id']
            or review.get('raw_output_sha256') != score['raw_output_sha256']
            or not isinstance(review.get('reviewer_id'), str) or not review['reviewer_id'].strip()
            or any(review.get(k) is not True for k in ('human', 'independent', 'blinded'))):
        raise ReviewError('review identity or independence mismatch')
    facts, constraints = review.get('facts'), review.get('constraints')
    expected_facts = {f['id'] for f in task['required_facts']}
    expected_constraints = {f'constraint-{i+1}' for i in range(len(task['constraints']))}
    if (not isinstance(facts, dict) or set(facts) != expected_facts
            or not isinstance(constraints, dict) or set(constraints) != expected_constraints):
        raise ReviewError('review criteria mismatch')
    supports = review.get('citation_support')
    expected_count = len(score.get('citation_checks', []))
    if supports is not None and (not isinstance(supports, list) or len(supports) != expected_count):
        raise ReviewError('review citation count mismatch')
    unsupported = review.get('unsupported_claims')
    if unsupported is not None and (not isinstance(unsupported, list)
                                   or any(not isinstance(s, str) or not s.strip() for s in unsupported)):
        raise ReviewError('invalid unsupported claims review')
    verdicts = list(facts.values()) + list(constraints.values())
    verdicts += [review.get('completion_correct')]
    verdicts += supports if supports is not None else [None]
    verdicts += [not unsupported if unsupported is not None else None]
    if any(v is not None and type(v) is not bool for v in verdicts):
        raise ReviewError('invalid review verdict')
    semantic = False if False in verdicts else None if None in verdicts else True
    mechanical = score['deterministic_gate']
    overall = False if False in (mechanical, semantic) else None if None in (mechanical, semantic) else True
    result.update(semantic_review=semantic, overall_quality_pass=overall,
                  unsupported_claims=unsupported, completion_correct=review.get('completion_correct'),
                  reviewed_facts=facts, reviewed_constraints=constraints,
                  reviewed_citation_support=supports, reviewer_id=review['reviewer_id'])
    return result


def _change(before: Any, after: Any) -> dict:
    valid = _count(before) and _count(after)
    return {'disabled': before, 'enabled': after,
            'difference': after-before if valid else None,
            'change_percent': (after-before)/before*100 if valid and before else None,
            'reduction_percent': (before-after)/before*100 if valid and before else None}


def summarize_pairs(records: list[dict]) -> dict:
    """Create descriptive results without pooling baseline types.

    Each arm record: pair_id, task_id, category, model, baseline_type,
    condition ('disabled'/'enabled'), attempts, completion_seconds,
    retrieval_seconds, quality_pass (bool/null). Same model/task/type/category
    required within pairs. Include missing/failed arms; never drop them.
    Report overall observed totals only if every arm has full measured usage;
    the separately selected quality-preserving subset needs BOTH quality
    passes and full usage and must not be advertised as whole-suite efficacy.
    """
    pairs = defaultdict(dict)
    for row in records:
        if row['condition'] not in ('disabled', 'enabled'):
            raise ValueError('invalid condition')
        if row['condition'] in pairs[row['pair_id']]:
            raise ValueError('duplicate arm; do not select a preferred attempt')
        if row.get('quality_pass') is not None and type(row['quality_pass']) is not bool:
            raise ValueError('invalid quality verdict')
        pairs[row['pair_id']][row['condition']] = row
    per_pair = []
    for pair_id, arms in sorted(pairs.items()):
        first = next(iter(arms.values()))
        if any(any(row[k] != first[k] for k in ('task_id', 'category', 'model', 'baseline_type')) for row in arms.values()):
            raise ValueError('noncomparable pair identity')
        measured = {arm: aggregate_attempts(row['attempts']) for arm, row in arms.items()}
        complete = len(arms) == 2 and all(m['total_tokens']['coverage'] == 'fully_measured' for m in measured.values())
        values = {arm: measured[arm]['total_tokens']['value'] if arm in arms else None for arm in ('disabled', 'enabled')}
        quality = {arm: arms[arm].get('quality_pass') if arm in arms else None for arm in ('disabled', 'enabled')}
        pair = {'pair_id': pair_id, **{k: first[k] for k in ('task_id', 'category', 'model', 'baseline_type')},
                'arms_present': len(arms), 'accounting': measured, 'usage_complete': complete,
                'quality': quality, 'quality_preserving_eligible': complete and all(v is True for v in quality.values()),
                'total_tokens': _change(values['disabled'], values['enabled']),
                'input_tokens': _change(*(measured.get(a, {}).get('input_tokens', {}).get('value') for a in ('disabled','enabled'))),
                'output_tokens': _change(*(measured.get(a, {}).get('output_tokens', {}).get('value') for a in ('disabled','enabled'))),
                'completion_seconds': _change(*(arms.get(a, {}).get('completion_seconds') for a in ('disabled','enabled'))),
                'retrieval_seconds': {a: arms.get(a, {}).get('retrieval_seconds') for a in ('disabled','enabled')}}
        per_pair.append(pair)
    grouped = []
    for fields in (('model', 'baseline_type'), ('model', 'baseline_type', 'category')):
        groups = defaultdict(list)
        for pair in per_pair:
            groups[tuple(pair[k] for k in fields)].append(pair)
        for key, rows in sorted(groups.items()):
            full = all(p['usage_complete'] for p in rows)
            selected = [p for p in rows if p['quality_preserving_eligible']]
            all_tokens = {a: sum(p['total_tokens'][a] for p in rows) if full else None for a in ('disabled','enabled')}
            qp_tokens = {a: sum(p['total_tokens'][a] for p in selected) if selected else None for a in ('disabled','enabled')}
            grouped.append({**dict(zip(fields, key)), 'pairs': len(rows),
                            'fully_measured_pairs': sum(p['usage_complete'] for p in rows),
                            'observed_total_tokens': _change(all_tokens['disabled'], all_tokens['enabled']),
                            'observed_input_tokens': _change(*(sum(p['input_tokens'][a] for p in rows) if full else None for a in ('disabled','enabled'))),
                            'observed_output_tokens': _change(*(sum(p['output_tokens'][a] for p in rows) if full else None for a in ('disabled','enabled'))),
                            'observed_completion_seconds': _change(*(sum(p['completion_seconds'][a] for p in rows)
                                if all(_count(p['completion_seconds'][a]) for p in rows) else None for a in ('disabled','enabled'))),
                            'retrieval_seconds': {a: {'known_sum': sum(p['retrieval_seconds'][a] for p in rows if _count(p['retrieval_seconds'][a])),
                                'measured_pairs': sum(_count(p['retrieval_seconds'][a]) for p in rows)} for a in ('disabled','enabled')},
                            'quality_preserving_pairs': len(selected),
                            'quality_preserving_total_tokens': _change(qp_tokens['disabled'], qp_tokens['enabled']),
                            'quality_counts': {a: {name: sum(p['quality'][a] is value for p in rows)
                                for name, value in (('pass',True),('fail',False),('unknown',None))} for a in ('disabled','enabled')}})
    return {'format': 'large-suite-paired-summary/1', 'pairs': per_pair, 'groups': grouped,
            'quality_subset_warning': 'Selected pairs with BOTH independent quality passes and complete usage; not overall efficacy.',
            'uncertainty': 'Descriptive finite-suite results. No statistical significance or population-generalization claim.'}
