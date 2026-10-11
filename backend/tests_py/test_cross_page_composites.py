from pathlib import Path
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument,PdfPage,PdfLine


def composite(tags=('a','b'),intervening=False):
    objects=[];pages=[]
    for i,tag in enumerate(tags):
        number=i+1
        box=(110,440,490,670) if i==0 else (110,100,490,660 if i<len(tags)-1 else 350)
        lines=[PdfLine(number,f'({tag}) Comparison curve', (210,box[3]+8,400,box[3]+22),600,840)]
        if intervening and i==0:lines.append(PdfLine(number,'A separate experiment follows here.',(90,720,520,735),600,840))
        pages.append(PdfPage(number,600,840,tuple(lines)))
        objects.append(LayoutObject('figure',number,box,'',600,840,'chart_body'))
    last=objects[-1]
    objects.append(LayoutObject('figure_caption',last.page_number,(140,382,470,399),'Figure 8.7 Comparison curves',600,840,'chart_caption'))
    return objects,PdfDocument(Path('cross-page.pdf'),tuple(pages))


def test_cross_page_panels_can_end_before_fixed_page_tail_threshold():
    objects,doc=composite()
    assert detect_caption_rules(objects,[13],doc)['13']['findings']==[]


def test_three_page_panel_chain_inherits_one_final_common_caption():
    objects,doc=composite(('a','b','c'))
    assert detect_caption_rules(objects,[13],doc)['13']['findings']==[]


def test_intervening_body_text_prevents_cross_page_panel_inheritance():
    objects,doc=composite(intervening=True)
    assert len(detect_caption_rules(objects,[13],doc)['13']['findings'])==1


def test_restarted_panel_letters_keep_independent_title_obligations():
    objects,doc=composite(('a','a'))
    assert len(detect_caption_rules(objects,[13],doc)['13']['findings'])==1


def test_missing_panel_sequence_does_not_borrow_a_next_page_title():
    objects,doc=composite(('a','c'))
    assert len(detect_caption_rules(objects,[13],doc)['13']['findings'])==1
