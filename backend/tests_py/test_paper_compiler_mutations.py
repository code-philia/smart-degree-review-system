import copy
import pytest
from paper_compiler.mutations import mutate,MutationError
from paper_compiler.contracts import ir_hash,validate_ir,validate_analysis
from test_paper_compiler_compiler import fixture


def recipe(ir):return {'mutation_id':'test-1','parent_sha256':ir_hash(ir),'operation':'replace_text','node_id':'entry','start':0,'end':5,'old_text':'Hello','replacement':'Changed','rule_id':'31','target_check_id':'title-required','status':'VIOLATION','evidence_domain':'source_format'}


def test_mutation_changes_source_ir_and_seals_expected_result(tmp_path):
    original,_=fixture(tmp_path);before=copy.deepcopy(original);changed,oracle=mutate(original,recipe(original))
    assert original==before and ir_hash(changed)!=ir_hash(original)
    node=next(n for n in changed['nodes'] if n['id']=='entry')
    assert node['text']=='Changed' and node['provenance'][0]['kind']=='synthetic'
    assert 'bbox' not in node['provenance'][0]
    assert node['provenance'][0]['ancestor_provenance']==before['nodes'][-1]['provenance']
    assert oracle['parent_sha256']==ir_hash(original) and oracle['mutant_sha256']==ir_hash(changed)
    assert "'expected':" not in str(changed) and 'VIOLATION' not in str(changed)
    validate_ir(changed,tmp_path)


def test_stale_analysis_is_invalidated_by_source_edit(tmp_path):
    ir,a=fixture(tmp_path);changed,_=mutate(ir,recipe(ir))
    with pytest.raises(ValueError,match='stale'):validate_analysis(changed,a)


@pytest.mark.parametrize('field,value',[('parent_sha256','bad'),('old_text','Not there'),('start',-1),('node_id','missing'),('replacement','Hello')])
def test_mutation_preconditions_are_enforced(tmp_path,field,value):
    ir,_=fixture(tmp_path);r=recipe(ir);r[field]=value
    with pytest.raises(MutationError):mutate(ir,r)


def test_body_mutation_rebuilds_reference_uses_without_source_impersonation(tmp_path):
    ir,_=fixture(tmp_path);r=recipe(ir);r.update(node_id='p',start=0,end=5,old_text='Hello',replacement='Unrelated purpose')
    changed,oracle=mutate(ir,r)
    uses=[n for n in changed['nodes'] if n['kind']=='ReferenceUse']
    assert len(uses)==1 and uses[0]['provenance'][0]['kind']=='synthetic'
    validate_ir(changed,tmp_path)

def test_bibliography_edit_invalidates_source_derived_attributes(tmp_path):
    ir,_=fixture(tmp_path)
    ir['nodes'][-1]['attrs'].update(resource_type='journal_article',fields={'title':'Hello'})
    changed,_=mutate(ir,recipe(ir))
    attrs=changed['nodes'][-1]['attrs']
    assert attrs['resource_type']['state']=='unknown'
    assert attrs['fields']=={}
    assert attrs['key']['state']=='unknown'

@pytest.mark.parametrize('replacement,expected',[('9','9'),('',None)])
def test_numeric_label_edit_rebuilds_key_and_reference_binding(tmp_path,replacement,expected):
    from paper_compiler.analysis import base_analysis,bind_references
    ir,_=fixture(tmp_path);ir['nodes'][-1]['text']='[1] Hello[J].'
    change=recipe(ir);change.update(start=1,end=2,old_text='1',replacement=replacement)
    changed,_=mutate(ir,change);key=changed['nodes'][-1]['attrs']['key']
    assert key==expected if expected else key['state']=='unknown'
    a=base_analysis(changed);bindings=bind_references(changed,a)
    assert all(b['status']=='unresolved' for b in bindings)
