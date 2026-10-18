"""Source IR edits and sealed evaluation metadata; no answers enter detector input."""
import copy
import re
from .contracts import ir_hash,validate_ir
from .citations import attach_citations

class MutationError(ValueError):pass

def mutate(ir:dict,recipe:dict):
    def need(condition,message):
        if not condition:raise MutationError(message)
    before=ir_hash(ir);need(before==recipe.get('parent_sha256'),'parent hash precondition failed')
    need(recipe.get('operation')=='replace_text','unsupported mutation operation')
    need(isinstance(recipe.get('mutation_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',recipe['mutation_id']),'invalid mutation ID')
    changed=copy.deepcopy(ir);node=next((n for n in changed['nodes'] if n['id']==recipe.get('node_id')),None)
    need(node is not None and node['kind'] in {'BibliographyEntry','Paragraph','Caption'},'unsupported or missing mutation target')
    text=node['text'];start,end=recipe.get('start'),recipe.get('end');replacement=recipe.get('replacement')
    need(isinstance(text,str) and type(start)is int and type(end)is int and 0<=start<=end<=len(text),'invalid replacement range')
    need(isinstance(replacement,str) and len(replacement)<=20000,'invalid replacement text')
    need(text[start:end]==recipe.get('old_text'),'source substring precondition failed')
    need(text[start:end]!=replacement,'mutation must change source content')
    node['text']=text[:start]+replacement+text[end:]
    node['provenance']=[{'kind':'synthetic','operation_id':recipe['mutation_id'],'ancestor_provenance':copy.deepcopy(node['provenance'])}]
    if node['kind']=='BibliographyEntry':
        node['attrs']={**node['attrs'],'resource_type':{'state':'unknown','reason':'source content changed; rederive type'},'fields':{}}
    if node['kind'] in {'Paragraph','Caption'}:
        # Re-derive all citation uses to avoid stale spans and IDs; untouched paragraphs retain their source provenance.
        remove={n['id'] for n in changed['nodes'] if n['kind'] in {'CitationGroup','ReferenceUse'}}
        changed['nodes']=[n for n in changed['nodes'] if n['id'] not in remove]
        for n in changed['nodes']:n['children']=[c for c in n['children'] if c not in remove]
        attach_citations(changed)
    changed['revision']='mutation-'+recipe['mutation_id']
    changed['metadata']={**changed.get('metadata',{}),'derivation':{'parent_sha256':before,'operation_id':recipe['mutation_id']}}
    validate_ir(changed)
    oracle={'schema_version':'mutation-oracle/1.0','mutation_id':recipe['mutation_id'],'parent_sha256':before,'mutant_sha256':ir_hash(changed),
        'rule_id':str(recipe['rule_id']),'target_node_id':recipe.get('target_node_id',node['id']),'target_check_id':recipe.get('target_check_id'),
        'status':recipe['status'],'evidence_domain':recipe.get('evidence_domain','unverified'),'valid':recipe.get('valid',False),
        'independent_basis':recipe.get('independent_basis'),'source_edit':{'node_id':node['id'],'start':start,'end':end,'old_text':recipe['old_text'],'replacement':replacement}}
    return changed,oracle
