"""Atomic verification targets keep adjacent numerical claims as context only."""
import copy
import json

import pytest

import numeric_consistency as n
from test_numeric_consistency import fixture


def declaration(text, number='3.57'):
    return {'id':'d1','contribution_id':'c1','number':number,'metric':'平均误差',
            'unit':'m','comparison':'absolute','condition':'空旷区域，指纹定位',
            'dataset':'','method':'指纹定位','baseline':'','text':text}


def test_non_percentage_source_clause_does_not_retain_other_method_clause():
    _, _, structure = fixture()
    text='实验在空旷区域、自习区域和书架区域开展。指纹定位平均误差分别为3.57 m、3.69 m和3.62 m，传播模型分别为3.73 m、4.01 m和3.79 m。'
    row=declaration(text);row.pop('text');row['abstract_span_id']='a1'
    structure['contributions']=[];structure['declarations']=[row];structure['mappings']=[]
    result=n.resolve_structure(structure,{'abstract_spans':[{'id':'a1','text':text}]},{'sections':{}})
    assert '3.57' in result['declarations'][0]['text']
    assert '传播模型' not in result['declarations'][0]['text']
    assert result['declarations'][0]['source_context'] == text
    assert 'text' not in row


def test_verifier_has_one_atomic_target_and_separate_grounded_source_context():
    text='指纹定位平均误差分别为3.57 m、3.69 m和3.62 m；传播模型分别为3.73 m、4.01 m和3.79 m。'
    d=declaration(text)
    source=copy.deepcopy(d)
    prompt=n.verifier_prompt({'declarations':[d],'mappings':[]},[])
    task=json.loads(prompt.split('\n输入：\n',1)[1])['tasks'][0]
    target=task['verification_target']
    assert target['number']=='3.57'
    assert target['condition']=='空旷区域，指纹定位'
    assert target['method']=='指纹定位'
    assert task['source_context']==text
    assert target['source_numbers']==[{'text':'3.57','start':text.index('3.57'),'end':text.index('3.57')+4}]
    assert d==source


def test_repeated_source_value_keeps_ambiguity_instead_of_fabricating_one_anchor():
    text='A条件误差3.57 m，B条件误差3.57 m。'
    task=json.loads(n.verifier_prompt({'declarations':[declaration(text)],'mappings':[]},[]).split('\n输入：\n',1)[1])['tasks'][0]
    assert len(task['verification_target']['source_numbers'])==2
    assert task['verification_target']['ambiguous_source_number'] is True
    assert task['source_context']==text


def test_range_target_preserves_both_native_endpoints():
    d=declaration('子知识库规模在16384至200000之间。','16384-200000')
    d.update(metric='规模',unit='',comparison='range',condition='子知识库')
    target=json.loads(n.verifier_prompt({'declarations':[d],'mappings':[]},[]).split('\n输入：\n',1)[1])['tasks'][0]['verification_target']
    assert target['number']=='16384-200000'
    assert [x['text'] for x in target['source_numbers']]==['16384','200000']
    assert target['ambiguous_source_number'] is False


def test_unrelated_metric_index_is_not_part_of_target_source_number():
    d=declaration('Pass@1、Pass@3、F1作为指标，其中平均误差3.57 m。')
    target=json.loads(n.verifier_prompt({'declarations':[d],'mappings':[]},[]).split('\n输入：\n',1)[1])['tasks'][0]['verification_target']
    assert [x['text'] for x in target['source_numbers']]==['3.57']


def test_unsupported_target_number_is_not_sent_to_verifier():
    d=declaration('当前条件误差3.69 m。')
    with pytest.raises(n.ContractError):
        n.verifier_prompt({'declarations':[d],'mappings':[]},[])


def test_atomic_target_keeps_full_abstract_condition_as_separate_native_context():
    d = declaration('在DatasetA上取得3.57 m。')
    d['source_context'] = '以粗糙输入计算平均误差，在DatasetA上取得3.57 m，另一条件为3.69 m。'
    task = json.loads(n.verifier_prompt({'declarations':[d],'mappings':[]},[]).split('\n输入：\n',1)[1])['tasks'][0]
    assert task['source_context'] == d['source_context']
    assert task['verification_target']['number'] == '3.57'


def test_anaphoric_target_retains_its_native_preceding_baseline_sentence():
    text = '实验结果优于代表性基线方法。其中，相关方法最高提升17.61%。'
    context = {'abstract': text, 'abstract_spans': n.abstract_spans(text)}
    row = declaration('', '17.61'); row.pop('text')
    row.update(abstract_span_id='a2', metric='Recall/NDCG', unit='%')
    result = n.resolve_structure({'contributions': [], 'declarations': [row], 'mappings': []}, context, {'sections': {}})
    assert result['declarations'][0]['source_context'] == text
    assert '17.61' in result['declarations'][0]['text']
    assert '基线' not in result['declarations'][0]['text']
