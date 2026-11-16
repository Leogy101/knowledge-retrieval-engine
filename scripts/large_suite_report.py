"""Offline collection of every scheduled arm, including failures/not-started arms.

No model calls, answer repair, retrieval queries or semantic judge. Human review
remains pending; apply_review in large_suite_scoring handles later attestations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0,str(Path(__file__).parent))
import large_suite as suite
import large_suite_scoring as scoring


def collect(run, fixture=suite.FIXTURE):
    run,fixture=Path(run),Path(fixture)
    docs,tasks,sources=suite.load_fixture(fixture)
    protocol=suite.read(fixture/'protocol.json')
    plan=suite.schedule(tasks,protocol);by_task={t['id']:t for t in tasks};by_doc={d['id']:d for d in docs}
    rows=[];blind=[];errors=[]
    expected={f"arm-{row['ordinal']:03}" for row in plan}
    unexpected=sorted(p.name for p in run.glob('arm-*') if p.name not in expected)
    if unexpected:raise ValueError('Unscheduled arm directories present; do not drop them')
    for planned in plan:
        folder=run/f"arm-{planned['ordinal']:03}";task=by_task[planned['task_id']]
        path=folder/'receipt.json';receipt=suite.read(path) if path.exists() else None
        row={**planned,'category':task['category'],'state':'not_started','attempts':[],
             'completion_seconds':None,'retrieval_seconds':None,'quality_pass':None,
             'measurement_errors':[],'quality_score':None}
        if receipt is None:
            rows.append(row);continue
        for key in ('ordinal','pair_id','task_id','model','condition','baseline_type'):
            if receipt.get(key)!=planned[key]:raise ValueError('Receipt/schedule identity mismatch')
        row.update(state=receipt['state'],attempts=receipt['attempts'],
                   completion_seconds=receipt.get('completion_seconds'),
                   retrieval_seconds=receipt.get('details',{}).get('retrieval_seconds'),
                   context_preparation_seconds=receipt.get('context_preparation_seconds'),
                   submitted_message_text_bytes=receipt.get('submitted_message_text_bytes'),
                   context_bytes=receipt.get('context_bytes'),
                   inference_seconds=receipt.get('inference_seconds'),
                   native_load_duration=receipt.get('load_duration'),restored=receipt.get('restored'))
        answer_path=folder/'answer.txt';request_path=folder/'request.json'
        raw=answer_path.read_text() if answer_path.exists() else None
        if raw is not None:
            blind.append({'run_id':folder.name,'task_id':task['id'],'raw_output':raw,
                          'model':planned['model'],'condition':planned['condition']})
        if receipt['attempts']:
            try:
                wire=request_path.read_bytes()
                if suite.digest(wire)!=receipt.get('request_sha256'):raise ValueError('request hash mismatch')
                request=json.loads(wire)
                if (set(request)!={'model','messages','think','stream','options','truncate','shift'}
                    or request['model']!=planned['model'] or request['think'] is not False
                    or request['stream'] is not False or request['truncate'] is not False or request['shift'] is not False
                    or request['options']!=protocol['options']):raise ValueError('request configuration mismatch')
                messages=request['messages']
                if len(messages)!=2 or any(set(m)!={'role','content'} or m['role']!='user' or not isinstance(m['content'],str) for m in messages):raise ValueError('request message shape mismatch')
                row['prompt_sha256']=suite.digest(messages[1]['content'].encode())
                checkpoint,_=suite.recover_checkpoint(task,docs,sources,'disabled')
                if messages[1]['content']!=suite.task_message(task,checkpoint):raise ValueError('frozen task instruction mismatch')
                body=messages[0]['content']
                if not body.startswith(suite.PREFIX) or not body.endswith(suite.SUFFIX):raise ValueError('context wrapper mismatch')
                context=body[len(suite.PREFIX):-len(suite.SUFFIX)]
                items=json.loads(context)
                for item in items:
                    d=by_doc[item['source_id']]
                    if not suite.eligible(d,task['scope']) or item['source_sha256']!=d['sha256']:raise ValueError('ineligible context source')
                    start,end=item['line_start'],item['line_end'];lines=sources[d['id']].splitlines(keepends=True)
                    if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(lines):raise ValueError('context locator mismatch')
                    span=''.join(lines[start-1:end])
                    if item['text'] not in (span,span.removesuffix('\n')):raise ValueError('context text mismatch')
                    if item!=suite.packet(d,item['text'],start,end):raise ValueError('source packet metadata mismatch')
                if suite.evidence(items)!=receipt['evidence']:raise ValueError('supplied evidence mismatch')
                if planned['condition']=='disabled' and planned['baseline_type']=='complete_documents':
                    complete=[suite.packet(d,sources[d['id']],1,len(sources[d['id']].splitlines()))
                              for d in sorted(docs,key=lambda d:d['id']) if suite.eligible(d,task['scope'])]
                    if items!=complete:raise ValueError('complete-document baseline omitted eligible material')
                elif len(context.encode())>protocol['selection_budget']['max_bytes'] or len(items)>protocol['selection_budget']['max_items']:
                    raise ValueError('fixed context budget exceeded')
                if len(context.encode())!=receipt['context_bytes']:raise ValueError('context byte count mismatch')
                if len(wire)!=receipt['http_json_body_bytes']:raise ValueError('request byte count mismatch')
                message_bytes=sum(len(m['content'].encode()) for m in messages)
                if message_bytes!=receipt['submitted_message_text_bytes']:raise ValueError('submitted bytes mismatch')
                if len(suite.encoded(messages))!=receipt['messages_serialized_bytes']:raise ValueError('serialized message bytes mismatch')
                if message_bytes+protocol['options']['num_predict']+protocol['chat_template_reserve']>protocol['options']['num_ctx']:
                    raise ValueError('complete prompt admission bound exceeded')
                row['prompt_sha256']=suite.digest(messages[1]['content'].encode())
                if raw is not None:
                    if suite.digest(raw.encode())!=receipt.get('answer_sha256'):raise ValueError('answer hash mismatch')
                    native=suite.read(folder/'response.json')
                    if native.get('message',{}).get('content')!=raw:raise ValueError('raw answer differs from response')
                    if len(receipt['attempts'])!=1:raise ValueError('approved one-attempt bound violated')
                    attempt=receipt['attempts'][0]
                    for key,native_key in [('input_tokens','prompt_eval_count'),('output_tokens','eval_count'),('cached_tokens','prompt_eval_cached_count')]:
                        v=native.get(native_key);v=v if type(v) is int and v>=0 else None
                        if attempt.get(key)!=v:raise ValueError('native usage mismatch')
                    scoped=[dict(d,eligible=suite.eligible(d,task['scope'])) for d in docs if d['scope']==task['scope']]
                    score=scoring.score_output(raw,task,scoped,sources,receipt['evidence'],row['prompt_sha256'])
                    row['quality_score']=score;row['quality_pass']=score['overall_quality_pass']
                if receipt['state']!='completed':row['quality_pass']=False
            except (ValueError,KeyError,TypeError,OSError) as error:
                row['measurement_errors'].append(str(error));row['quality_pass']=False
                # Preserve all counters for diagnosis, never present suspect totals as complete.
                row['attempts']=[dict(a,usage_final=False) for a in row['attempts']]
        elif raw is not None:
            row['measurement_errors'].append('answer without a recorded attempt');row['quality_pass']=False
        rows.append(row)
    # Matched tasks must have identical actual instructions; never omit mismatch.
    paired={}
    for row in rows:
        if row.get('prompt_sha256'):paired.setdefault(row['pair_id'],[]).append(row)
    for group in paired.values():
        if len({r['prompt_sha256'] for r in group})>1:
            for r in group:
                r['measurement_errors'].append('paired task instruction mismatch');r['quality_pass']=False
                r['attempts']=[dict(a,usage_final=False) for a in r['attempts']]
    return {'format':'large-suite-collected/1','scheduled_arms':len(plan),'records':rows,
            'summary':scoring.summarize_pairs(rows),'independent_human_review':'pending',
            'blind_records':blind,'tasks':by_task,'sources':sources,'documents':docs}


def write_report(run,output,fixture=suite.FIXTURE):
    result=collect(run,fixture);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    bundle=scoring.make_blind_bundle(result.pop('blind_records'),result.pop('tasks'),result.pop('sources'),
                                    secrets.token_hex(32),documents=result.pop('documents'))
    suite.write(output/'results.json',result)
    suite.write(output/'blind-review.json',bundle['public'])
    private=output/'private';private.mkdir(mode=0o700)
    key=private/'unblinding-key.json'
    with os.fdopen(os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as handle:
        json.dump(bundle['private_key'],handle,indent=2);handle.write('\n')
    rows=['KRE Large Suite Results','',
          'All scheduled arms are retained. Semantic quality remains unknown pending independent blinded human review. No answer repair or inference is performed by this report.',
          '', '| Model | Baseline type | Pairs | Fully measured | Disabled tokens | Enabled tokens | Reduction | Quality-preserving pairs |',
          '|---|---|---:|---:|---:|---:|---:|---:|']
    show=lambda v:'Unknown' if v is None else str(v)
    for group in result['summary']['groups']:
        if 'category' in group:continue
        metric=group['observed_total_tokens']
        rows.append(f"| {group['model']} | {group['baseline_type']} | {group['pairs']} | {group['fully_measured_pairs']} | {show(metric['disabled'])} | {show(metric['enabled'])} | {show(metric['reduction_percent'])} | {group['quality_preserving_pairs']} |")
    rows += ['', 'Individual arms, attempts, native-accounting coverage, preparation/inference timing, citation checks, evidence-group coverage and canonical span recall are in results.json. Missing measurements remain unknown.',
             '', 'Do not combine complete-document and retrieval-baseline totals into one savings claim. Negative reduction is regression. The both-quality-pass subset is selected and cannot establish whole-suite efficacy.',
             '', 'Give reviewers blind-review.json only. Keep private/unblinding-key.json, raw run directories and results.json concealed until reviews are locked. Raw answer style may still reveal clues. No independent human review has been fabricated.',
             '', 'Charts should plot measured tokens and quality by model and baseline type after inference; no synthetic chart is presented as real performance.']
    (output/'report.md').write_text('\n'.join(rows)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,default=suite.FIXTURE)
    args=parser.parse_args();result=write_report(args.run,args.output,args.fixture)
    print(json.dumps({'scheduled_arms':result['scheduled_arms'],'output':str(args.output),'inference_calls':0}))


if __name__=='__main__':main()
