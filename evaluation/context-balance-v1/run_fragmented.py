"""First offline comparison on frozen fragmented-source cases; no inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(args):
    repo, experiments, fixture = args.repo.resolve(), args.experiments.resolve(), args.fixture.resolve()
    assert sha(fixture) == '40c653a4d5a6f745f18444385cb872450259dd8ca41ad889ab2d4c292845fa2f'
    lock = json.loads((experiments / 'EXPERIMENT_LOCK.json').read_text())
    for name, expected in lock['files'].items():
        assert sha(experiments / name) == expected
    assert sha(repo / 'src/kre/ingestion.py') == '16dd33a740fcc60980020646f5444d06000079cbb74aeeba1d51ec21f703d6b1'
    if args.output.exists():
        raise ValueError('Refuse to overwrite a prior run')
    args.output.mkdir(parents=True)
    data = json.loads(fixture.read_text())
    # Source-author intent was clarified before any retrieval. Original fixture
    # and its unsupported reference-only exclusion expectation stay unchanged.
    translations = {'freshness': {'current': 'fresh', 'stale': 'stale', 'unknown': 'unknown'},
                    'authority': {'primary': 'authoritative', 'secondary': 'unverified', 'draft': 'unverified', 'unreviewed': 'unverified'},
                    'destination': {'public': 'approved_remote', 'local': 'local_only'},
                    'purpose': {'answer_question': 'current_answer'},
                    'reference_only': 'active unverified source; author confirms not revoked/superseded',
                    'origin': 'synthetic URI retained as display_uri; source_evidence classification'}
    protocol = {'started_utc': datetime.now(timezone.utc).isoformat(), 'fixture_sha256': sha(fixture),
                'runner_sha256': sha(Path(__file__)), 'experiment_lock': lock, 'metadata_translation': translations,
                'unknown_expectations': ['fragmented-04 excludes active unverified seed-tips; no native authority-only eligibility control'],
                'no_gold_in_selection': True, 'inference_calls': 0, 'warm_repetitions': 5}
    (args.output / 'PROTOCOL.json').write_text(json.dumps(protocol, indent=2)+'\n')
    sys.path[:0] = [str(repo / 'src'), str(experiments)]
    import kre.store as native
    from variants import CHUNKERS
    scopes = {k: set(data['access_policy'][k]) for k in ['reader', 'owner']}
    sources = {s['source_id']: s for s in data['sources']}
    results, layouts = [], {}
    with patch('socket.socket', side_effect=AssertionError('No network in offline comparison')):
        for variant, chunker in CHUNKERS.items():
            with patch.object(native, 'chunks', chunker), native.Store(':memory:', principal='offline', scopes=scopes,
                    destinations=frozenset({'local_only', 'approved_remote'})) as store:
                for source in data['sources']:
                    assert hashlib.sha256(source['text'].encode()).hexdigest() == source['sha256']
                    store.ingest_text(source['source_id'], source['text'], collection=source['collection'],
                                      freshness=translations['freshness'][source['freshness']],
                                      authority=translations['authority'][source['authority']], origin='source_evidence',
                                      egress='approved_remote' if 'public' in source['allowed_destinations'] else 'local_only',
                                      _display_uri=source['origin'])
                    if source['state'] in {'revoked', 'superseded'}:
                        store.lifecycle(source['source_id'], {'revoked': 'revoke', 'superseded': 'supersede'}[source['state']])
                    else:
                        assert source['state'] in {'active', 'reference_only'}
                layouts[variant] = [dict(row) for row in store.db.execute('SELECT r.source_id,c.line_start,c.line_end,c.text FROM chunks c JOIN revisions r ON r.revision_id=c.revision_id ORDER BY c.id')]
                for case in data['cases']:
                    request = {'contract_version': '0.1', 'request_id': case['id'], 'query': case['query'],
                               'access_scope_ref': case['scope'], 'purpose': translations['purpose'][case['purpose']],
                               'destination': translations['destination'][case['destination']], 'budget': case['budget']}
                    response = store.context(request)
                    valid = store.validate_context(response, scope_ref=case['scope'], destination=request['destination'])
                    if response['error']:
                        assert not response['items'] and not response['context_text']
                    else:
                        assert valid == 'current'
                    items = response['items']
                    for item in items:
                        source = sources[item['source_id']]
                        start, end = item['locator']['line_start'], item['locator']['line_end']
                        assert item['text'] == '\n'.join(source['text'].split('\n')[start-1:end])
                        assert item['content_sha256'] == hashlib.sha256(item['text'].encode()).hexdigest()
                        assert source['collection'] in scopes[case['scope']]
                        assert source['state'] in {'active', 'reference_only'} and source['freshness'] != 'stale'
                        assert case['destination'] in source['allowed_destinations']
                        assert item['authority'] == translations['authority'][source['authority']]
                        assert item['freshness'] == translations['freshness'][source['freshness']]
                        assert item['origin'] == 'source_evidence'
                    size = len(response['context_text'].encode())
                    assert size == response['token_usage']['context_bytes'] == response['token_usage']['estimated_tokens']
                    assert size <= min(case['budget']['max_bytes'], case['budget']['max_tokens'])
                    assert len(items) <= case['budget']['max_items']
                    gold = []
                    for span in case['gold']:
                        source = sources[span['source_id']]
                        assert span['quote'] == '\n'.join(source['text'].split('\n')[span['line_start']-1:span['line_end']])
                        wanted = set(range(span['line_start'], span['line_end']+1))
                        supplied = set()
                        for item in items:
                            if item['source_id'] == span['source_id']:
                                supplied.update(range(item['locator']['line_start'], item['locator']['line_end']+1))
                        gold.append({'source_id': span['source_id'], 'line_start': span['line_start'], 'line_end': span['line_end'], 'covered': wanted <= supplied})
                    selected = {i['source_id'] for i in items}
                    gold_sources = {g['source_id'] for g in case['gold']}
                    contextual = set(case['relevance']['contextual_sources'])
                    unknown = ['seed-tips'] if case['id'] == 'fragmented-04' else []
                    forbidden = selected & (set(case['forbidden_sources']) - set(unknown))
                    assert not forbidden
                    store.context(request)
                    times = []
                    for _ in range(5):
                        begin = time.perf_counter_ns(); store.context(request); times.append((time.perf_counter_ns()-begin)/1e6)
                    results.append({'variant': variant, 'case_id': case['id'], 'budget_class': case['budget_class'],
                                    'request': request, 'response': response, 'native_validation': valid,
                                    'gold': gold, 'covered': sum(g['covered'] for g in gold), 'required': len(gold),
                                    'context_bytes': size, 'conservative_estimated_tokens': size, 'actual_model_tokens': None,
                                    'items': len(items), 'exact_citations': len(items), 'source_policy_violations': 0,
                                    'selected_sources': sorted(selected), 'gold_sources': sorted(gold_sources),
                                    'selected_gold_sources': len(selected & gold_sources),
                                    'selected_contextual_sources': len(selected & contextual),
                                    'unknown_exclusion_expectations': unknown,
                                    'unknown_exclusion_sources_present': sorted(selected & set(unknown)),
                                    'latency_samples_ms': times})
    summaries = []
    for variant in CHUNKERS:
        rows = [r for r in results if r['variant'] == variant]
        times = sorted(t for r in rows for t in r['latency_samples_ms'])
        summaries.append({'variant': variant, 'cases': len(rows), 'covered': sum(r['covered'] for r in rows),
                          'required': sum(r['required'] for r in rows),
                          'complete_cases': sum(r['covered'] == r['required'] for r in rows),
                          'context_bytes': sum(r['context_bytes'] for r in rows),
                          'conservative_estimated_tokens': sum(r['conservative_estimated_tokens'] for r in rows),
                          'items': sum(r['items'] for r in rows), 'exact_citations': sum(r['exact_citations'] for r in rows),
                          'errors': [r['case_id'] for r in rows if r['response']['error']],
                          'source_precision_proxy': sum(r['selected_gold_sources'] for r in rows)/sum(len(r['selected_sources']) for r in rows),
                          'warm_p50_ms': statistics.median(times), 'warm_p95_ms': times[37],
                          'source_policy_violations': 0, 'semantic_quality': None})
    artifact = {'protocol': protocol, 'summary': summaries, 'layouts': layouts, 'cases': results}
    (args.output / 'results.json').write_text(json.dumps(artifact, indent=2)+'\n')
    manifest = {p.name: sha(p) for p in args.output.iterdir() if p.is_file()}
    (args.output / 'SHA256_MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['repo', 'experiments', 'fixture', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    main(p.parse_args())
