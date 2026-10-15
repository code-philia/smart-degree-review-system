from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

def test_native_matrix_image_keeps_the_equation_identity():
 objects=[LayoutObject('text',1,(90,300,510,440),r'E_m=\left(\begin{array}{ccc} x&0&y \\0&x&0\end{array}\right)',600,840,'interline_equation')]
 page=PdfPage(1,600,840,(),images=((89,299,512,441),))
 doc=PdfDocument(Path('matrix.pdf'),(page,))
 assert detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']==[]

def test_an_equation_inside_a_diagram_does_not_exempt_the_whole_diagram():
 objects=[LayoutObject('text',1,(200,330,310,360),'x=y+z',600,840,'interline_equation'),LayoutObject('figure',1,(90,300,510,440),'',600,840,'image_body')]
 doc=PdfDocument(Path('matrix.pdf'),(PdfPage(1,600,840,()),))
 assert len(detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings'])==1

def test_titled_console_log_is_a_listing_even_without_executable_statements():
 body=(80,100,520,210)
 texts=['result: {"message": "ok"}', '[output]: {"state": "ready"}', '============================', '[finished] final report follows:', '============================']
 lines=tuple(PdfLine(1,t,(85,105+i*18,500,118+i*18),600,840) for i,t in enumerate(texts))+(PdfLine(1,'Listing 2.4 Runtime transcript',(170,220,470,235),600,840),)
 doc=PdfDocument(Path('transcript.pdf'),(PdfPage(1,600,840,lines),))
 assert detect_caption_rules(prepare_caption_layout([LayoutObject('figure',1,body,'',600,840,'image_body')],doc),[13],doc)['13']['findings']==[]


def committee_document():
    form=PdfPage(1,600,840,(PdfLine(1,'答辩日期 论文题目 答辩结论 答辩委员会工作职务 姓名',(60,80,540,700),600,840,source='mineru',role='table_body'),))
    text='答辩委员会工作职务 姓名 职称 工作单位 签名 主席 委员 委员 秘书'
    table=PdfLine(2,text,(60,80,540,250),600,840,source='mineru',role='table_body')
    page=PdfPage(2,600,840,(table,),unreadable=True,images=((0,0,600,840),),ink_bottom=650)
    return PdfDocument(Path('committee.pdf'),(form,page)),text


def test_three_member_committee_signature_table_has_no_academic_title_requirement():
    from pdf_rules.signature_ocr import signature_regions
    doc,text=committee_document()
    assert signature_regions(*doc.pages)==[(60,80,540,250)]
    objects=[LayoutObject('table',2,(60,80,540,250),text,600,840,'table_body')]
    result=detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    assert result['13']['findings']==[]
    assert result['14']['findings']==[]


def test_independent_research_figure_below_a_signature_form_is_retained():
    doc,text=committee_document()
    objects=[LayoutObject('table',2,(60,80,540,250),text,600,840,'table_body'),
             LayoutObject('figure',2,(100,500,300,610),'',600,840,'image_body')]
    result=detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    assert len(result['13']['findings'])==1
    assert result['13']['findings'][0]['location']['bounding_rect']['y1']==500
    assert result['14']['findings']==[]


def test_a_signature_shaped_research_table_without_verified_preceding_form_remains():
    from dataclasses import replace
    doc,text=committee_document()
    first=replace(doc.pages[0],lines=(PdfLine(1,'第一章 实验结果',(60,80,540,100),600,840),))
    doc=PdfDocument(doc.path,(first,doc.pages[1]))
    objects=[LayoutObject('table',2,(60,80,540,250),text,600,840,'table_body')]
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']


def prompt_with_separate_header():
    frame=(80,90,520,440);body=(80,115,520,435)
    texts=['You are an investigator. Your subordinate can query logs.',
           'Core Task: Investigate the proposed nodes and related activity.',
           'Judging Criteria: Ensure correct identifiers and event order.',
           'Please follow the stated workflow and exclude known events.']
    lines=(PdfLine(1,'系统提示词',(90,95,310,110),600,840),)+tuple(
        PdfLine(1,t,(90,130+i*65,510,145+i*65),600,840) for i,t in enumerate(texts))
    doc=PdfDocument(Path('prompt.pdf'),(PdfPage(1,600,840,lines,graphics=(frame,)),))
    return doc,[LayoutObject('table',1,body,' '.join(texts),600,840,'table_body')]


def test_prompt_header_may_be_outside_the_parser_body_but_inside_the_same_frame():
    doc,objects=prompt_with_separate_header()
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']==[]


def test_separate_prompt_heading_cannot_exempt_an_independent_titled_research_table():
    from dataclasses import replace
    doc,objects=prompt_with_separate_header()
    caption=PdfLine(1,'表2.1 提示词评估',(170,65,430,80),600,840)
    doc=replace(doc,pages=(replace(doc.pages[0],lines=(caption,)+doc.pages[0].lines),))
    targets=[o for o in prepare_caption_layout(objects,doc) if o.kind=='table']
    assert targets


def test_nested_prompt_frame_uses_the_frame_that_owns_its_heading():
    from dataclasses import replace
    doc,objects=prompt_with_separate_header()
    page=replace(doc.pages[0],graphics=((80,90,520,440),(81,115,519,439)))
    doc=replace(doc,pages=(page,))
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']==[]


def test_wrapped_role_task_criteria_workflow_is_a_single_column_prompt():
    frame=(80,90,520,440)
    texts=['系统提示词','You are a threat investigator with access to event logs.',
           'Core Task: Investigate the suggested nodes and their relations.',
           'with other events.', 'Judging Criteria:',
           '1. Ensure identifiers match the supplied original nodes.',
           'and events.', '2. Prioritize relevant suspicious sequences.',
           '3. Exclude known events.', 'Workflow:',
           '1. Request the corresponding event logs.',
           '2. Analyze the returned evidence.', '3. Identify new events.']
    lines=tuple(PdfLine(1,t,(90,96+i*24,510 if len(t)>45 else 320,110+i*24),600,840) for i,t in enumerate(texts))
    doc=PdfDocument(Path('wrapped-prompt.pdf'),(PdfPage(1,600,840,lines,graphics=(frame,)),))
    objects=[LayoutObject('table',1,(80,115,520,440),' '.join(texts[1:]),600,840,'table_body')]
    assert detect_caption_rules(prepare_caption_layout(objects,doc),[14],doc)['14']['findings']==[]
