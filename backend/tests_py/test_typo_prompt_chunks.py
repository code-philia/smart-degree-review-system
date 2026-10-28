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
