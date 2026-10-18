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
            'citation_order':{'use':{'numeric_value':observed(1,['use']),'first_appearance_rank':observed(1,['use']),'is_first_use':observed(True,['use'])}}}
        basis_ids={'title':['general'],'type_code':['general'],'institution':['8.7'],'access_date':['8.11'],'standard_number':['8.8-8.9'],'patent_number':['8.10']}
        return {'id':'31-'+name,'ir':ii,'analysis':aa,'status':'PASS' if remove is None or optional else 'VIOLATION','basis_ids':['gbt7714-2025:'+x for x in basis_ids.get(remove,[])]}
    return [make('journal-without-optional-doi'),make('missing-title',remove='title'),make('missing-type-code',remove='type_code'),
        make('thesis-valid',typ='D'),make('thesis-missing-institution',typ='D',remove='institution'),
        make('web-valid',typ='EB'),make('web-missing-access-date',typ='EB',remove='access_date'),
        make('standard-valid',typ='S'),make('standard-missing-number',typ='S',remove='standard_number'),
        make('patent-valid',typ='P'),make('patent-missing-application-number',typ='P',remove='patent_number')]
