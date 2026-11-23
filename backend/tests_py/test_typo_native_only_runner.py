from pathlib import Path
import pymupdf
from unittest.mock import patch
import run_bilingual_semantic_lint as lint
from paper_compiler.frontend import _build_source_tree

def image():
    with pymupdf.open() as doc:
        p=doc.new_page(width=600,height=800)
        p.insert_text((60,100),'Scanned paper page')
        return p.get_pixmap().tobytes('png')

def make_ir(tmp_path, native=False):
    path=tmp_path/'input.pdf'
    with pymupdf.open() as doc:
        if native:
            p=doc.new_page(width=600,height=800)
            p.insert_text((60,80),'Chapter 1 Introduction',fontsize=18)
            p.insert_text((60,130),'实验使用该方法分祈数据。',fontname='china-s',fontsize=12)
        p=doc.new_page(width=600,height=800)
        p.insert_image(p.rect,stream=image())
        p.insert_text((60,130),'扫描误识别多轮对活场景。',fontname='china-s',fontsize=12,render_mode=3)
        doc.save(path)
    return _build_source_tree(path,include_citations=False)

def test_all_scanned_pages_make_no_model_or_ocr_requests(tmp_path):
    ir=make_ir(tmp_path)
    with patch.object(lint,'request_json',side_effect=AssertionError('scan must not reach model')) as model, \
         patch.object(pymupdf.Page,'get_textpage_ocr',side_effect=AssertionError('OCR forbidden')):
        result=lint.run_typo_rule_from_ir(ir,max_workers=1)
    assert model.call_count==0
    assert result['outcome']=='inconclusive'
    assert result['findings']==[]
    assert result['params']['native_text_scope']['coverage']=='none'

def test_absent_pdf_provenance_makes_no_model_requests():
    ir={'nodes':[{'id':'body','kind':'Body','children':['p']},
                 {'id':'p','kind':'Paragraph','text':'没有PDF来源的疑似对活文字。','children':[]} ]}
    with patch.object(lint,'request_json',return_value=({'errors':[]},{'input_tokens':1,'output_tokens':1})) as model:
        result=lint.run_typo_rule_from_ir(ir,max_workers=1)
    assert model.call_count==0
    assert result['outcome']=='inconclusive'

def test_native_typo_is_detected_while_adjacent_scan_stays_out(tmp_path):
    ir=make_ir(tmp_path,native=True)
    requests=[]
    def respond(messages,**kwargs):
        prompt=messages[0]['content'];requests.append(prompt)
        assert '对活' not in prompt
        if '候选复核器' in prompt:
            return {'accepted':True,'reason':'分析数据中的分析是固定搭配'}, {'input_tokens':1,'output_tokens':1}
        return {'errors':[{'original':'祈','corrected':'析','context':'实验使用该方法分祈数据。','reason':'分析数据的析字误写为祈'}]}, {'input_tokens':1,'output_tokens':1}
    with patch.object(lint,'request_json',side_effect=respond), \
         patch.object(pymupdf.Page,'get_textpage_ocr',side_effect=AssertionError('OCR forbidden')):
        result=lint.run_typo_rule_from_ir(ir,max_workers=1)
    assert requests
    assert [f['message'] for f in result['findings']]==['疑似错别字：祈']
    assert result['findings'][0]['location']['page_number']==1
    assert result['params']['native_text_scope']['scanned_pages']==[2]
