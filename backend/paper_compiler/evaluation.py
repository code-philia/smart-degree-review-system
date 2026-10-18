"""Paired target-local evaluation; undecidable and excluded cases stay visible."""
from collections import Counter,defaultdict

def _find(report,oracle):
    rows=[item for rule in report.get('rules',[]) if str(rule['rule_id'])==str(oracle['rule_id']) for item in rule.get('results',[])
        if item.get('node_id')==oracle['target_node_id'] and (oracle.get('target_check_id') is None or item.get('check_id')==oracle['target_check_id'])]
    if not rows:return None
    statuses={r['status'] for r in rows}
    return next((s for s in ['ERROR','VIOLATION','UNKNOWN','PASS','NOT_APPLICABLE'] if s in statuses),'UNKNOWN')

def score_pair(oracle,original,mutant):
    before=_find(original,oracle);after=_find(mutant,oracle)
    result={'rule_id':str(oracle['rule_id']),'parent_sha256':oracle['parent_sha256'],'mutation_id':oracle.get('mutation_id'),
        'evidence_domain':oracle['evidence_domain'],'before':before,'after':after,'detected':False,'valid_pair':False}
    if not oracle.get('valid'):outcome='unverified_oracle'
    elif before!='PASS':outcome='invalid_parent' if before in {'VIOLATION','NOT_APPLICABLE'} else 'undecidable_parent'
    elif after is None:outcome='unlocalizable'
    else:
        result['valid_pair']=True
        if after in {'UNKNOWN','ERROR'}:outcome='undecidable' if after=='UNKNOWN' else 'error'
        elif after==oracle['status']:outcome='detected';result['detected']=True
        else:outcome='missed'
    result['outcome']=outcome
    return result

def summarize_pairs(records,minimum_parents=100):
    grouped=defaultdict(list)
    for row in records:grouped[str(row['rule_id'])].append(row)
    output={}
    for rid,rows in grouped.items():
        counts=Counter(row['outcome'] for row in rows);valid=[r for r in rows if r['valid_pair']]
        real={r['parent_sha256'] for r in valid if r['evidence_domain'] in {'source_format','real_external','real_citation_purpose'}}
        detected=sum(r['detected'] for r in valid)
        output[rid]={'candidate_pairs':len(rows),'valid_pairs':len(valid),'detected':detected,'undecidable':counts['undecidable'],
            'outcomes':dict(counts),'distinct_real_parents':len(real),'target_shortfall':max(0,minimum_parents-len(real)),
            'detection_rate_including_unknown':detected/len(valid) if valid else None,'domains':dict(Counter(r['evidence_domain'] for r in rows))}
    return {'schema_version':'mutation-evaluation/1.0','by_rule':output,'total_candidate_pairs':len(records),'minimum_real_parents_per_rule':minimum_parents}


def evaluate(case_manifest,report_root,runner):
    """Read sealed answers only in this evaluator; runner receives normal IR paths."""
    from pathlib import Path
    from .batch import load,freeze,safe_id
    from .storage import write_json_atomic
    from .contracts import validate_ir,ir_hash
    root=Path(report_root);data=load(case_manifest)
    if not data.get('version'):raise ValueError('case version required')
    ids=[safe_id(c['id']) for c in data.get('cases',[])]
    if len(set(ids))!=len(ids):raise ValueError('duplicate evaluation case')
    freeze(root,{'manifest':data,'evaluator_version':'paired-target/1.0'})
    records=[]
    for case in data['cases']:
        checkpoint=root/'cases'/(case['id']+'.json')
        if checkpoint.exists():records.append(load(checkpoint));continue
        oracle=load(case['oracle']);paths=[Path(case['original']),Path(case['mutant'])]
        for path,key in zip(paths,['parent_sha256','mutant_sha256']):
            ir=load(path);validate_ir(ir)
            if ir_hash(ir)!=oracle[key]:raise ValueError('evaluation IR/oracle hash mismatch')
        reports=[]
        for label,path in zip(['original','mutant'],paths):
            output=root/'detector-results'/case['id']/(label+'.json')
            if output.exists():result=load(output)
            else:
                try:result=runner(path)
                except Exception as error:result={'rules':[],'error':{'type':type(error).__name__,'reason':str(error)[:500]}}
                write_json_atomic(output,result,exclusive=True)
            reports.append(result)
        row=score_pair(oracle,*reports)
        if any('error' in r for r in reports):row.update(outcome='error',valid_pair=False,detected=False)
        write_json_atomic(checkpoint,row,exclusive=True);records.append(row)
    summary=summarize_pairs(records,data.get('minimum_parents',100))
    write_json_atomic(root/'summary.json',summary);return summary
