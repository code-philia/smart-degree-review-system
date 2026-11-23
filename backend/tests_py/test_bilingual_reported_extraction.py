import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from scripts.paper_model_bilingual_rules import extract_bilingual_facts
from scripts.run_bilingual_semantic_lint import prompt_for

def page(index, rows):
    return {'page_index':index,'width':600,'height':840,'lines':[
        {'id':f'{index}-{i}','text':t,'bbox':b,'font_size':b[3]-b[1]}
        for i,(t,b) in enumerate(rows)]}

def facts(*pages):
    return extract_bilingual_facts({'nodes':[],'layout':{'pages':list(pages)}})

def test_and_inside_a_keyword_is_not_a_list_delimiter():
    f=facts(page(0,[('Keywords: Cross-Lingual and Cross-Platform Alignment; Multi-source and Multi-modal Data',[80,300,550,312])]))
    assert f['english_keywords']['values']==['Cross-Lingual and Cross-Platform Alignment','Multi-source and Multi-modal Data']

@pytest.mark.parametrize('last,continued,expected',[
    ('Large Language Model, Intel AMX,','Performance Prediction',['Large Language Model','Intel AMX','Performance Prediction']),
    ('Missing Modality,','Contrastive Learning, Diffusion Model',['Missing Modality','Contrastive Learning','Diffusion Model']),
    ('Floating-Point Arithmetic; Exponentiation','Protocol; Reciprocal Protocol; Transformer',['Floating-Point Arithmetic','Exponentiation Protocol','Reciprocal Protocol','Transformer']),
])
def test_complete_words_continue_on_adjacent_keyword_page(last,continued,expected):
    f=facts(page(0,[('University thesis',[80,40,400,52]),('Abstract',[250,120,350,144]),
                    ('We evaluate a method.',[80,180,500,192]),('Keywords: '+last,[80,730,550,742]),('II',[290,780,310,792])]),
            page(1,[('University thesis',[80,40,400,52]),(continued,[80,120,550,132]),('III',[290,780,310,792])]))
    assert f['english_keywords']['values']==expected

def test_keywords_do_not_continue_into_unrelated_sentences():
    f=facts(page(0,[('Keywords: Graph Learning,',[80,730,500,742])]),
            page(1,[('This chapter introduces the method.',[80,120,500,132])]))
    assert f['english_keywords']['values']==['Graph Learning']

def test_keyword_continuation_skips_mirrored_odd_even_running_headers():
    f=facts(page(0,[('Abstract',[490,70,525,82]),('Abstract',[250,120,350,144]),
                    ('We evaluate a method.',[80,180,500,192]),
                    ('Keywords: CPU,',[80,730,550,742]),('III',[290,780,310,792])]),
            page(1,[('Abstract',[75,70,110,82]),('Performance Prediction',[75,120,500,132]),('IV',[290,780,310,792])]))
    assert f['english_keywords']['values']==['CPU','Performance Prediction']

@pytest.mark.parametrize('title',['1 Introduction','Introduction','绪论'])
def test_pending_keyword_does_not_consume_a_full_size_next_page_title(title):
    f=facts(page(0,[('Keywords: CPU,',[80,730,500,742])]),
            page(1,[(title,[80,120,350,144]),('This is the body.',[80,180,500,192])]))
    assert f['english_keywords']['values']==['CPU']

def test_abstract_continuation_ignores_mirrored_chapter_running_rows():
    f=facts(page(0,[('Chapter 1',[490,50,560,62]),('Abstract',[250,120,350,144]),
                    ('We propose a retrieval method.',[80,180,500,192])]),
            page(1,[('Chapter 1',[40,50,110,62]),('MRR improves by 18.8 percent.',[80,120,500,132]),
                    ('Keywords: Retrieval; Ranking',[80,180,500,192])]))
    assert 'MRR improves by 18.8 percent.' in f['english_abstract']

def test_keywords_do_not_cross_a_blank_or_new_title_page():
    f=facts(page(0,[('Keywords: Graph Learning,',[80,730,500,742])]),page(1,[]),
            page(2,[('Diffusion Model',[80,120,500,132])]))
    assert f['english_keywords']['values']==['Graph Learning']
    f=facts(page(0,[('Keywords: Graph Learning,',[80,730,500,742])]),
            page(1,[('Abstract',[250,120,350,144]),('Diffusion Model',[80,180,500,192])]))
    assert f['english_keywords']['values']==['Graph Learning']

def test_repeated_chapter_header_does_not_end_abstract():
    f=facts(page(0,[('Chapter 1',[420,50,500,62]),('Abstract',[250,120,350,144]),
                    ('We propose a retrieval method.',[80,180,500,192])]),
            page(1,[('Chapter 1',[420,50,500,62]),('MRR improves by 18.8 percent.',[80,120,500,132]),
                    ('Keywords: Retrieval; Ranking',[80,180,500,192])]))
    assert 'MRR improves by 18.8 percent.' in f['english_abstract']
    assert 'Chapter 1' not in f['english_abstract']

def test_actual_new_chapter_still_ends_unclosed_abstract():
    f=facts(page(0,[('Abstract',[250,120,350,144]),('We propose a retrieval method.',[80,180,500,192])]),
            page(1,[('Chapter 1 Introduction',[180,120,500,144]),('This is body text.',[80,180,500,192])]))
    assert f['english_abstract']=='We propose a retrieval method.'

@pytest.mark.parametrize('first,second,expected',[
    ('cross-','window attention mechanism','cross-window attention mechanism'),
    ('processing-','in-memory','processing-in-memory'),
])
def test_semantic_prompt_keeps_the_actual_hyphenated_keyword(first,second,expected):
    f=facts(page(0,[('关键词：模型',[80,200,500,212]),('Keywords: '+first,[80,300,550,312]),(second,[80,324,550,336])]))
    prompt=prompt_for('bilingual_keywords_correspondence_check',f)
    assert expected in prompt
    assert json.dumps(f['english_keywords']['values'],ensure_ascii=False) in prompt
