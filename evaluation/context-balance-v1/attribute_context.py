"""Read-only known-task attribution. Gold is diagnostic only, never a selector."""
from pathlib import Path
import argparse,hashlib,importlib.util,json
from collections import Counter,defaultdict


def main(repo,out):
    spec=importlib.util.spec_from_file_location('frozen_suite',repo/'scripts/large_suite.py')
    suite=importlib.util.module_from_spec(spec);spec.loader.exec_module(suite)
    docs,tasks,sources=suite.load_fixture();byid={d['id']:d for d in docs}
    records=json.loads((repo/'docs/verification/post96/production-retrieval-comparison.json').read_text())
    taskbyid={t['id']:t for t in tasks}
    enc=suite.encoded
    size=lambda text:len(text.encode('utf-8'))
    prop=lambda k,v:len(enc(k))+1+len(enc(v))
    def refs_gold(task):
        spans=list(task['required_evidence'])
        spans += [s for g in task.get('evidence_groups',[]) for a in g['alternatives'] for s in a['spans']]
        unique={json.dumps(s,sort_keys=True):s for s in spans}
        return list(unique.values())
    def gold_positions(task):
        pos=defaultdict(set)
        for s in refs_gold(task):pos[s['source_id']].update(range(s['line_start'],s['line_end']+1))
        return pos
    def packets(refs):
        return [suite.packet(byid[r['source_id']],'\n'.join(sources[r['source_id']].split('\n')[r['line_start']-1:r['line_end']]),r['line_start'],r['line_end']) for r in refs]
    def quantify(task,items):
        gold=gold_positions(task);counts=defaultdict(int);seen=Counter();locations=set();line_texts=Counter()
        for item in items:
            source=item['source_id'];text=item['text'];n=size(text)
            counts['source_text_bytes']+=n
            counts['source_json_escape_bytes']+=len(enc(text))-2-n
            lines=text.split('\n')
            counts['source_newline_bytes']+=max(0,len(lines)-1)
            for number,line in enumerate(lines,item['line_start']):
                counts['gold_line_content_bytes' if number in gold.get(source,set()) else 'non_gold_line_content_bytes']+=size(line)
                if number not in gold.get(source,set()):
                    counts['nongold_text_in_gold_source_bytes' if source in gold else 'text_in_non_gold_sources_bytes']+=size(line)
                if line.strip():
                    if line_texts[line]:counts['repeated_identical_line_content_bytes']+=size(line)
                    line_texts[line]+=1
                if line.startswith('Synthetic Meridian/Harbor evaluation document.'):
                    counts['synthetic_disclaimer_bytes']+=size(line)
                key=(source,number)
                counts['repeated_source_line_occurrences']+=int(key in locations);locations.add(key)
            if seen[source]:
                counts['repeated_source_metadata_bytes']+=sum(prop(k,item[k]) for k in ('source_id','source_sha256','lifecycle','freshness','authority','origin'))
            seen[source]+=1
        context=len(enc(items));counts['context_bytes']=context;counts['metadata_and_json_syntax_bytes']=context-counts['source_text_bytes']-counts['source_json_escape_bytes']
        assert counts['gold_line_content_bytes']+counts['non_gold_line_content_bytes']+counts['source_newline_bytes']==counts['source_text_bytes']
        counts['selected_unique_sources']=len(seen)
        counts['selected_gold_sources']=len(set(seen)&set(gold))
        counts['gold_sources']=len(gold)
        counts['items']=len(items)
        counts['labeled_source_precision']=counts['selected_gold_sources']/len(seen) if seen else None
        counts['labeled_source_recall']=counts['selected_gold_sources']/len(gold) if gold else None
        counts['gold_annotation_covers_whole_source']=False
        return dict(counts)
    per=[]
    for row in records['tasks']:
        task=taskbyid[row['task_id']];q={'task_id':task['id'],'scope':task['scope'],'category':task['category']}
        for version in ('original','corrected'):
            items=packets(row[version]['evidence']);assert len(enc(items))==row[version]['context_bytes']
            q[version]=quantify(task,items);q[version]['evidence_groups']=row[version]['coverage']
        per.append(q)
    summaries=[]
    for scope in ('all','compact','large'):
        selected=[r for r in per if scope=='all' or r['scope']==scope];r={'scope':scope,'tasks':len(selected)}
        for version in ('original','corrected'):
            sums={k:sum(x[version].get(k,0) for x in selected) for k in ('context_bytes','items','source_text_bytes','gold_line_content_bytes','non_gold_line_content_bytes','source_newline_bytes','source_json_escape_bytes','metadata_and_json_syntax_bytes','repeated_source_metadata_bytes','repeated_source_line_occurrences','selected_unique_sources','selected_gold_sources','nongold_text_in_gold_source_bytes','text_in_non_gold_sources_bytes','repeated_identical_line_content_bytes','synthetic_disclaimer_bytes')}
            positive=[x for x in selected if x[version]['gold_sources']]
            sums['positive_task_returned_sources']=sum(x[version]['selected_unique_sources'] for x in positive)
            sums['positive_task_labeled_source_precision']=sum(x[version]['selected_gold_sources'] for x in positive)/sum(x[version]['selected_unique_sources'] for x in positive)
            r[version]=sums
        r['delta']={k:r['corrected'][k]-r['original'][k] for k in r['original']}
        summaries.append(r)
    missed={'LS02','LS04','LS05','LS06','LS22','LS23','LS24'};oracle=[]
    def para_ranges(text):
        # Original paragraph+heading boundary semantics; no context selector uses gold.
        ranges=[];start=None;lines=text.split('\n')
        for n,line in enumerate(lines,1):
            if not line.strip():
                if start is not None:ranges.append((start,n-1));start=None
                continue
            if start is not None and line.lstrip().startswith('#'):ranges.append((start,n-1));start=n
            if start is None:start=n
        if start is not None:ranges.append((start,len(lines)))
        return ranges
    for task in tasks:
        if task['id'] not in missed:continue
        gold=gold_positions(task);source_rows=[];allfocused=[];allparas=[];allfull=[]
        for source,positions in gold.items():
            text=sources[source];lines=text.split('\n');start,end=min(positions),max(positions)
            focal=suite.packet(byid[source],'\n'.join(lines[start-1:end]),start,end)
            prs=[suite.packet(byid[source],'\n'.join(lines[a-1:b]),a,b) for a,b in para_ranges(text) if set(range(a,b+1))&positions]
            nonblank=[n for n,line in enumerate(lines,1) if line.strip()];full=suite.packet(byid[source],'\n'.join(lines[nonblank[0]-1:nonblank[-1]]),nonblank[0],nonblank[-1])
            source_rows.append({'source_id':source,'gold_lines':sorted(positions),'full_lines':[nonblank[0],nonblank[-1]],'focused_lines':[start,end],
              'source_utf8_bytes':size(text),'full_packet_bytes':len(enc([full])),'focused_packet_bytes':len(enc([focal])),
              'gold_paragraph_packets':len(prs),'gold_paragraph_packet_bytes':len(enc(prs)),
              'full_is_cheaper_than_gold_paragraph_packets':len(enc([full]))<len(enc(prs)),
              'full_document_needed_by_frozen_gold':set(range(nonblank[0],nonblank[-1]+1))<=positions})
            allfocused.append(focal);allparas+=prs;allfull.append(full)
        original=next(r for r in records['tasks'] if r['task_id']==task['id'])
        oracle.append({'task_id':task['id'],'current_context_bytes':original['corrected']['context_bytes'],
            'gold_source_full_packet_bytes':len(enc(allfull)),'oracle_focused_contiguous_packet_bytes':len(enc(allfocused)),
            'oracle_gold_paragraph_packet_bytes':len(enc(allparas)),'sources':source_rows,
            'warning':'Gold-only diagnostic, not an executable evidence-selection policy or semantic sufficiency judgment. Alternative gold spans are unioned, so optional valid alternatives may overstate minimum.'})
    cost_rows=[]
    for task_record in records['tasks']:
        legacy_items=packets(task_record['original']['evidence'])
        grouped=defaultdict(list)
        for item in legacy_items:grouped[item['source_id']].append(item)
        for source,selected in grouped.items():
            source_text=sources[source]
            if size(source_text)>1200:continue
            lines=source_text.split('\n');nonblank=[i for i,line in enumerate(lines,1) if line.strip()]
            whole=suite.packet(byid[source],'\n'.join(lines[nonblank[0]-1:nonblank[-1]]),nonblank[0],nonblank[-1])
            before_cost=len(enc(selected));after_cost=len(enc([whole]))
            cost_rows.append({'task_id':task_record['task_id'],'scope':task_record['scope'],'source_id':source,
              'source_utf8_bytes':size(source_text),'legacy_selected_packets':len(selected),
              'legacy_selected_packet_bytes':before_cost,'whole_source_packet_bytes':after_cost,
              'delta_whole_minus_selected_bytes':after_cost-before_cost,
              'whole_cheaper':after_cost<before_cost,
              'legacy_selected_spans':[[i['line_start'],i['line_end']] for i in selected],
              'full_source_span':[nonblank[0],nonblank[-1]]})
    cost_summary=[]
    for scope in ('all','compact','large'):
        selected=[r for r in cost_rows if scope=='all' or r['scope']==scope]
        cost_summary.append({'scope':scope,'short_source_task_incidences':len(selected),
          'legacy_multipacket_source_incidences':sum(r['legacy_selected_packets']>1 for r in selected),
          'whole_cheaper_incidences':sum(r['whole_cheaper'] for r in selected),
          'whole_equal_incidences':sum(r['delta_whole_minus_selected_bytes']==0 for r in selected),
          'whole_more_expensive_incidences':sum(r['delta_whole_minus_selected_bytes']>0 for r in selected),
          'legacy_packet_bytes':sum(r['legacy_selected_packet_bytes'] for r in selected),
          'whole_packet_bytes':sum(r['whole_source_packet_bytes'] for r in selected),
          'sum_whole_delta_if_always_expanded':sum(r['delta_whole_minus_selected_bytes'] for r in selected),
          'sum_delta_for_cheaper_only_groups':sum(r['delta_whole_minus_selected_bytes'] for r in selected if r['whole_cheaper'])})
    review=json.loads((repo/'docs/verification/post96/quality-review.json').read_text())
    actual_review=json.loads((repo/'.scratch/large-scale-v1-results/blind-review.json').read_text())
    # Hash identity proves no newly completed fields in the retained artifact.
    review_hash=hashlib.sha256((repo/'.scratch/large-scale-v1-results/blind-review.json').read_bytes()).hexdigest()
    assert review_hash==review['original_blind_review_sha256']
    result={'format':'kre-context-relevance-attribution/1','model_calls':0,'source_commit':'89f115c','known_suite_tasks':len(tasks),
      'definition':'Gold-line text is a measured lower bound on directly required evidence. Nongold text is unannotated, not proved irrelevant. Newlines, JSON escaping and metadata are disjoint from decoded line content. Repeated metadata is a nonadditive subset of metadata.',
      'summaries':summaries,'per_task':per,'oracle_missing_cases':oracle,
      'fixed_legacy_source_cost':{'summary':cost_summary,'source_groups':cost_rows,'limitation':'Fixed selected-source cost diagnostic only: no candidate or ranking changes, no selector, no measured tokens. Each source-group cost includes its array wrapper; deltas are additive because wrapper costs cancel. A cheaper whole-source group cannot solve every lexical evidence omission.'},
      'contract':{'metadata_dedup_in_native_context_allowed':False,'reason':'Store._validate_context requires context_text == _render(items) and each complete item == _item(stored_chunk,citation_id). Removing fields, subspans, merged packets or a source dictionary fails equality.',
        'host_projection':'The large benchmark already projects immutable native items to common packets. A host-specific smaller presentation is distinct from the native contract and has no new model token measurement.'},
      'review':{'retained_blind_review_sha256':review_hash,'unchanged_since_previous_review':True,'blank_human_templates':review['blank_human_templates'],'semantic_judgments_added':0,'independent_human_reviews_applied':0,'review_status':'unknown/pending','mechanical_regressions_35b':['LS04','LS05']},
      'limits':['No model tokens, answer quality, independent semantic judgments or new billed usage measured.','Gold-only oracle ranges must not enter retrieval requests, algorithm choices or proposed live prompts.','Required-source precision is label-based, and nongold sources can contain useful corroboration or abstention evidence.']}
    out.mkdir(parents=True,exist_ok=True);(out/'attribution.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'summaries':summaries,'oracle':[{'task_id':o['task_id'],'current_context_bytes':o['current_context_bytes'],'oracle_focused_contiguous_packet_bytes':o['oracle_focused_contiguous_packet_bytes'],'oracle_gold_paragraph_packet_bytes':o['oracle_gold_paragraph_packet_bytes']} for o in oracle],'review':result['review']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.repo.resolve(),a.output.resolve())
