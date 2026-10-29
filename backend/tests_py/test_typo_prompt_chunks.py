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
    assert '不要把 PDF 跨行连字符' in prompt
    assert '严格 JSON' in prompt


def test_chinese_extraction_space_is_not_a_typo_and_other_finding_has_bbox(monkeypatch):
    ir = {'nodes': [
        {'id':'body','kind':'Body','children':['section']},
        {'id':'section','kind':'Section','children':['p']},
        {'id':'p','kind':'Paragraph','text':'这是剔 除和錯字。','provenance':[{'page_index':4,'bbox':[10,20,100,40]}]},
    ]}
    monkeypatch.setattr(mod, 'request_json', lambda _messages: ({'findings': [
        {'text':'剔 除','suggestion':'剔除','reason':'提取空格'},
        {'text':'錯字','suggestion':'错字','reason':'字形错误'},
    ]}, {'input_tokens': 1, 'output_tokens': 1}))
    result = mod.run_typo_rule_from_ir(ir)
    assert len(result['findings']) == 1
    assert result['findings'][0]['message'] == '疑似错别字：錯字'
    assert result['findings'][0]['location']['type'] == 'pdf_bbox'
    assert result['findings'][0]['location']['page_number'] == 5


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
