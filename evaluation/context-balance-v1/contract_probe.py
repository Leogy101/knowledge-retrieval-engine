"""Offline negative probe of the existing native rendering contract."""
from pathlib import Path
import argparse,copy,json,sys
p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.repo.resolve()/'src'))
from kre import Store
with Store(':memory:',principal='offline',scopes={'reader':{'public'}}) as store:
    store.ingest_text('record','Report sample alpha.\n\nReport sample beta.\n\n'+('padding '*190),collection='public',freshness='fresh')
    request={'contract_version':'0.1','request_id':'contract-probe','query':'Report sample','access_scope_ref':'reader','destination':'local_only','purpose':'current_answer','budget':{'max_tokens':6000,'max_bytes':6000,'max_items':8}}
    original=store.context(request);assert len(original['items'])==2
    check=lambda value:store.validate_context(value,scope_ref='reader',destination='local_only')
    variants={};reduced=copy.deepcopy(original);del reduced['items'][1]['recorded_at']
    reduced['context_text']=store._render(reduced['items']);size=len(reduced['context_text'].encode());reduced['token_usage'].update(context_bytes=size,estimated_tokens=size)
    variants['drop_repeated_item_metadata']=check(reduced)
    reduced=copy.deepcopy(original)
    reduced['context_text']=json.dumps({'sources':{'record':{k:original['items'][0][k] for k in ('source_id','revision_id','recorded_at')}},'excerpts':[{'text':item['text'],'locator':item['locator']} for item in original['items']]})
    size=len(reduced['context_text'].encode());reduced['token_usage'].update(context_bytes=size,estimated_tokens=size)
    variants['deduplicated_source_dictionary_context_text']=check(reduced)
    result={'format':'kre-contract-rendering-negative-probe/1','model_calls':0,'original':check(original),'variants':variants,'source_policy_unchanged':True}
    a.output.write_text(json.dumps(result,indent=2)+'\n')
