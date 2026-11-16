import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent
path = root/'offline-transfer-eight.v1.json'
data = json.loads(path.read_text(encoding='utf-8'))
assert data['fixture_status'] == 'frozen_before_any_retrieval_run'
assert data['synthetic'] is True
assert len(data['cases']) == 8
source_ids = [s['source_id'] for s in data['sources']]
assert len(source_ids) == len(set(source_ids))
case_ids = [c['id'] for c in data['cases']]
assert len(case_ids) == len(set(case_ids))
sources = {s['source_id']:s for s in data['sources']}
for s in sources.values():
    assert s['freshness'] in {'fresh','stale','unknown'}
    assert s['authority'] in {'authoritative','unverified'}
    assert s['origin'] in {'source_evidence','user_assertion','model_inference'}
    assert s['state'] in {'active','revoked'}
    assert s['collection'] in {'public','private'}
    assert isinstance(s['text'],str) and s['text']
    assert '\r' not in s['text']
gold_count = 0
compact_checks = []
for c in data['cases']:
    assert c['scope'] in data['scope_definitions']
    assert c['purpose'] == 'current_answer'
    assert c['destination'] == 'local_only'
    assert c['query'] and c['answer_requirements']
    assert set(c['budget']) == {'max_bytes','max_tokens','max_items'}
    for name, upper in [('max_bytes',262144),('max_tokens',262144),('max_items',32)]:
        assert type(c['budget'][name]) is int and 0 < c['budget'][name] <= upper
    assert len(set(g['source_id'] for g in c['gold'])) >= 2
    assert len(set(c['forbidden_sources'])) == len(c['forbidden_sources'])
    assert not set(c['forbidden_sources']) & {g['source_id'] for g in c['gold']}
    allowed = set(data['scope_definitions'][c['scope']]['collections'])
    for sid in c['forbidden_sources']:
        s = sources[sid]
        assert s['state'] == 'revoked' or s['freshness'] == 'stale' or s['collection'] not in allowed
    for sid in c['distractor_sources']:
        assert sid in sources
    for g in c['gold']:
        s = sources[g['source_id']]
        assert s['collection'] in allowed
        assert s['freshness'] == 'fresh' and s['state'] == 'active'
        assert s['authority'] == 'authoritative' and s['origin'] == 'source_evidence'
        lines = s['text'].splitlines()
        assert 1 <= g['line_start'] <= g['line_end'] <= len(lines)
        assert '\n'.join(lines[g['line_start']-1:g['line_end']]) == g['quote']
        gold_count += 1
    if c['budget']['max_items'] < 12:
        texts = [sources[sid]['text'] for sid in sorted({g['source_id'] for g in c['gold']})]
        total_bytes = sum(len(t.encode('utf-8')) for t in texts)
        # A transparent lexical proxy, not a call to the product's tokenizer.
        lexical_units = sum(len(re.findall(r'[A-Za-z_]+|[0-9]+|[^\w\s]',t)) for t in texts)
        assert len(texts) <= c['budget']['max_items']
        assert total_bytes <= c['budget']['max_bytes']
        assert lexical_units <= c['budget']['max_tokens']
        compact_checks.append({'case_id':c['id'],'gold_source_count':len(texts),'whole_source_utf8_bytes':total_bytes,'lexical_token_proxy':lexical_units,'runtime_tokenizer_used':False})
lengths = [len(s['text']) for s in sources.values()]
assert max(lengths) > 2000
assert min(lengths) < 200
assert any(s['state']=='revoked' for s in sources.values())
assert any(s['freshness']=='stale' for s in sources.values())
assert any(s['collection']=='private' for s in sources.values())
assert any(c['scope']=='owner' for c in data['cases'])
assert any(c['missing_evidence'] for c in data['cases'])
report = {'status':'passed','validation_kind':'data_only_no_retrieval','validated_at_utc':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'fixture_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'source_count':len(sources),'case_count':len(data['cases']),'gold_span_count':gold_count,'shortest_source_characters':min(lengths),'longest_source_characters':max(lengths),'sources_over_2000_characters':sum(n>2000 for n in lengths),'compact_budget_checks':compact_checks,'notes':['Gold span checks use exact source text and one-based inclusive lines.','No Store, gateway, model, HTTP, or retrieval code was imported or executed.','The compact case lexical token proxy is not a product tokenizer guarantee.']}
(root/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','fixture_sha256','source_count','case_count','gold_span_count','sources_over_2000_characters']}))
