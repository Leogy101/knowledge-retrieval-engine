"""Offline known-case comparison of predeclared chunkers. No model/network use."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from variants import CHUNKERS, DESCRIPTIONS


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values, fraction):
    import math
    return sorted(values)[math.ceil(len(values)*fraction)-1] if values else None


def main(args):
    freeze = json.loads((HERE/'EXPERIMENT_LOCK.json').read_text())
    for name, expected in freeze['files'].items():
        assert sha(HERE/name) == expected, 'Locked experiment changed: ' + name
    if args.output.exists():
        raise ValueError('Refuse to replace existing comparison')
    args.output.mkdir(parents=True)
    repo = args.repo.resolve()
    sys.path[:0] = [str(repo/'src'), str(repo/'scripts')]
    import kre.store as store_module
    suite = load('known_suite', repo/'scripts/large_suite.py')
    scoring = load('known_scoring', repo/'scripts/compare_post96_retrieval.py')
    prior = load('prior_evaluation', repo/'scripts/evaluate.py')
    docs, tasks, sources = suite.load_fixture()
    protocol = suite.read(suite.FIXTURE/'protocol.json')
    by_id = {d['id']: d for d in docs}
    results = []
    previous = []
    original_chunks = store_module.chunks
    try:
        for name, chunker in CHUNKERS.items():
            store_module.chunks = chunker
            with suite.make_store(docs, sources) as store:
                baseline = suite.WindowBaseline(docs, sources)
                try:
                    for budget in freeze['known_native_budgets']:
                        settings = dict(protocol, selection_budget=dict(protocol['selection_budget'], max_bytes=budget))
                        for task in tasks:
                            ctx = suite.contexts(task, docs, sources, store, baseline, settings, conditions=('enabled',))['enabled']
                            details = ctx['details']
                            packets = json.loads(ctx['messages'][0]['content'][len(suite.PREFIX):-len(suite.SUFFIX)])
                            exact = all(item['text']=='\n'.join(sources[item['source_id']].split('\n')[item['line_start']-1:item['line_end']])
                                        and item['content_sha256']==hashlib.sha256(item['text'].encode()).hexdigest()
                                        and suite.eligible(by_id[item['source_id']], task['scope']) for item in packets)
                            assert exact
                            assert details['native_context_bytes'] <= budget
                            assert len(packets) <= settings['selection_budget']['max_items']
                            assert details['native_error'] is None or details['native_error']['code']=='BUDGET_TOO_SMALL'
                            if details['native_error'] is None: assert details['validation']=='current'
                            coverage = scoring.evidence_coverage(task, ctx['evidence'])
                            gold_sources = {span['source_id'] for span in task['required_evidence']}
                            for group in task.get('evidence_groups', []):
                                for alt in group['alternatives']:
                                    gold_sources.update(span['source_id'] for span in alt['spans'])
                            selected_sources = {item['source_id'] for item in packets}
                            relevant_sources = selected_sources & gold_sources
                            request = {'contract_version':'0.1','request_id':task['id'],'query':task['question'],
                                       'access_scope_ref':task['scope'],'destination':'local_only','purpose':'current_answer',
                                       'freshness_requirement':'allow_unknown',
                                       'budget':{'max_bytes':budget,'max_tokens':budget,'max_items':16}}
                            store.context(request)  # warm timing sample, not extra inference
                            times=[]
                            for _ in range(freeze['warm_repetitions']):
                                start=time.perf_counter_ns(); store.context(request); times.append((time.perf_counter_ns()-start)/1e6)
                            results.append({'variant':name,'budget_bytes':budget,'task_id':task['id'],
                                            'baseline_type':ctx['baseline_type'],'coverage':coverage,
                                            'context_bytes':ctx['context_bytes'],
                                            'submitted_message_bytes':ctx['submitted_message_text_bytes'],
                                            'native_context_bytes':details['native_context_bytes'],
                                            'conservative_estimated_tokens':details['native_context_bytes'],
                                            'items':len(packets),'exact_citations':len(packets),
                                            'selected_sources':sorted(selected_sources),'reference_gold_sources':sorted(gold_sources),
                                            'relevant_sources':len(relevant_sources),'source_precision_proxy':len(relevant_sources)/len(selected_sources) if gold_sources and selected_sources else None,
                                            'native_status':details['native_status'],'error':details['native_error'],'omissions':details['omissions'],
                                            'selected':ctx['evidence'],'latency_samples_ms':times,
                                            'checks':{'source_lines_and_hashes_exact':exact,'native_validation':details['validation'],
                                                      'budget_and_items_within_original_cap':True,'source_eligibility_correct':True}})
                finally:
                    baseline.close()
            report=prior.evaluate('all',repetitions=freeze['warm_repetitions'])
            summary=report['summary']['kre']
            previous.append({'variant':name,'summary':summary,'corpus_chunks':report['corpus_chunks'],
                             'cases':[{'case_id':c['case_id'],'required_expectation':c['required_expectation'],
                                       **c['algorithms']['kre']['metrics']} for c in report['cases']]})
    finally:
        store_module.chunks=original_chunks
    aggregates=[]
    for name in CHUNKERS:
        for budget in freeze['known_native_budgets']:
            rows=[r for r in results if r['variant']==name and r['budget_bytes']==budget]
            positive=[r for r in rows if r['reference_gold_sources']]
            times=[t for r in rows for t in r['latency_samples_ms']]
            aggregates.append({'variant':name,'budget_bytes':budget,'cases':len(rows),
                               'covered_groups':sum(r['coverage']['passed'] for r in rows),'gold_groups':sum(r['coverage']['total'] for r in rows),
                               'complete_cases':sum(r['coverage']['passed']==r['coverage']['total'] for r in rows),
                               'context_bytes':sum(r['context_bytes'] for r in rows),'native_context_bytes':sum(r['native_context_bytes'] for r in rows),
                               'items':sum(r['items'] for r in rows),'exact_citations':sum(r['exact_citations'] for r in rows),
                               'errors':sum(r['error'] is not None for r in rows),
                               'micro_source_precision_proxy':sum(r['relevant_sources'] for r in positive)/sum(len(r['selected_sources']) for r in positive),
                               'warm_p50_ms':statistics.median(times),'warm_p95_ms':percentile(times,.95)})
    artifact={'format':'kre-context-balance-known/1','inference_calls':0,'experiment_lock':freeze,
              'descriptions':DESCRIPTIONS,'summary':aggregates,'cases':results,'prior_28':previous,
              'limitations':['Known cases are diagnostic, not independent generalization evidence.',
                             'Only gold-labelled source precision is measured; nongold text may still be relevant context.',
                             'Conservative estimated tokens equal native UTF8 bytes, not actual model usage.',
                             'Warm timing repeats are local query-only measurements; no cold process, adapter or model time.',
                             'No gold spans/source filters/required hints enter known24 retrieval requests.',
                             'Prior28 keeps frozen explicit required refs and controls; each candidate builds refs from its immutable chunks.']}
    (args.output/'results.json').write_text(json.dumps(artifact,indent=2)+'\n')
    print(json.dumps(aggregates,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args())
