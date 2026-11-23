"""Native definitions accompany data but cannot substitute for result evidence."""
import json

import numeric_consistency as n
from test_numeric_metric_evidence import block, model, MAPPING


def decl():
    return {'id':'d1','number':'5.3934','metric':'平均绝对误差','unit':'kcal/mol','comparison':'absolute',
            'condition':'','dataset':'','method':'','baseline':'','text':'平均绝对误差5.3934 kcal/mol。'}


def test_native_pre_experiment_metric_definition_is_available_to_verifier():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为绝对误差的均值。'),
                 block('result','experiment','本模型的MAE为5.3934 kcal/mol。'))
    candidates,traces=n.retrieve_candidates([decl()],[MAPPING],source)
    context=[c for c in candidates if c.get('evidence_role')=='metric_definition']
    assert context and context[0]['text']=='平均绝对误差（MAE）定义为绝对误差的均值。'
    assert context[0]['source_node_id']=='definition-node'
    assert context[0]['is_primary'] is False
    assert context[0]['page']==20
    prompt=n.verifier_prompt({'declarations':[decl()],'mappings':[MAPPING]},candidates)
    public=json.loads(prompt.split('\n输入：\n',1)[1])['tasks'][0]['candidates']
    assert any(c.get('evidence_role')=='metric_definition' for c in public)


def test_definition_alone_cannot_validate_a_numerical_verdict():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为绝对误差的均值。'))
    candidates,_=n.retrieve_candidates([decl()],[MAPPING],source)
    context=next(c for c in candidates if c.get('evidence_role')=='metric_definition')
    payload={'results':[{'declaration_id':'d1','status':'consistent','reason':'指标有定义','suggestion':'',
                         'evidence':[{'candidate_id':context['candidate_id']}]}]}
    checked=n.resolve_citations(payload,candidates)
    results,errors=n.validated_results(checked,[decl()],candidates)
    assert errors and results[0]['status']=='execution_error'
    assert 'supporting_evidence_required' in errors[0]['errors']


def test_surrogate_source_quotes_stay_exact_but_verifier_prompt_is_utf8_encodable():
    d=decl();d['text']+='原式字形\ud835。'
    prompt=n.verifier_prompt({'declarations':[d],'mappings':[]},[])
    prompt.encode('utf-8')
    assert json.loads(prompt.split('\n输入：\n',1)[1])['tasks'][0]['source_context']==d['text']
