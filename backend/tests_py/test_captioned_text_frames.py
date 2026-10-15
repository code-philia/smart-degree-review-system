from pathlib import Path
import pymupdf
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.container_ownership import recover_ruled_table_containers
from pdf_rules.caption_rules import detect_caption_rules


def fixture(tmp_path, footer=True, fragmented=True, original_rules=True, internal=False, outside=False, chart=False, mismatched=False):
    path=tmp_path/'declared-text-table.pdf'
    pdf=pymupdf.open();raw=pdf.new_page(width=600,height=840)
    if original_rules:
        raw.draw_line((85,130),(515,130))
        raw.draw_line((85 if not mismatched else 135,420),(515,420))
    pdf.save(path);pdf.close()
    boxes=[(90,135,510,250),(90,260,510,415)] if fragmented else [(90,135,510,415)]
    bodies=[LayoutObject('figure',1,b,'',600,840,'image_body') for b in boxes]
    texts=['Query: [query]','User History: [user_history]',
           'Determine whether the requested parameter is supported.',
           'Return your reasoning and the structured JSON result.']
    if chart:texts=['0','10','20','30','Accuracy','Time']
    lines=[PdfLine(1,t,(95,150+i*30,500,164+i*30),600,840) for i,t in enumerate(texts)]
    cap=LayoutObject('table_caption',1,(160,430,440,444) if footer else (160,107,440,121),
                     'Table A.9 Interaction example',600,840,'table_caption')
    objects=bodies+[cap]
    if internal:objects.append(LayoutObject('figure_caption',1,(180,252,420,265),'Figure 2.8 Independent illustration',600,840))
    if outside:objects.append(LayoutObject('figure',1,(90,520,510,630),'',600,840,'image_body'))
    doc=PdfDocument(path,(PdfPage(1,600,840,tuple(lines)),))
    return objects,doc


@pytest.mark.parametrize('footer,fragmented',[(True,True),(True,False),(False,True)])
def test_native_ruled_text_frame_inherits_its_explicit_table_title(tmp_path,footer,fragmented):
    objects,doc=fixture(tmp_path,footer,fragmented)
    recovered=recover_ruled_table_containers(objects,doc)
    assert len([o for o in recovered if o.kind=='table'])==1
    assert not [o for o in recovered if o.kind=='figure']
    assert detect_caption_rules(recovered,[13,14],doc)['13']['findings']==[]
    assert detect_caption_rules(recovered,[13,14],doc)['14']['findings']==[]


@pytest.mark.parametrize('kwargs',[
    {'original_rules':False}, {'internal':True}, {'chart':True}, {'mismatched':True}])
def test_title_or_inferred_envelope_alone_does_not_absorb_independent_objects(tmp_path,kwargs):
    objects,doc=fixture(tmp_path,**kwargs)
    recovered=recover_ruled_table_containers(objects,doc)
    assert len([o for o in recovered if o.kind=='figure'])==2


def test_unrelated_image_below_caption_retains_missing_figure_title_obligation(tmp_path):
    objects,doc=fixture(tmp_path,outside=True)
    recovered=recover_ruled_table_containers(objects,doc)
    assert len([o for o in recovered if o.kind=='table'])==1
    assert len([o for o in recovered if o.kind=='figure'])==1
    assert len(detect_caption_rules(recovered,[13],doc)['13']['findings'])==1


@pytest.mark.parametrize('original_rules',[True,False])
def test_overlong_table_body_stops_at_its_original_footer_title(tmp_path,original_rules):
    objects,doc=fixture(tmp_path,fragmented=False,original_rules=original_rules)
    path=tmp_path/'one-row-table.pdf'
    pdf=pymupdf.open();raw=pdf.new_page(width=600,height=840)
    if original_rules:
        raw.draw_line((85,130),(515,130));raw.draw_line((85,160),(515,160))
    pdf.save(path);pdf.close()
    body=LayoutObject('table',1,(85,130,515,640),'Example record',600,840,'table_body')
    cap=LayoutObject('table_caption',1,(160,170,440,184),'Table A.9 Interaction example',600,840,'table_caption')
    line=PdfLine(1,'Generate the requested dialogue state.',(95,140,490,154),600,840)
    doc=PdfDocument(path,(PdfPage(1,600,840,(line,)),))
    recovered=recover_ruled_table_containers([body,cap],doc)
    table=next(o for o in recovered if o.kind=='table')
    assert table.bbox[3]==(160 if original_rules else 640)
    if original_rules:assert detect_caption_rules(recovered,[14],doc)['14']['findings']==[]
