from pathlib import Path
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules


def fixture(restart=False, barrier=False, separate_title=False):
    boxes=[(80,338,270,424),(310,338,500,424),(195,469,385,555)]
    letters=['a','b','c'] if not restart else ['a','b','a']
    lines=[]
    for box,letter in zip(boxes,letters):
        centre=(box[0]+box[2])/2
        lines += [PdfLine(1,f'({letter}) 条件比较',(centre-30,box[1]-32,centre+30,box[1]-19),600,840),
                  PdfLine(1,f'({letter}) Condition comparison',(centre-50,box[1]-17,centre+50,box[1]-5),600,840)]
    if barrier:lines.append(PdfLine(1,'The following results concern a separate experiment.',(80,427,500,439),600,840))
    objects=[LayoutObject('table',1,b,'',600,840,'table_body') for b in boxes]
    objects.append(LayoutObject('table_caption',1,(195,285,385,300),'表4.4 不同条件下的性能比较',600,840))
    if separate_title:objects.append(LayoutObject('table_caption',1,(195,431,385,441),'表4.5 另一实验',600,840))
    return objects,PdfDocument(Path('translated-table-panels.pdf'),(PdfPage(1,600,840,tuple(lines)),))


def test_top_common_table_title_owns_translated_subtables_in_two_rows():
    objects,document=fixture()
    layout=prepare_caption_layout(objects,document)
    assert len([o for o in layout if o.kind=='table'])==1
    assert detect_caption_rules(layout,[14],document)['14']['findings']==[]


def test_restarted_panel_namespace_does_not_absorb_another_table():
    objects,document=fixture(restart=True)
    layout=prepare_caption_layout(objects,document)
    assert len([o for o in layout if o.kind=='table'])>=2


def test_body_paragraph_preserves_separate_lower_table():
    objects,document=fixture(barrier=True)
    layout=prepare_caption_layout(objects,document)
    assert len([o for o in layout if o.kind=='table'])>=2


def test_intervening_table_title_preserves_two_academic_objects():
    objects,document=fixture(separate_title=True)
    layout=prepare_caption_layout(objects,document)
    assert len([o for o in layout if o.kind=='table'])>=2
