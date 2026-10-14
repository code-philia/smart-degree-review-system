from pathlib import Path
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.caption_context import contextual_caption


def line(text,y,page=1,font=None,bold=False):
    return PdfLine(page,text,(85,y,520,y+12),600,840,font_size=font,bold=bold)


def run(lines):
    doc=PdfDocument(Path('scope.pdf'),tuple(PdfPage(n,600,840,tuple(l for l in lines if l.page_number==n)) for n in range(1,max(l.page_number for l in lines)+1)))
    return detect_rules(build_index(doc),[11,15,16])


def test_appendix_can_cite_existing_chapter_numbered_body_figure():
    ls=[line('图4.1 系统界面',200),line('附录A 完整页面示例',100,2),line('图A.1 完整案例截图，见图4.1',300,2)]
    assert run(ls)['11']['findings']==[]
    assert [x['token'] for x in run(ls)['15']['findings']]==['A.1']


def test_explicit_appendix_qualifier_cannot_fall_back_to_body():
    ls=[line('图4.1 系统界面',200),line('附录A 完整页面示例',100,2),line('详见附录A中的图4.1。',300,2)]
    assert len(run(ls)['11']['findings'])==1


def test_unqualified_local_appendix_target_takes_precedence():
    ls=[line('图4.1 正文界面',200),line('附录A 完整页面示例',100,2),line('图4.1 附录界面',200,2),line('如图4.1所示。',300,2)]
    assert [x['page'] for x in run(ls)['15']['findings']]==[1]


def test_provides_predicate_is_prose_despite_prompt_font_noise():
    body=line('图B.3提供了评估生成答案正确性的指令，通过将其与标准答案',660,font=12)
    prompt=[line('An evaluator should compare the generated answer and truth.',y,font=10.5) for y in (200,220,240)]
    page=PdfPage(1,600,840,tuple(prompt+[body,line('列表进行对比判断答案是否正确。',680,font=12)]))
    assert contextual_caption(body,page,'figure') is None


def test_nominal_providing_title_is_preserved():
    title=line('图B.3 提供评估数据的提示词',300,font=10.5,bold=True)
    assert contextual_caption(title,PdfPage(1,600,840,(title,)),'figure')


def test_appendix_entry_in_directory_cannot_change_body_scope():
 ls=[line('附录B 提示词........................60',100),line('图4.1 系统界面',200,2),line('附录A 完整页面示例',100,3),line('完整示例参见图4.1。',300,3)]
 doc=PdfDocument(Path('toc.pdf'),tuple(PdfPage(n,600,840,tuple(l for l in ls if l.page_number==n)) for n in (1,2,3)))
 index=build_index(doc)
 assert index.figures[0].scope=='body'
 assert detect_rules(index,[11])['11']['findings']==[]


def test_inflected_reporting_predicate_in_body_font_is_not_a_title():
 prose=line('本文对算法的生成内容开展实验并分析各类指标表现。',500,font=12)
 subject=line('表5.9统计了代表性词汇的频率。',450,font=12)
 page=PdfPage(1,600,840,(prose,subject))
 assert contextual_caption(subject,page,'table') is None


def test_inflected_predicate_in_compact_caption_typography_is_preserved():
 prose=line('本文对算法的生成内容开展实验并分析各类指标表现。',500,font=12)
 title=PdfLine(1,'表5.9 完成了评估的模型对比',(160,300,440,312),600,840,font_size=10.5,bold=True)
 assert contextual_caption(title,PdfPage(1,600,840,(prose,title)),'table')


def test_cited_source_appendix_is_not_a_missing_local_appendix():
    ls=[line('参见 Atlas[17] 附录B.2中的引理4。',200)]
    doc=PdfDocument(Path('external.pdf'),(PdfPage(1,600,840,tuple(ls)),))
    assert detect_rules(build_index(doc),[29])['29']['findings']==[]


def test_reference_source_appendix_does_not_hide_later_local_appendix():
    ls=[line('参见文献[17] 附录B.2中的引理4，另见本文附录Z。',200)]
    doc=PdfDocument(Path('external.pdf'),(PdfPage(1,600,840,tuple(ls)),))
    assert [f['token'] for f in detect_rules(build_index(doc),[29])['29']['findings']]==['Z']


def test_separate_author_citation_does_not_qualify_local_appendix():
    ls=[line('Atlas[17]研究了该方法，完整推导见附录Z。',200)]
    doc=PdfDocument(Path('local.pdf'),(PdfPage(1,600,840,tuple(ls)),))
    assert [f['token'] for f in detect_rules(build_index(doc),[29])['29']['findings']]==['Z']
