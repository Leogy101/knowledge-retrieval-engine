"""Replay the installed public generic inference path with fictional KRE evidence."""
import argparse
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from unittest.mock import patch

from kre import Store, evidence_ref
from kre._stdio import serve
from kre.mcp import KnowledgeTools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--openclaw-root', type=Path, required=True)
    args = parser.parse_args()
    marker = 'SYNTHETIC_DUPLICATION_SENTINEL_7C9A'
    with patch('kre.store._now', return_value='2026-11-15T00:00:00Z'), patch(
            'kre.store.uuid.uuid4', return_value=uuid.UUID('00000000-0000-0000-0000-000000000001')):
        with Store(':memory:', principal='fixture', scopes={'scope': {'shared'}},
                   destinations=frozenset({'approved_remote'})) as store:
            store.db.execute("UPDATE metadata SET value=? WHERE key='namespace'", ('0' * 32,))
            store.db.commit()
            store.ingest_text('fixture-source', marker + ' is a fictional project code.', collection='shared',
                              egress='approved_remote', freshness='fresh')
            handler = KnowledgeTools(store, scope_ref='scope', destination='approved_remote')
            result = handler.call('kre_retrieve', {'query': marker})
            context = result['context']
            packets = [
                {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                    'protocolVersion': '2025-11-25', 'capabilities': {},
                    'clientInfo': {'name': 'synthetic-replay', 'version': '1'}}},
                {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {
                    'name': 'kre_retrieve', 'arguments': {'query': marker}}},
            ]
            outgoing = io.BytesIO()
            serve('kre', 'synthetic', handler.definitions(), lambda name, parameters: result,
                  incoming=io.BytesIO(b''.join(json.dumps(p).encode() + b'\n' for p in packets)),
                  outgoing=outgoing)
            response_packet = outgoing.getvalue().splitlines()[-1]
            wire_result = json.loads(response_packet)['result']
            validation = {'complete': handler.call('kre_validate', {'context': context})['validation']}
            for field in ('items', 'context_text'):
                candidate = copy.deepcopy(context)
                del candidate[field]
                validation['without_' + field] = handler.call('kre_validate', {'context': candidate})['validation']
            reconstructed = copy.deepcopy(context)
            reconstructed['context_text'] = Store._render(reconstructed['items'])
            validation['reconstructed'] = handler.call('kre_validate', {'context': reconstructed})['validation']
            ref = evidence_ref(context['items'][0])
            store.revoke('fixture-source')
            validation['revoked'] = handler.call('kre_validate', {'context': reconstructed})['validation']
            validation['required_revoked_error'] = handler.call('kre_retrieve', {
                'query': marker, 'required_refs': [ref]})['error']['code']
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / 'fictional-mcp-response.json'
        fixture.write_text(json.dumps(wire_result))
        replay = json.loads(subprocess.check_output([
            'node', str(Path(__file__).with_suffix('.mjs')), str(args.openclaw_root), str(fixture)
        ], text=True, timeout=15))
    replay['canonical_context_text_bytes'] = len(context['context_text'].encode())
    replay['mcp_jsonrpc_response_bytes_without_newline'] = len(response_packet)
    replay['context_fields_equivalent'] = json.loads(context['context_text']) == context['items']
    replay['validation'] = validation
    print(json.dumps(replay, indent=2))


if __name__ == '__main__':
    main()
