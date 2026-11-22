"""Native-PDF regressions for separate Chinese and English keyword counts."""
import sys
from pathlib import Path
import pytest
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paper_compiler.frontend import _build_source_tree
from paper_compiler.local_checks import detect_ir

MESSAGE = '关键词共{}个，按最新国标要求关键词为3-8个，该范围为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新。'

def paper(tmp_path, chinese=('关键词：软件；分析；检测',), english=('Keywords: software; analysis; review',), body_keywords=None, continuation_x=110):
    path = tmp_path/'keywords.pdf'
    with pymupdf.open() as doc:
        def page(title, prose, terms):
            p=doc.new_page(width=600,height=800)
            p.insert_text((60,90),title,fontname='helv' if title.isascii() else 'china-s',fontsize=18)
            p.insert_text((60,140),prose,fontname='helv' if prose.isascii() else 'china-s',fontsize=12)
            for i,text in enumerate(terms): p.insert_text((60 if i==0 else continuation_x,210+i*22),text,fontname='helv' if text.isascii() else 'china-s',fontsize=12)
        if chinese is not None: page('摘要','本文提出一种论文检测方法，对文档结构进行建模与验证。',chinese)
        if english is not None: page('Abstract','This study describes a method for document analysis and review.',english)
        page('第1章 绪论','本文研究方法可以有效改进论文检测。', (body_keywords,) if body_keywords else ())
        doc.save(path)
    return _build_source_tree(path,include_citations=False)

def findings(ir): return detect_ir(ir,[36])['36']['findings']

@pytest.mark.parametrize('count',[2,3,8,9])
def test_english_limits_are_checked_separately(tmp_path,count):
    ir=paper(tmp_path,english=('Keywords: '+'; '.join('term '+str(i) for i in range(count)),))
    found=findings(ir)
    if 3<=count<=8: assert found==[]
    else:
        assert len(found)==1
        assert found[0]['message']==MESSAGE.format(count)
        assert found[0]['location']['page_number']==2

def test_both_lists_can_have_their_own_advisory(tmp_path):
    found=findings(paper(tmp_path,chinese=('关键词：软件；分析',),english=('Keywords: software; analysis',)))
    assert [f['message'] for f in found]==[MESSAGE.format(2),MESSAGE.format(2)]
    assert [f['location']['page_number'] for f in found]==[1,2]

@pytest.mark.parametrize('label',['Keywords:','Key words:','KEY WORDS:','Index terms—'])
def test_english_label_variants(tmp_path,label):
    found=findings(paper(tmp_path,english=(label+' machine learning; document analysis',)))
    assert len(found)==1 and found[0]['message']==MESSAGE.format(2)

def test_wrapped_english_final_period_is_included(tmp_path):
    assert findings(paper(tmp_path,english=('Keywords: machine learning; document analysis;', 'academic review.')))==[]

def test_label_on_its_own_line_is_not_counted_as_a_term(tmp_path):
    found=findings(paper(tmp_path,english=('Keywords', 'machine learning; document analysis')))
    assert len(found)==1 and found[0]['message']==MESSAGE.format(2)

def test_english_only_paper_is_supported(tmp_path):
    found=findings(paper(tmp_path,chinese=None,english=('Keywords: machine learning; document analysis',)))
    assert len(found)==1 and found[0]['location']['page_number']==1

def test_body_keyword_mentions_are_excluded(tmp_path):
    assert findings(paper(tmp_path,body_keywords='Keywords: two; terms'))==[]

def test_multiword_english_terms_are_not_split_on_spaces(tmp_path):
    found=findings(paper(tmp_path,english=('Keywords: large language model; natural language processing',)))
    assert len(found)==1 and found[0]['message']==MESSAGE.format(2)


def test_keyword_level_prose_is_not_a_keyword_label(tmp_path):
    from paper_compiler.local_checks import _keyword_terms
    assert _keyword_terms('It introduces a benchmark with domain instructions and\nkeyword-level annotations, prompting, decoding, evaluation.') is None
    ir=paper(tmp_path,english=('keyword-level annotations, prompting, decoding, evaluation,',
                              'robustness, alignment, performance, accuracy, precision.',
                              'Keywords: machine learning; document analysis; review'))
    assert findings(ir)==[]


def test_english_label_in_merged_abstract_keeps_final_continuation(tmp_path):
    from paper_compiler.local_checks import _keyword_block, _keyword_terms
    ir=paper(tmp_path,english=('Keywords: machine learning; document analysis;', 'academic review.'))
    node=next(n for n in ir['nodes'] if (n['text'] or '').startswith('Keywords:'))
    node['text']='This abstract explains the study.\n'+node['text']
    assert len(_keyword_terms(_keyword_block(ir,node)['text']))==3


@pytest.mark.parametrize('label',['Keywords -','Key words -','Index terms -','Keywords-'])
def test_dash_heading_with_a_list_on_the_next_line(tmp_path,label):
    assert findings(paper(tmp_path,english=(label, 'machine learning; document analysis; review')))==[]


@pytest.mark.parametrize('chinese_count,english_count',[(3,2),(2,3),(2,2),(3,3),(0,3),(0,2),(3,0),(0,0)])
def test_both_languages_in_one_native_paragraph_are_counted_separately(tmp_path,chinese_count,english_count):
    zh='关键词：'+'；'.join(['软件','分析','检测'][:chinese_count])
    en='Keywords: '+'; '.join(['software','analysis','review'][:english_count])
    ir=paper(tmp_path,chinese=None,english=(zh,en),continuation_x=60)
    assert any(zh in (n['text'] or '') and en in (n['text'] or '') for n in ir['nodes'])
    found=findings(ir)
    assert [f['message'] for f in found]==[MESSAGE.format(n) for n in [chinese_count,english_count] if n<3]
