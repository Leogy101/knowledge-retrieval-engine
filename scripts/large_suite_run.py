"""Bounded direct-loopback runner. Pending preparation is NEVER authorization.

One dispatch per scheduled arm; no retry/repair or generated code execution.
CLI requires an explicit later approval file matching the exact execution freeze.
Fake transports exercise this module offline; preparation never calls run_block.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import http.client
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).parent))
import large_suite as suite

HOST,PORT='127.0.0.1',11434
STOP_REQUESTED=False


def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()


def request_stop(signum=None,frame=None):
    global STOP_REQUESTED
    STOP_REQUESTED=True


def expired(signum,frame):raise TimeoutError('Best-effort arm deadline reached')


@contextlib.contextmanager
def deadline(seconds):
    previous=signal.signal(signal.SIGALRM,expired)
    signal.setitimer(signal.ITIMER_REAL,max(.001,seconds))
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)


class LocalTransport:
    def call(self,method,path,payload=None,*,timeout=3,receipt=None,raw_path=None):
        if (method,path) not in {('GET','/api/ps'),('GET','/api/tags'),('GET','/api/version'),('POST','/api/show'),('POST','/api/chat')}:
            raise ValueError('Endpoint not allowlisted')
        connection=http.client.HTTPConnection(HOST,PORT,timeout=timeout)
        try:
            connection.connect()
            if connection.sock.getpeername()!=(HOST,PORT):raise ValueError('Non-loopback transport')
            if receipt is not None:receipt['peer']={'address':HOST,'port':PORT}
            data=None if payload is None else suite.encoded(payload)
            connection.request(method,path,body=data,headers={} if data is None else {'Content-Type':'application/json'})
            response=connection.getresponse();raw=response.read(2_000_001)
            if raw_path is not None:Path(raw_path).write_bytes(raw)
            if receipt is not None:receipt['http_status']=response.status
            if response.status!=200 or len(raw)>2_000_000:raise ValueError('HTTP failure or oversized response; no retries')
            return json.loads(raw)
        finally:connection.close()


def inspect(transport,model,*,loaded=False,expected_version='0.40.15'):
    version=transport.call('GET','/api/version')['version']
    if version!=expected_version:raise ValueError('Ollama version drift')
    tags=transport.call('GET','/api/tags').get('models',[])
    rows=[m for m in tags if m.get('name')==model['name']]
    if len(rows)!=1 or rows[0].get('digest')!=model['digest']:raise ValueError('Model identity drift')
    details=rows[0].get('details',{})
    if any(details.get(native)!=model[key] for native,key in [('format','format'),('runner','runner'),('quantization_level','quantization')]):
        raise ValueError('Native backend or quantization drift')
    show=transport.call('POST','/api/show',{'model':model['name']})
    if any(data.get(key) for data in [rows[0],show] for key in ('remote_model','remote_host')):raise ValueError('Remote model forbidden')
    if not any(type(v) is bool and v is False for v in show.get('thinking',{}).get('values',[])):
        raise ValueError('think:false not supported by metadata')
    resident=transport.call('GET','/api/ps').get('models',[])
    if not loaded and resident:raise ValueError('Existing model residency; do not disturb workloads')
    if loaded and (len(resident)!=1 or resident[0].get('name')!=model['name'] or resident[0].get('digest')!=model['digest'] or resident[0].get('context_length')!=32768 or resident[0].get('remote_model') or resident[0].get('remote_host')):
        raise ValueError('Unexpected residency or context settings')
    return {'version':version,'model':model['name'],'digest':model['digest'],'details':rows[0].get('details'),
            'thinking':show.get('thinking'),'residency':resident}


def memory_guard(minimum_percent):
    # Read-only OS report; never allocate a stress probe or stop another process.
    value=subprocess.check_output(['/usr/bin/memory_pressure','-Q'],text=True,timeout=3)
    match=re.search(r'System-wide memory free percentage:\s*(\d+)%',value)
    if not match:raise ValueError('Memory headroom unavailable')
    percent=int(match.group(1))
    if percent<minimum_percent:raise ValueError('Insufficient approved memory headroom')
    return percent


def lifecycle(transport,model,options,kind,folder,timeout):
    payload={'model':model['name'],'messages':[],'think':False,'stream':False,'options':options,
             'keep_alive':'5m' if kind=='load' else 0}
    record={'kind':kind,'started_utc':utc(),'inference':False,'state':'started'}
    suite.write(folder/(kind+'-receipt.json'),record)
    (folder/(kind+'-request.json')).write_bytes(suite.encoded(payload))
    began=time.monotonic()
    try:
        response=transport.call('POST','/api/chat',payload,timeout=timeout,receipt=record,raw_path=folder/(kind+'-response.json'))
        record['response']=response
        if (response.get('model')!=model['name'] or response.get('done') is not True or response.get('done_reason')!=kind
                or any(response.get('message',{}).get(key) for key in ('content','thinking','tool_calls'))
                or any(response.get(key) not in (None,0) for key in ('prompt_eval_count','eval_count'))):
            raise ValueError('Unverified lifecycle behavior')
        record['state']='completed'
    except BaseException as error:
        record.update(state='unknown',error=type(error).__name__);raise
    finally:
        record.update(wall_seconds=time.monotonic()-began,finished_utc=utc())
        suite.write(folder/(kind+'-receipt.json'),record)
    return record


def execute_arm(row,model,protocol,folder,prepare,transport,*,guard=memory_guard,should_stop=None):
    """One reserved arm; lifecycle completion and inference completeness separate."""
    should_stop=should_stop or (lambda:STOP_REQUESTED)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    record={**row,'format':'kre-large-arm/1','state':'preflight','started_utc':utc(),
            'attempts':[],'retries':0,'repairs':0,'actual_billed_charge':None,'estimated_cost':None,
            'server_rendered_prompt_bytes':None,'terminal_observed':False,'restored':False}
    suite.write(folder/'receipt.json',record)
    terminal=False;load_confirmed=False;attempt=None;began=None
    try:
        record['before']=inspect(transport,model)
        record['headroom_percent']=guard(model['minimum_free_memory_percent'])
        began=time.monotonic()
        with deadline(model['arm_deadline_seconds']):
            lifecycle(transport,model,protocol['options'],'load',folder,model['arm_deadline_seconds'])
            load_confirmed=True
            record['loaded']=inspect(transport,model,loaded=True)
            record['loaded_headroom_percent']=guard(protocol['minimum_loaded_free_memory_percent'])
            if should_stop():raise InterruptedError('Stopped after preload; no content dispatch')
            context=prepare()
            if should_stop():raise InterruptedError('Stopped during preparation; no content dispatch')
            record.update({k:v for k,v in context.items() if k!='messages'})
            payload={'model':model['name'],'messages':context['messages'],'think':False,'stream':False,
                     'options':protocol['options'],'truncate':False,'shift':False}
            wire=suite.encoded(payload)
            (folder/'request.json').write_bytes(wire)
            record['request_sha256']=suite.digest(wire);record['http_json_body_bytes']=len(wire)
            attempt={'state':'started','usage_final':False,'retry':False,'input_tokens':None,'output_tokens':None,
                     'cached_tokens':None,'reasoning_tokens':None,'billed_charge':None,'estimated_cost':None,
                     'submitted_message_bytes':context['submitted_message_text_bytes'],'dispatch_utc':utc()}
            record['attempts']=[attempt]
            # Persist reservation before transport. Unknown dispatch is never retried.
            suite.write(folder/'receipt.json',record)
            remaining=model['arm_deadline_seconds']-(time.monotonic()-began)
            if remaining<=0:raise TimeoutError('No remaining arm time')
            call_started=time.monotonic()
            response=transport.call('POST','/api/chat',payload,timeout=remaining,receipt=attempt,raw_path=folder/'response.json')
            record['inference_seconds']=time.monotonic()-call_started
            terminal=response.get('done') is True
            record['terminal_observed']=terminal
            for native,key in [('prompt_eval_count','input_tokens'),('eval_count','output_tokens'),('prompt_eval_cached_count','cached_tokens')]:
                value=response.get(native)
                attempt[key]=value if type(value) is int and value>=0 else None
            if response.get('model')!=model['name'] or not terminal:raise ValueError('Unverified model or nonterminal response')
            attempt.update(usage_final=True,state='completed')
            for name in ('total_duration','load_duration','prompt_eval_duration','eval_duration'):
                v=response.get(name);record[name]=v if type(v) is int and v>=0 else None
            message=response.get('message',{});content=message.get('content')
            record['model_tool_calls']=len(message.get('tool_calls') or [])
            record['returned_thinking_bytes']=len((message.get('thinking') or '').encode())
            if not isinstance(content,str):raise ValueError('Missing response content')
            (folder/'answer.txt').write_text(content)
            record['answer_sha256']=suite.digest(content.encode());record['done_reason']=response.get('done_reason')
            if message.get('tool_calls') or message.get('thinking'):raise ValueError('Unexpected tools/thinking')
            if response.get('done_reason') not in ('stop','length'):raise ValueError('Unknown termination reason')
            if attempt['input_tokens'] is None or attempt['output_tokens'] is None:raise ValueError('Missing usage stops benchmark')
            if attempt['output_tokens']>protocol['options']['num_predict']:raise ValueError('Output limit not enforced')
            if attempt['input_tokens']+attempt['output_tokens']>protocol['options']['num_ctx']:raise ValueError('Context limit not enforced')
            # Length termination is an observed incomplete answer; never repair/retry.
            record['state']='completed' if response.get('done_reason')=='stop' else 'output_limit'
    except (Exception,KeyboardInterrupt) as error:
        record.update(state='stopped',error_type=type(error).__name__,error=str(error))
        if attempt is not None and attempt['state']=='started':attempt['state']='cancelled' if isinstance(error,(KeyboardInterrupt,InterruptedError)) else 'failed'
    finally:
        record['completion_seconds']=None if began is None else time.monotonic()-began
        # Known terminal response or no dispatched content permits safe lifecycle cleanup.
        # Unknown completion cannot trigger unload, kill, retry, or another arm.
        can_cleanup=load_confirmed and (terminal or attempt is None)
        if can_cleanup:
            try:
                with deadline(protocol['cleanup_deadline_seconds']):
                    inspect(transport,model,loaded=True)
                    lifecycle(transport,model,protocol['options'],'unload',folder,protocol['cleanup_deadline_seconds'])
                    record['after']=inspect(transport,model)
                record['restored']=True
            except Exception as error:
                record.update(state='stopped',cleanup_error=type(error).__name__)
        elif not load_confirmed and began is None:
            record['restored']=True  # No lifecycle operation dispatched.
        record['finished_utc']=utc();suite.write(folder/'receipt.json',record)
    return record


def verify_approval(approval,freeze,freeze_bytes):
    if (approval.get('status')!='approved' or approval.get('execution_freeze_sha256')!=suite.digest(freeze_bytes)
        or approval.get('maximum_content_calls')!=96 or approval.get('quiet_window_confirmed') is not True):
        raise ValueError('Exact later execution approval and quiet window required')
    for name,expected in freeze['files'].items():
        path=(suite.ROOT/name).resolve()
        if not path.is_relative_to(suite.ROOT) or suite.digest(path.read_bytes())!=expected:
            raise ValueError('Frozen execution inputs changed')


def run_block(folder,approval_path,output,block):
    folder,output=Path(folder),Path(output)
    if output.resolve() != (suite.ROOT/'.scratch/large-scale-v1-live').resolve():
        raise ValueError('Use the single frozen campaign output directory; no second campaign')
    freeze_bytes=(folder/'execution-freeze.json').read_bytes();freeze=json.loads(freeze_bytes)
    verify_approval(suite.read(approval_path),freeze,freeze_bytes)
    if block not in (1,2,3,4):raise ValueError('Unknown bounded block')
    docs,tasks,sources=suite.load_fixture(folder);protocol=suite.read(folder/'protocol.json')
    plan=suite.schedule(tasks,protocol)
    if len(plan)!=96:raise ValueError('Unexpected schedule')
    output.mkdir(parents=True,exist_ok=True)
    with (output/'run.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state_path=output/'run-state.json'
        if not state_path.exists():
            suite.write(state_path,{'execution_freeze_sha256':suite.digest(freeze_bytes),'created_utc':utc(),'deadline_epoch':time.time()+protocol['campaign_wall_limit_seconds']})
        state=suite.read(state_path)
        if state['execution_freeze_sha256']!=suite.digest(freeze_bytes):raise ValueError('Campaign freeze mismatch')
        if subprocess.check_output(['git','status','--porcelain'],cwd=suite.ROOT,text=True).strip():raise ValueError('Working tree not clean')
        # No skip-over of uncertain/failed attempts or incomplete earlier blocks.
        for row in plan:
            receipt=output/f"arm-{row['ordinal']:03}"/'receipt.json'
            if row['block']<block and (not receipt.exists() or suite.read(receipt)['state'] not in ('completed','output_limit')):
                raise ValueError('Earlier block incomplete')
            if receipt.exists() and suite.read(receipt)['state'] not in ('completed','output_limit'):
                raise ValueError('Prior uncertain or failed arm; no automatic resume')
        signal.signal(signal.SIGINT,request_stop)
        by_task={t['id']:t for t in tasks};by_model={m['id']:m for m in protocol['models']}
        build=time.perf_counter();store=suite.make_store(docs,sources);kre_setup=time.perf_counter()-build
        build=time.perf_counter();baseline=suite.WindowBaseline(docs,sources);baseline_setup=time.perf_counter()-build
        suite.write(output/f'block-{block}-setup.json',{'kre_seconds':kre_setup,'baseline_seconds':baseline_setup,
            'kre_index_bytes':store.db.execute('PRAGMA page_count').fetchone()[0]*store.db.execute('PRAGMA page_size').fetchone()[0],
            'baseline_index_bytes':baseline.db.execute('PRAGMA page_count').fetchone()[0]*baseline.db.execute('PRAGMA page_size').fetchone()[0],'utc':utc()})
        try:
            for row in plan:
                if row['block']!=block:continue
                arm_folder=output/f"arm-{row['ordinal']:03}"
                if arm_folder.exists():continue # Completed receipts validated above; never repeat them.
                if STOP_REQUESTED or (output/'STOP').exists() or time.time()>=state['deadline_epoch']:break
                prior=[suite.read(p) for p in output.glob('arm-*/receipt.json')]
                if sum(len(r['attempts']) for r in prior)>=96:raise ValueError('Call budget exhausted')
                if sum(r.get('completion_seconds') or 0 for r in prior)>=protocol['cumulative_arm_limit_seconds']:break
                task=by_task[row['task_id']];model=dict(by_model[row['model_id']])
                remaining_arm=protocol['cumulative_arm_limit_seconds']-sum(r.get('completion_seconds') or 0 for r in prior)
                remaining_campaign=state['deadline_epoch']-time.time()-30
                if min(remaining_arm,remaining_campaign)<=0:break
                model['arm_deadline_seconds']=min(model['arm_deadline_seconds'],remaining_arm,remaining_campaign)
                prepare=lambda:suite.contexts(task,docs,sources,store,baseline,protocol,conditions=(row['condition'],))[row['condition']]
                result=execute_arm(row,model,protocol,arm_folder,prepare,LocalTransport(),should_stop=lambda:STOP_REQUESTED or (output/'STOP').exists())
                print(json.dumps({'ordinal':row['ordinal'],'state':result['state'],'restored':result['restored']}),flush=True)
                if result['state'] not in ('completed','output_limit') or not result['restored']:break
        finally:store.close();baseline.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,default=suite.FIXTURE)
    p.add_argument('--approval',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--block',type=int,required=True)
    a=p.parse_args();run_block(a.fixture,a.approval,a.output,a.block)


if __name__=='__main__':main()
