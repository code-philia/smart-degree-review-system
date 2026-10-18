"""Independent compiler contract controls. Never passed to analysis or inference."""
import copy
from .analysis import base_analysis,observed,unknown
from .contracts import ir_hash
from .registry import FIELD_TYPES

def _ir():
    return {'schema_version':'paper-ir/1.0','model_version':'paper-model/1.0','document_id':'compiler-control','revision':'1',
        'source_artifacts':[],'root_id':'paper','nodes':[
            {'id':'paper','kind':'Paper','text':None,'children':['entry','use'],'attrs':{},'provenance':[]},
            {'id':'entry','kind':'BibliographyEntry','text':'[1] Smith A. A title[J]. Journal, 2020.','children':[],'attrs':{'key':'1'},'provenance':[{'kind':'synthetic','operation_id':'compiler-control','ancestor_provenance':[]}]},
            {'id':'use','kind':'ReferenceUse','text':'[1]','children':[],'attrs':{'namespace':'bibliography','expected_kind':'BibliographyEntry','scope_id':'paper','selector':{'kind':'numeric','value':'1'}},'provenance':[{'kind':'synthetic','operation_id':'compiler-control','ancestor_provenance':[]}]}
        ],'layout':{'pages':[]},'coverage':{'bibliography':{'status':'complete'},'reference_uses':{'status':'complete'}},'profile':{},'metadata':{},'extensions':{}}

def compiler_controls(rule_id):
    ir=_ir();a=base_analysis(ir);a['evidence']=[{'id':'control-evidence','kind':'controlled_contract','scope':'independent compiler semantics, not real external literature'}]
    if str(rule_id) in {'32','33'}:
        cap,field,node=('external_work','exists','entry') if str(rule_id)=='32' else ('citation_relevance','related','use')
        cases=[]
        for label,value,status in [('positive',True,'PASS'),('negative',False,'VIOLATION'),('insufficient',None,'UNKNOWN')]:
            aa=copy.deepcopy(a);aa['results']={cap:{node:{field:observed(value,['control-evidence']) if value is not None else unknown('insufficient evidence')}}}
            cases.append({'id':str(rule_id)+'-'+label,'ir':copy.deepcopy(ir),'analysis':aa,'status':status})
        return cases
    if str(rule_id)!='31':return []
    def make(name,typ='J',remove=None,optional=False):
        ii=copy.deepcopy(ir);aa=copy.deepcopy(a)
        ii['nodes'][1]['attrs']['resource_type']={'J':'journal_article','M':'book','D':'thesis','EB':'webpage','S':'standard','P':'patent'}.get(typ,'unknown')
        aa['paper_ir_sha256']=ir_hash(ii)
        values={'authors':['Smith A'],'title':'A title','type_code':typ}
        if typ=='J':values.update(container='Journal',year='2020')
        if typ=='D':values.update(institution='Example University',year='2020')
        if typ=='S':values={'standard_number':'GB/T 1234—2020','title':'A title','type_code':'S'}
        if typ=='P':values['patent_number']='CN123456789A'
        if typ in {'EB','PP','DS'}:values.update(carrier_code='OL',url='https://example.org/work',access_date='2024-06-01')
        available_fields=list(values)
        if remove:values.pop(remove,None)
        title=values.get('title','');code=values.get('type_code','');author='Smith A. ' if 'authors' in values else ''
        if typ=='J':text=f"[1] {author}{title}[{code}]. Journal, 2020."
        elif typ=='D':text=f"[1] {author}{title}[{code}]. {values.get('institution','')}, 2020."
        elif typ=='S':text=f"[1] {values.get('standard_number','')} {title}[{code}]."
        elif typ=='P':text=f"[1] {author}{title}: {values.get('patent_number','')}[{code}]."
        else:text=f"[1] {author}{title}[{code}/OL][{values.get('access_date','')}]. https://example.org/work."
        ii['nodes'][1]['text']=text;aa['paper_ir_sha256']=ir_hash(ii)
        fields={name:observed(values[name],['control-evidence']) if name in values else {'state':'confirmed_absent','search_scope':'entry','evidence_ids':['entry']} for name in FIELD_TYPES}
        aa['results']={'bibliography_fields':{'entry':fields},
            'bibliography_shape':{'entry':{'electronic':observed(typ in {'EB','PP','DS'},['entry']),'type_bracketed':observed(remove!='type_code',['entry']),'label_bracketed':observed(True,['entry']),'system':observed('numeric',['entry']),'field_sequence':observed(list(values),['entry'])}},
            'external_work':{'entry':{'exists':observed(True,['control-evidence']),'available_fields':observed(available_fields,['control-evidence'])}},
            'bibliography_order':{'entry':{'position':observed(1,['entry']),'numeric_value':observed(1,['entry'])}},
            'citation_order':{'use':{'system':observed('numeric',['use']),'numeric_value':observed(1,['use']),'first_appearance_rank':observed(1,['use']),'is_first_use':observed(True,['use'])}}}
        basis_ids={'title':['general'],'type_code':['general'],'institution':['8.7'],'access_date':['8.11'],'standard_number':['8.8-8.9'],'patent_number':['8.10']}
        return {'id':'31-'+name,'ir':ii,'analysis':aa,'status':'PASS' if remove is None or optional else 'VIOLATION','basis_ids':['gbt7714-2025:'+x for x in basis_ids.get(remove,[])]}
    cases=[make('journal-without-optional-doi'),make('missing-title',remove='title'),make('missing-type-code',remove='type_code'),
        make('thesis-valid',typ='D'),make('thesis-missing-institution',typ='D',remove='institution'),
        make('web-valid',typ='EB'),make('web-missing-access-date',typ='EB',remove='access_date'),
        make('standard-valid',typ='S'),make('standard-missing-number',typ='S',remove='standard_number'),
        make('patent-valid',typ='P'),make('patent-missing-application-number',typ='P',remove='patent_number')]

    from .analysis import citation_syntax
    for index,text in enumerate(['[1]','[1,3]','[1-3]','[1,3-5]','(Smith, 2020)','Smith (2020)']):
        case=make('body-valid-'+str(index));ii=case['ir'];aa=case['analysis']
        case['diagnostic']='Valid citation notation: singleton and grouped numeric forms may omit comma or range symbols; author-year narrative form includes an author prefix outside parentheses, so opening is the first author character, not the year parenthesis.'
        style='numeric' if text.startswith('[') else 'author_year'
        ii['nodes'][0]['children'].append('group')
        ii['nodes'].append({'id':'group','kind':'CitationGroup','text':text,'children':[],
            'attrs':{'style':style,'marker':text,'superscript':False},'provenance':[{'kind':'synthetic','operation_id':'independent-body-control'}]})
        if style=='author_year':
            ii['nodes'][1]['text']='Smith A. 2020. A title[J]. Journal.'
            ii['nodes'][1]['attrs']['key']='Smith|2020'
            ii['nodes'][2]['text']=text;ii['nodes'][2]['attrs']['selector']={'kind':'author_year','value':'Smith|2020'}
            shape=aa['results']['bibliography_shape']['entry'];shape['system']=observed(style,['entry']);shape['label_bracketed']=observed(False,['entry'])
            shape['field_sequence']=observed(['authors','year','title','type_code','container'],['entry'])
            aa['results']['bibliography_order']['entry']['numeric_value']=unknown('author-year entry')
            aa['results']['citation_order']['use']['system']=observed(style,['use'])
            aa['results']['citation_order']['use']['numeric_value']=unknown('author-year citation')
        aa['paper_ir_sha256']=ir_hash(ii);citation_syntax(ii,aa)
        aa['results']['citation_syntax']['group']['automatic_footnote']=observed(False,['group'])
        cases.append(case)
    repeated=copy.deepcopy(next(c for c in cases if c['id']=='31-body-valid-0'))
    repeated['id']='31-repeated-numeric-use'
    repeated['analysis']['results']['citation_order']['use']['is_first_use']=observed(False,['use'])
    cases.append(repeated)
    grouped=copy.deepcopy(next(c for c in cases if c['id']=='31-body-valid-4'))
    grouped['id']='31-grouped-author-year'
    group=next(n for n in grouped['ir']['nodes'] if n['id']=='group');group['text']='(Smith, 2020; Jones, 2021)';group['attrs']['marker']=group['text']
    grouped['analysis']['paper_ir_sha256']=ir_hash(grouped['ir']);citation_syntax(grouped['ir'],grouped['analysis'])
    grouped['analysis']['results']['citation_syntax']['group']['automatic_footnote']=observed(False,['group'])
    cases.append(grouped)
    malformed=copy.deepcopy(next(c for c in cases if c['id']=='31-body-valid-1'))
    malformed['id']='31-numeric-semicolon';malformed['status']='VIOLATION';malformed['basis_ids']=['gbt7714-2025:9.1-9.2']
    group=next(n for n in malformed['ir']['nodes'] if n['id']=='group');group['text']='[1;3]';group['attrs']['marker']=group['text']
    malformed['analysis']['paper_ir_sha256']=ir_hash(malformed['ir']);citation_syntax(malformed['ir'],malformed['analysis'])
    malformed['analysis']['results']['citation_syntax']['group']['automatic_footnote']=observed(False,['group'])
    cases.append(malformed)
    wrapped=make('physical-line-wrap',typ='EB')
    wrapped['ir']['nodes'][1]['text']=wrapped['ir']['nodes'][1]['text'].replace(' https://','\nhttps://')
    wrapped['analysis']['paper_ir_sha256']=ir_hash(wrapped['ir']);cases.append(wrapped)
    return cases
