import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('typo', Path(__file__).parents[1] / 'scripts' / 'run_bilingual_semantic_lint.py')
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def ir_for(text):
    return {'layout': {'pages': [{'page_index': 0, 'width': 595, 'height': 842}]}, 'nodes': [
        {'id': 'body', 'kind': 'Body', 'children': ['p']},
        {'id': 'p', 'kind': 'Paragraph', 'text': text,
         'provenance': [{'page_index': 0, 'bbox': [10, 20, 300, 40]}]},
    ]}


def test_chunks_follow_body_and_bound_size():
    ir = {'nodes': [
        {'id': 'body', 'kind': 'Body', 'children': ['section']},
        {'id': 'section', 'kind': 'Section', 'children': ['p1', 'p2']},
        {'id': 'p1', 'kind': 'Paragraph', 'text': 'alpha', 'provenance': [{'page_index': 2}]},
        {'id': 'p2', 'kind': 'Paragraph', 'text': 'beta', 'provenance': [{'page_index': 3}]},
    ]}
    chunks = mod._body_chunks(ir, size=6)
    assert [item['text'] for item in chunks] == ['alpha', 'beta']
    assert [item['page'] for item in chunks] == [3, 4]


def test_prompt_is_the_strict_chinese_typo_schema():
    prompt = mod.typo_prompt('测试段落')
    assert '中文学术论文错别字检测器' in prompt
    assert '"errors"' in prompt
    assert '无法在原文中精确定位' in prompt


def test_only_exact_single_character_replacement_is_accepted(monkeypatch):
    ir = ir_for('剔 除，錯字。re-\nverse')
    def fake_request(messages):
        if '候选复核器' in messages[0]['content']:
            if '候选原字：剔' in messages[0]['content']:
                return {'accepted': False, 'reason': '同义替换'}, {'input_tokens': 1, 'output_tokens': 1}
            return {'accepted': True, 'reason': '确认'}, {'input_tokens': 1, 'output_tokens': 1}
        return {'errors': [
            {'original': '錯', 'corrected': '错', 'context': '剔除，錯字。re-verse', 'reason': '“錯”是“错”的字形误用'},
            {'original': 'r', 'corrected': 'R', 'context': 're-verse', 'reason': '大小写'},
            {'original': '剔除', 'corrected': '删除', 'context': '剔除，錯字。re-verse', 'reason': '改写'},
        ]}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    result = mod.run_typo_rule_from_ir(ir)
    assert [item['message'] for item in result['findings']] == ['疑似错别字：錯']
    assert result['findings'][0]['suggestion'] == '错'
    assert result['findings'][0]['location']['type'] == 'pdf_bbox'
    assert result['findings'][0]['location']['page_number'] == 1


def test_one_changed_character_in_a_model_word_pair_is_reduced(monkeypatch):
    def fake_request(messages):
        if '候选复核器' in messages[0]['content']:
            return {'accepted': True, 'reason': '确认'}, {'input_tokens': 1, 'output_tokens': 1}
        return {'errors': [
            {'original': '布署', 'corrected': '部署', 'context': '系统尚未完成布署，因此暂不发布', 'reason': '固定词语'},
        ]}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    result = mod.run_typo_rule_from_ir(ir_for('系统尚未完成布署，因此暂不发布。'))
    assert [(item['message'], item['suggestion']) for item in result['findings']] == [('疑似错别字：布', '部')]


def test_field_reviewer_can_repair_a_malformed_discovery_pair(monkeypatch):
    def fake_request(messages):
        prompt = messages[0]['content']
        if '候选字段复核器' in prompt:
            return {'accepted': True, 'original': '名', 'corrected': '明', 'reason': '“表名”应为“表明”'}, {'input_tokens': 1, 'output_tokens': 1}
        if '候选复核器' in prompt:
            return {'accepted': True, 'reason': '确认'}, {'input_tokens': 1, 'output_tokens': 1}
        return {'errors': [
            {'original': '表', 'corrected': '表', 'context': '它们共同表名，任务通信', 'reason': '“表名”应为“表明”，名应为明'},
        ]}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    result = mod.run_typo_rule_from_ir(ir_for('它们共同表名，任务通信需要保留结构。'))
    assert [(item['message'], item['suggestion']) for item in result['findings']] == [('疑似错别字：名', '明')]


def test_field_reviewer_cannot_invent_a_replacement(monkeypatch):
    def fake_request(messages):
        prompt = messages[0]['content']
        if '候选字段复核器' in prompt:
            return {'accepted': True, 'original': '模', 'corrected': '模', 'reason': '字段仍不合法'}, {'input_tokens': 1, 'output_tokens': 1}
        return {'errors': [
            {'original': '模', 'corrected': '模', 'context': '当模形规模超出片上容量时', 'reason': '候选字段错误'},
        ]}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    assert mod.run_typo_rule_from_ir(ir_for('当模形规模超出片上容量时。'))['findings'] == []


def test_context_must_match_target_chunk(monkeypatch):
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'errors': [
        {'original': '布', 'corrected': '部', 'context': '不存在的上下文', 'reason': '固定词语'},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    assert mod.run_typo_rule_from_ir(ir_for('系统尚未完成布署，因此暂不发布。'))['findings'] == []


def test_duplicate_source_span_is_reported_once(monkeypatch):
    response = {'errors': [
        {'original': '錯', 'corrected': '错', 'context': '正文包含錯字，需要修正。', 'reason': '字形错误'},
        {'original': '錯', 'corrected': '错', 'context': '正文包含錯字，需要修正。', 'reason': '重复返回'},
    ]}
    def fake_request(messages):
        if '候选复核器' in messages[0]['content']:
            return {'accepted': True, 'reason': '确认'}, {'input_tokens': 1, 'output_tokens': 1}
        return response, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    assert len(mod.run_typo_rule_from_ir(ir_for('正文包含錯字，需要修正。'))['findings']) == 1


def test_no_hardcoded_typo_fallback_when_model_returns_empty(monkeypatch):
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'errors': []}, {'input_tokens': 1, 'output_tokens': 1}))
    assert mod.run_typo_rule_from_ir(ir_for('系统尚未完成布署。'))['findings'] == []


def test_unconfirmed_candidate_is_not_reported(monkeypatch):
    def fake_request(messages):
        if '候选复核器' in messages[0]['content']:
            return {'accepted': False, 'reason': '原文表达可成立'}, {'input_tokens': 1, 'output_tokens': 1}
        return {'errors': [
            {'original': '布', 'corrected': '部', 'context': '系统尚未完成布署', 'reason': '候选'},
        ]}, {'input_tokens': 1, 'output_tokens': 1}
    monkeypatch.setattr(mod, 'request_json', fake_request)
    assert mod.run_typo_rule_from_ir(ir_for('系统尚未完成布署。'))['findings'] == []


def test_cjk_line_break_is_joined_for_model_without_losing_segment_offsets():
    text = '介绍了室内定位技术、基于指\n纹技术室内定位。'
    ir = {'layout': {'pages': [{'page_index': 0, 'width': 595, 'height': 842}]}, 'nodes': [
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


def test_nearby_technical_identifier_does_not_hide_chinese_candidate():
    text = '面向FPGA加速的研究中，在一次布署中的相应位置。后续PU3调用foo()。'
    position = text.index('布')
    assert mod._looks_like_code_context(text, position, position + 1) is False
