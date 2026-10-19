"""Explicitly attributed unit fixtures; historical oracle/IR files are never changed."""
from copy import deepcopy

def explicit_fixture(original):
    f=deepcopy(original);data=f['data'];context=data['citation_context'];nid=context['node_id']
    old=context['text'];text='The cited work [1] states: “'+old.replace('[1]','')+'”'
    context.update(text=text,selector={'kind':'numeric','value':'1'})
    data['node']={'id':'use','kind':'ReferenceUse','text':'[1]','attrs':{'selector':{'kind':'numeric','value':'1'}}}
    for source in data['sources']:
        if source.get('origin')=='paper' and source.get('node_id')==nid:source['text']=text
    for field in f['raw']['fields'].values():
        for q in field.get('quotes',[]):
            if any(source.get('origin')=='paper' and source.get('node_id')==nid and source['source_id']==q['source_id'] for source in data['sources']):q['quote']=text
    return f

def attributed_paper(tmp_path):
    from test_paper_compiler_program_analysis import paper
    ir=paper(tmp_path);p=next(n for n in ir['nodes'] if n['id']=='p')
    p['text']='The cited work [1] states: “We apply tree models.”'
    p['provenance']=[{'kind':'synthetic','operation_id':'explicit-attribution-unit-fixture','ancestor_provenance':p['provenance']}]
    return ir

def attributed_reference(data,*args,**kwargs):
    from test_paper_compiler_program_analysis import grounded_reference
    raw=grounded_reference(data,*args,**kwargs)
    source=next(s for s in data['sources'] if s.get('node_id')==data['citation_context']['node_id'])
    raw['fields']['related']['quotes'][0]['quote']=source['text']
    return raw
