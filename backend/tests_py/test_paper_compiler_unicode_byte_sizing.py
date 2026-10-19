import copy
from paper_compiler import analysis,model_runtime,program_analysis

def test_analysis_batch_retains_lone_surrogate():
    nodes=[{'id':'e1','text':'Formula \ud8351'},{'id':'e2','text':'Title'}]
    before=copy.deepcopy(nodes)
    assert list(analysis._bibliography_batches(nodes,8,128*1024))==[nodes]
    assert nodes==before

def test_classification_batch_retains_source_math_text():
    source={'id':'p','kind':'Paragraph','text':'\ud8351, \ud8352, \ud835\ud835'}
    model={'version':'paper-model/1.0'}
    rows=list(model_runtime._classification_batches([{'id':'s'}],{'s':[source]},model,{},8))
    assert rows[0]['sources'][0]['text']==source['text']

def test_program_input_size_handles_lone_surrogate_and_keeps_valid_unicode_size():
    data={'text':'\ud8351'}
    before=copy.deepcopy(data)
    assert program_analysis._batch_utf8_bytes(data)>0
    assert data==before
    import json
    good={'text':'中文α∑𝛼'}
    assert program_analysis._batch_utf8_bytes(good)==len(json.dumps(good,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
