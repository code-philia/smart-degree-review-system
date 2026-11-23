"""Experimental setup is source context, not stand-alone result evidence."""
import copy

import numeric_consistency as n
from test_numeric_definition_candidates import decl
from test_numeric_metric_evidence import block, model, section, MAPPING
from test_numeric_statistical_evidence import average_row


def setup_case():
    text = ('本实验在DeviceA上运行。DialogSet数据由用户真实对话记录收集，'
            '每条样本包含多轮问答，用于构建多用户多轮对话实验。')
    source = model(block('setup', 'setup', text),
                   block('result', 'experiment', '平均绝对误差为5.3934 kcal/mol。'))
    source['sections']['setup'] = section('setup', 'chapter', '5.1 实验环境与配置')
    return text, source


def test_sibling_native_setup_reaches_verifier_with_exact_source_identity():
    text, source = setup_case()
    before = copy.deepcopy(source)
    candidates, _ = n.retrieve_candidates([decl()], [MAPPING], source)
    context = [c for c in candidates if c.get('evidence_role') == 'experiment_context']
    assert [c['text'] for c in context] == [text]
    assert context[0]['block_id'] == 'setup'
    assert context[0]['source_node_id'] == 'setup-node'
    native = source['blocks'][0]['provenance'][0]
    assert {key: context[0]['provenance'][0][key] for key in native} == native
    assert context[0]['provenance'][0]['quote_text_start'] == 0
    assert context[0]['provenance'][0]['quote_text_end'] == len(text)
    assert source == before


def test_setup_from_other_method_or_chapter_is_not_imported():
    _, source = setup_case()
    source['sections']['other-setup'] = section('other-setup', 'other-method', '实验环境与配置')
    source['sections']['foreign-setup'] = section('foreign-setup', 'other-chapter', 'Experimental setup')
    source['blocks'].extend([block('other', 'other-setup', 'OtherModel uses DeviceB and another dataset.'),
                             block('foreign', 'foreign-setup', 'A different research chapter uses DeviceC.')])
    candidates, _ = n.retrieve_candidates([decl()], [MAPPING], source)
    assert [c['block_id'] for c in candidates if c.get('evidence_role') == 'experiment_context'] == ['setup']


def test_setup_alone_cannot_validate_a_numeric_result():
    _, source = setup_case()
    candidates, _ = n.retrieve_candidates([decl()], [MAPPING], source)
    context = next(c for c in candidates if c.get('evidence_role') == 'experiment_context')
    payload = {'results': [{'declaration_id': 'd1', 'status': 'consistent', 'reason': '环境已明确',
                           'suggestion': '', 'evidence': [{'candidate_id': context['candidate_id']}]}]}
    results, errors = n.validated_results(n.resolve_citations(payload, candidates), [decl()], candidates)
    assert errors and results[0]['status'] == 'execution_error'
    assert 'supporting_evidence_required' in errors[0]['errors']


def test_setup_average_input_length_cannot_establish_mean_metric_semantics():
    row = average_row(metric='平均SSE')
    row['evidence'][0]['quote'] = 'ProposedModel SSE 5.3934'
    row['evidence'].append({'candidate_id': 'setup', 'quote': '平均输入长度为512。',
                            'evidence_role': 'experiment_context'})
    n.conservative_evidence_guard([row], model=model(), mappings=[MAPPING])
    assert row['status'] == 'inconclusive'
