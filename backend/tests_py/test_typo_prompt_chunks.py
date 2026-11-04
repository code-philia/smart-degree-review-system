import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('typo', Path(__file__).parents[1] / 'scripts' / 'run_bilingual_semantic_lint.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def test_chunks_follow_body_and_bound_size():
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p1','p2']},
        {'id':'p1','kind':'Paragraph','text':'alpha','provenance':[{'page_index':2}]},
        {'id':'p2','kind':'Paragraph','text':'beta','provenance':[{'page_index':3}]},
    ]}
    chunks = mod._body_chunks(ir, size=6)
    assert [item['text'] for item in chunks] == ['alpha', 'beta']
    assert [item['page'] for item in chunks] == [3, 4]

def test_prompt_excludes_line_break_hyphen_as_error():
    prompt = mod.typo_prompt('re-\nverse')
    assert '跨行连字符' in prompt and '不得报告' in prompt
    assert '严格 JSON' in prompt


def test_chinese_extraction_space_is_not_a_typo_and_other_finding_has_bbox(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph','text':'剔 除，錯字。re-\nverse','provenance':[{'page_index':4,'bbox':[10,20,100,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': [
        {'text':'剔 除','suggestion':'剔除','reason':'提取空格','confidence':0.99},
        {'text':'錯字','suggestion':'错字','reason':'字形错误','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': False},
        {'text':'re-\nverse','suggestion':'reverse','reason':'换行','confidence':0.99},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    result = mod.run_typo_rule_from_ir(ir)
    assert len(result['findings']) == 1
    assert result['findings'][0]['message'] == '疑似错别字：錯字'
    assert result['findings'][0]['location']['type'] == 'pdf_bbox'
    assert result['findings'][0]['location']['page_number'] == 5


def test_chinese_finding_without_required_evidence_is_rejected(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph','text':'该方案可以降低至较低开销。',
         'provenance':[{'page_index':0,'bbox':[10,20,100,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': [
        {'text':'降低至','suggestion':'降至','reason':'无充分证据','confidence':0.99,
         'common_confusion': False, 'semantic_validity': True,
         'stable_usage': False, 'context_proof': False},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    assert mod.run_typo_rule_from_ir(ir)['findings'] == []


def test_duplicate_source_span_is_reported_once(monkeypatch):
    ir = {'layout': {'pages': [{'page_index': 0, 'width': 595, 'height': 842}]},
          'nodes': [
              {'id':'body','kind':'Body','children':['section']},
              {'id':'section','kind':'Section','children':['p']},
              {'id':'p','kind':'Paragraph','text':'正文包含錯字，需要修正。',
               'provenance':[{'page_index':0,'bbox':[10,20,100,40]}]},
          ]}
    response = {'findings': [
        {'text':'錯字','suggestion':'错字','reason':'字形错误','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': False},
        {'text':'錯字','suggestion':'错字','reason':'重复返回','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': False},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: (response, {'input_tokens': 1, 'output_tokens': 1}))
    assert len(mod.run_typo_rule_from_ir(ir)['findings']) == 1


def test_multi_character_chinese_typo_inside_prose_is_not_lost(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph','text':'系统尚未完成布署，因此暂不发布。',
         'provenance':[{'page_index':0,'bbox':[10,20,100,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': [
        {'text':'布署','suggestion':'部署','reason':'常见异形误写','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': False},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    assert [item['message'] for item in mod.run_typo_rule_from_ir(ir)['findings']] == ['疑似错别字：布署']


def test_phrase_rewrite_and_valid_lower_to_are_not_typo_findings(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph','text':'开销降低至原来的一半，并计片外传输量。',
         'provenance':[{'page_index':0,'bbox':[10,20,100,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': [
        {'text':'降低至','suggestion':'降低到','reason':'错误改写','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': True},
        {'text':'计片外传输量','suggestion':'累计片外传输量','reason':'扩写短语','confidence':0.99,
         'common_confusion': True, 'semantic_validity': True,
         'stable_usage': True, 'context_proof': True},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    assert mod.run_typo_rule_from_ir(ir)['findings'] == []


def test_high_confidence_cjk_confusions_cover_mutations_without_model(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph',
         'text':'进一不优化；一次布署完成。结果共同表名，自动分祈与模形训练有效。',
         'provenance':[{'page_index':0,'bbox':[10,20,300,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': []},
                                                                  {'input_tokens': 1, 'output_tokens': 1}))
    findings = mod.run_typo_rule_from_ir(ir)['findings']
    assert [(item['message'], item['suggestion']) for item in findings] == [
        ('疑似错别字：进一不', '进一步'), ('疑似错别字：布署', '部署'),
        ('疑似错别字：表名', '表明'), ('疑似错别字：分祈', '分析'),
        ('疑似错别字：模形', '模型'),
    ]


def test_cjk_line_break_is_joined_for_model_without_losing_segment_offsets():
    text = '介绍了室内定位技术、基于指\n纹技术室内定位。'
    ir = {'layout': {'pages': [{'page_index': 0, 'width': 595, 'height': 842}]},
          'nodes': [
              {'id': 'body', 'kind': 'Body', 'children': ['p']},
              {'id': 'p', 'kind': 'Paragraph', 'text': text, 'provenance': [
                  {'page_index': 0, 'bbox': [1, 2, 200, 12], 'node_text_start': 0, 'node_text_end': 14},
                  {'page_index': 0, 'bbox': [1, 20, 200, 30], 'node_text_start': 14, 'node_text_end': len(text)},
              ]},
          ]}
    chunk = mod._body_chunks(ir)[0]
    assert '指纹技术室内定位' in chunk['model_text']
    assert '\n纹技术' not in chunk['model_text']
    assert chunk['model_text'].find('纹技术') == chunk['segments'][1]['start']
