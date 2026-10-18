
import pytest
from test_paper_compiler_compiler import fixture

def test_format_source_predicate(tmp_path):
    from paper_compiler.experiment import format_recipe
    from paper_compiler.mutations import mutate
    ir,_=fixture(tmp_path);ir['nodes'][-1]['text']='[1] Smith. Title[J]. Journal, 2020.'
    changed,oracle=mutate(ir,format_recipe(ir,'entry','type-required'))
    assert '[J]' not in changed['nodes'][-1]['text']
    assert oracle['valid'] and oracle['status']=='VIOLATION'

def test_multiple_markers_do_not_make_valid_oracle(tmp_path):
    from paper_compiler.experiment import format_recipe
    ir,_=fixture(tmp_path);ir['nodes'][-1]['text']='One[J]. Two[M].'
    with pytest.raises(ValueError,match='marker'):format_recipe(ir,'entry','type-required')

def test_semantic_oracle_requires_quotes_and_exclusion():
    from paper_compiler.experiment import validate_semantic_oracle
    a={'original_supported':True,'replacement_excluded':True,'basis':'explicit_scope_contradiction','intent_quote':'claim','original_quote':'support','replacement_quote':'scope','alternatives_excluded':'methods excluded','reason':'incompatible object'}
    assert validate_semantic_oracle(a,'claim','support','scope')
    assert not validate_semantic_oracle({**a,'replacement_quote':'invented'},'claim','support','scope')
    assert not validate_semantic_oracle({**a,'basis':'missing_detail'},'claim','support','scope')

def test_identity_control_needs_verified_original(tmp_path):
    from paper_compiler.experiment import identity_recipe
    ir,a=fixture(tmp_path)
    with pytest.raises(ValueError,match='identity'):identity_recipe(ir,a,'entry','exists')
    a['results']['external_work']={'entry':{'exists':{'state':'observed','value':True,'evidence_ids':['record']}}}
    assert identity_recipe(ir,a,'entry','exists')['status']=='PASS'
