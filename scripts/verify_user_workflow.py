"""Verify an independently installed KRE wheel with synthetic files and MCP stdio.

Run with the clean environment's Python. No source checkout import, network,
model inference, existing database, live host configuration or extra dependency.
"""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time


def run(*args: str, cwd: Path, expected: int = 0, input_text: str | None = None) -> str:
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    process = subprocess.run([sys.executable, '-I', *args], cwd=cwd, env=environment,
                             input=input_text, text=True, capture_output=True, timeout=30)
    if process.returncode != expected:
        raise RuntimeError(f'Offline command failed ({process.returncode}): {process.stderr}')
    return process.stdout


def main() -> None:
    began = time.monotonic()
    version = importlib.metadata.version('knowledge-retrieval-engine')
    checks = []
    with tempfile.TemporaryDirectory(prefix='kre-user-workflow-') as directory:
        base = Path(directory)
        documents = base / 'documents'
        documents.mkdir()
        database = base / 'knowledge.sqlite3'
        def cli(*args: str, expected: int = 0, as_json: bool = True):
            output = run('-m', 'kre', '--db', str(database), *args, cwd=base, expected=expected)
            return json.loads(output) if as_json else output
        assert run('-m', 'kre', '--version', cwd=base).strip() == version
        assert cli('init')['fts5'] is True
        checks += ['installed_version', 'initialize_fts5']
        for command in ('demo', 'demo-k2'):
            output = json.loads(run('-m', 'kre', '--db', str(base / (command+'.sqlite3')),
                                    command, '--json', cwd=base))
            assert isinstance(output, dict)
            if command == 'demo-k2':
                assert output['initial_context_validation_after_update'] == 'changed'
                assert output['required_revoked']['error']['code'] == 'REQUIRED_EVIDENCE_MISSING'
            checks.append(command)
        guide = documents / 'runbook.md'
        text = '# Example release\n\nRollback restores the amber snapshot after operator approval.\n'
        guide.write_text(text, encoding='utf-8')
        first = cli('ingest', str(guide), '--root', str(documents), '--source-id', 'runbook')['files'][0]
        assert first['status'] == 'indexed'
        assert 'amber snapshot' in cli('search', 'rollback', as_json=False)
        context = cli('context', 'rollback', '--budget', '4000', '--max-bytes', '4000')
        item = context['items'][0]
        assert item['source_id'] == 'runbook' and item['revision_id'] == first['revision_id']
        selected = '\n'.join(text.splitlines()[item['locator']['line_start']-1:item['locator']['line_end']])
        assert selected == item['text']
        assert hashlib.sha256(item['text'].encode()).hexdigest() == item['content_sha256']
        assert context['token_usage']['context_bytes'] <= 4000
        assert cli('inspect', first['revision_id'])['text'] == text
        checks += ['explicit_root_ingestion', 'lexical_search', 'bounded_context', 'exact_citation', 'inspect_revision']
        ref = {key: item[key] for key in ('source_id','revision_id','chunk_id','content_sha256')}
        refs = base / 'required.json'
        refs.write_text(json.dumps([ref]), encoding='utf-8')
        required = cli('context', 'unmatchedword', '--required', str(refs), '--budget', '4000')
        assert required['required']['delivered'] == [ref]
        too_small = cli('context', 'rollback', '--required', str(refs), '--budget', '1', expected=2)
        assert too_small['error']['code'] == 'BUDGET_TOO_SMALL' and too_small['context']['items'] == []
        assertion = lambda text: {'text': text, 'origin': 'user_assertion', 'refs': []}
        card = {'objective': assertion('Prepare an offline rollback review.'),
                'constraints': [assertion('Do not execute the rollback.')],
                'decisions': [{'text': item['text'], 'origin': 'source_evidence', 'refs': [ref]}],
                'questions': [], 'next_actions': [assertion('Ask the operator to review the evidence.')]}
        card_path = base / 'task.json'
        card_path.write_text(json.dumps(card), encoding='utf-8')
        assert cli('task-checkpoint', 'rollback-review', '--card', str(card_path))['status'] == 'checkpointed'
        assert cli('task-resume', 'rollback-review')['card'] == card
        checks += ['required_evidence', 'required_budget_failure', 'checkpoint', 'resume_current']
        def rpc(identifier: int, method: str, params: dict | None = None) -> dict:
            return {'jsonrpc':'2.0','id':identifier,'method':method, 'params': params or {}}
        def mcp(*messages: dict) -> dict:
            initialize = rpc(1, 'initialize', {'protocolVersion':'2025-11-25','capabilities':{},
                    'clientInfo':{'name':'offline-workflow','version':'1'}})
            body = ''.join(json.dumps(m)+'\n' for m in [initialize,*messages])
            output = run('-m','kre.mcp','--db',str(database),'--principal','workflow-owner',
                     '--collection','default','--destination','local_only','--local-client',
                     '--max-bytes','4000',cwd=base,input_text=body)
            return {m['id']:m for m in map(json.loads,output.splitlines())}
        wire = mcp(rpc(2,'tools/list'),rpc(3,'tools/call',{'name':'kre_retrieve','arguments':{'query':'rollback'}}))
        assert {x['name'] for x in wire[2]['result']['tools']} == {'kre_retrieve','kre_validate'}
        nested = json.loads(wire[3]['result']['content'][0]['text'])['context']
        checked = mcp(rpc(2,'tools/call',{'name':'kre_validate','arguments':{'context':nested}}))
        assert json.loads(checked[2]['result']['content'][0]['text'])['validation'] == 'current'
        denied = mcp(rpc(2,'tools/call',{'name':'kre_retrieve','arguments':{'query':'rollback','collection':'private'}}))
        assert denied[2]['result']['isError'] is True
        checks += ['mcp_stdio_discovery', 'mcp_retrieve', 'mcp_validate', 'mcp_scope_escalation_denied', 'mcp_process_exit']
        guide.write_text(text.replace('amber','cobalt'), encoding='utf-8')
        second = cli('ingest', str(guide), '--root', str(documents), '--source-id', 'runbook')['files'][0]
        assert second['revision_id'] != first['revision_id']
        assert cli('inspect', first['revision_id'])['text'] == text
        assert 'cobalt' in cli('context','rollback','--budget','4000')['context_text']
        resumed = cli('task-resume','rollback-review')
        assert resumed['status'] == 'partial' and resumed['card']['decisions'] == []
        checks += ['update_immutable_revision', 'inspect_superseded_revision', 'resume_excludes_superseded_evidence']
        cli('lifecycle','runbook','--action','revoke')
        assert cli('context','rollback')['items'] == []
        assert cli('context','rollback','--historical')['items'] == []
        assert cli('task-resume','rollback-review')['card']['decisions'] == []
        assert cli('context','rollback','--required',str(refs),expected=2)['error']['code'] == 'REQUIRED_EVIDENCE_MISSING'
        checks += ['revoke_current_evidence', 'historical_cannot_restore_revoked', 'resume_excludes_revoked_evidence']
    print(json.dumps({'status':'passed','package_version':version,'checks':checks,'check_count':len(checks),
           'python':platform.python_version(),'os':platform.system(),'os_release':platform.release(),
           'architecture':platform.machine(),'sqlite':sqlite3.sqlite_version,'duration_seconds':time.monotonic()-began,
           'model_calls':0,'runtime_dependencies':importlib.metadata.requires('knowledge-retrieval-engine') or [],
           'temporary_data_removed':True,'live_host_configuration_changed':False},indent=2))

if __name__ == '__main__':
    main()
