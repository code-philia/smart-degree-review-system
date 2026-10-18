"""Verified package loading and diagnostics with honest document coverage."""
from collections import Counter
import hashlib,json
from pathlib import Path
from .compiler import validate_rule_ir,generate_code
from .contracts import validate_analysis,ir_hash
from .expressions import run_generated
from .storage import json_bytes

def _hash(data):return hashlib.sha256(data).hexdigest()

def load_package(folder):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text());rule=json.loads((folder/'rule-ir.json').read_text())
    inputs=json.loads((folder/'input.json').read_text());code=(folder/'checks.py').read_text();registry=inputs['registry']
    checks={'code_sha256':_hash(code.encode()),'rule_ir_sha256':_hash(json_bytes(rule)),
        'rule_text_sha256':_hash(inputs['rule_text'].encode()),'standards_sha256':_hash(json_bytes(inputs['basis'])), 'registry_sha256':_hash(json_bytes(registry))}
    if any(manifest.get(key)!=value for key,value in checks.items()):raise ValueError('rule package hash mismatch')
    validate_rule_ir(rule,registry)
    if code!=generate_code(rule):raise ValueError('generated backend mismatch')
    return {'rule_ir':rule,'manifest':manifest,'code':code,'registry':registry,'input':inputs}

def _evidence_check(ir,analysis):
    nodes={n['id']:n for n in ir['nodes']}
    for item in analysis['evidence']:
        if item.get('kind')=='source_span':
            node=nodes.get(item.get('node_id'));start=item.get('start');end=item.get('end')
            if node is None or type(start)is not int or type(end)is not int or not 0<=start<end<=len(node.get('text') or '') or node['text'][start:end]!=item.get('quote'):
                raise ValueError('source evidence quote mismatch')

def check(ir,analysis,rule_packages):
    validate_analysis(ir,analysis);_evidence_check(ir,analysis);rules=[]
    for package in rule_packages:
        rule=package['rule_ir'];manifest=package['manifest']
        if _hash(package['code'].encode())!=manifest['code_sha256'] or _hash(json_bytes(rule))!=manifest['rule_ir_sha256']:raise ValueError('rule package hash mismatch')
        for name,version in manifest['capability_versions'].items():
            if analysis['capability_versions'].get(name)!=version:raise ValueError('analysis capability version mismatch: '+name)
        registry=package.get('registry',{})
        types={'string':str,'number':(int,float),'boolean':bool,'array':list,'object':dict}
        for cap_name in rule['requires']:
            fields=registry.get('capabilities',{}).get(cap_name,{}).get('fields',{})
            for node_id,facts in analysis['results'].get(cap_name,{}).items():
                for name,observation in facts.items():
                    if name not in fields:raise ValueError('unknown analysis field type: '+cap_name+'.'+name)
                    if not isinstance(observation,dict) or 'state' not in observation:raise ValueError('untyped analysis observation')
                    if observation['state']=='observed':
                        typ=fields[name];value=observation.get('value')
                        if typ not in types or not isinstance(value,types[typ]) or (typ=='number' and isinstance(value,bool)):
                            raise ValueError('analysis field type mismatch: '+cap_name+'.'+name)
        results=run_generated(package['code'],ir,analysis);counts=Counter(r['status'] for r in results)
        for row in results:
            assessment=analysis['results'].get('citation_relevance',{}).get(row.get('node_id'),{}).get('related')
            if assessment and 'citation_relevance' in rule['requires']:row['assessment']=assessment
        scopes={ {'BibliographyEntry':'bibliography','CitationGroup':'reference_uses','ReferenceUse':'reference_uses'}.get(c['target_kind'],c['target_kind']) for c in rule['checks'] }
        gaps=[s for s in sorted(scopes) if ir['coverage'].get(s,{}).get('status')!='complete']
        if counts['ERROR']:status='ERROR'
        elif counts['VIOLATION']:status='VIOLATION'
        elif counts['UNKNOWN'] or gaps:status='UNKNOWN'
        elif counts['PASS']:status='PASS'
        else:status='NOT_APPLICABLE'
        rules.append({'rule_id':rule['rule_id'],'title':rule['title'],'status':status,'counts':dict(counts),'results':results,
            'basis_catalog':[{**b,'kind':'standard' if b['id'].startswith('gbt') else 'project'} for b in package.get('input',{}).get('basis',[])],
            'coverage':{'incomplete_scopes':gaps},'package_sha256':_hash(json_bytes(manifest))})
    return {'schema_version':'paper-check/1.0','document_id':ir['document_id'],'paper_ir_sha256':ir_hash(ir),
        'rules':rules,'evidence':analysis['evidence'],'bindings':analysis.get('bindings',[]),'coverage':ir['coverage']}
