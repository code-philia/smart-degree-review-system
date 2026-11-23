"""Regenerate only verified program headings after a locator mapping repair."""
import copy

import pytest

import numeric_consistency as n
from test_numeric_consistency import fixture


def repaired_case():
    ir,facts,data=fixture()
    model=n.source_model(ir)
    data['declarations'][0]['method']='FusionNet'
    model['blocks'].append({'block_id':'name:p5','source_node_id':'name','section_id':'ch','page':5,'block_type':'Paragraph','text':'融合模型FusionNet方法。','provenance':[]})
    model['sections']['other']['title']='第四章 FusionNet实验评估'
    model['blocks'].append({'block_id':'eval:p10','source_node_id':'eval','section_id':'other','page':10,'block_type':'Paragraph','text':'本章评估FusionNet方法。','provenance':[]})
    model['sections']['exp2']={'section_id':'exp2','parent_id':'other','heading_node_id':'eh2','title':'4.2 实验结果','level':2,'block_ids':['eh2:p11']}
    model['blocks'].append({'block_id':'eh2:p11','source_node_id':'eh2','section_id':'exp2','page':11,'block_type':'Heading','text':'4.2 实验结果','provenance':[]})
    context=n.structure_context(facts,model)
    data['mappings'][0].pop('evidence')
    old=n.resolve_structure(data,context,model)
    assert old['mappings'][0]['evidence'][0]['source_node_id']=='eh'
    fixed=copy.deepcopy(old)
    fixed['mappings'][0].update(chapter_id='other',experiment_section_ids=['exp2'])
    return fixed,context,model


def test_verified_program_heading_is_regenerated_for_the_repaired_scope():
    fixed,context,model=repaired_case()
    result=n.resolve_structure(fixed,context,model)
    assert result['mappings'][0]['evidence']==[{'source_node_id':'eh2','quote':'4.2 实验结果','page':11,'quote_origin':'program_section_heading'}]
    assert n.validate_structure(result,context,model)
    assert fixed['mappings'][0]['evidence'][0]['source_node_id']=='eh'


def test_forged_program_heading_is_not_silently_discarded():
    fixed,context,model=repaired_case()
    fixed['mappings'][0]['evidence'][0]['quote']='并不存在的标题'
    result=n.resolve_structure(fixed,context,model)
    assert result['mappings'][0]['evidence'][0]['quote']=='并不存在的标题'
    with pytest.raises(n.ContractError):n.validate_structure(result,context,model)


def test_explicit_model_evidence_is_not_replaced_by_a_heading():
    fixed,context,model=repaired_case()
    fixed['mappings'][0]['evidence'][0].pop('quote_origin')
    result=n.resolve_structure(fixed,context,model)
    assert result['mappings'][0]['evidence']==fixed['mappings'][0]['evidence']
    with pytest.raises(n.ContractError):n.validate_structure(result,context,model)


def test_native_heading_recovery_cannot_authorize_an_unrelated_method_chapter():
    fixed,context,model=repaired_case()
    model['blocks']=[b for b in model['blocks'] if b['source_node_id']!='eval']
    result=n.resolve_structure(fixed,context,model)
    with pytest.raises(n.ContractError,match='named method'):
        n.validate_structure(result,context,model)


def test_locator_prompt_admits_a_source_supported_separate_evaluation_chapter():
    fixed, context, model = repaired_case()
    resolved = n.resolve_structure(fixed, context, model)
    assert n.validate_structure(resolved, context, model)
    prompt = n.structure_prompt(context)
    assert '选择该评估主章' in prompt
    assert '不能使用独立统一实验章' not in prompt
    assert '实验子章节必须属于对应研究章节' in prompt
