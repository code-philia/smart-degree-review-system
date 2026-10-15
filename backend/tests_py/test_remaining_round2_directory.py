from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.numbering import toc_line_keys

def line(text,x,y,width=180,page=1):
    return PdfLine(page,text,(x,y,x+width,y+12),600,800,font_size=12,
                   text_regions=((0,len(text),(x,y,x+width,y+12)),))

def document(kind='图',wrapped=False):
    rows=[]
    for i,y in enumerate((130,190,250),1):
        rows.append(line(f'{kind}7-{i} 测试目录中的完整项目标题',70,y,340))
        if wrapped:rows.append(line('标题续行',60,y+18,100))
        dy=y+18 if wrapped else y
        rows.extend([line('············',420,dy,55),line(str(i+20),520,dy,20)])
    # A real body title on this same page is deliberately retained.
    rows.append(line(f'{kind}8-1 实验结果',180,450,240))
    doc=PdfDocument(Path('directory-continuation.pdf'),(PdfPage(1,600,800,tuple(rows)),))
    return doc

@pytest.mark.parametrize('kind,rule',[('图',15),('表',16)])
@pytest.mark.parametrize('wrapped',[False,True])
def test_split_leaders_and_page_number_exclude_only_directory_entries(kind,rule,wrapped):
    doc=document(kind,wrapped)
    keys=toc_line_keys(doc)
    assert all((1,l.bbox) in keys for l in doc.lines if l.bbox[1]<300)
    assert (1,doc.lines[-1].bbox) not in keys
    findings=detect_rules(build_index(doc),[rule])[str(rule)]['findings']
    assert [(f['page'],f['token']) for f in findings]==[(1,'8.1')]

def test_single_caption_with_nearby_numeric_ink_does_not_prove_directory():
    doc=document()
    doc=PdfDocument(doc.path,(PdfPage(1,600,800,doc.lines[:3]),))
    assert not toc_line_keys(doc)

def test_directory_entry_cannot_supply_body_reference():
    doc=document()
    body=line('图7-1 真实但未引用的正文图',180,450,240,page=2)
    doc=PdfDocument(doc.path,doc.pages+(PdfPage(2,600,800,(body,)),))
    findings=detect_rules(build_index(doc),[15])['15']['findings']
    assert (2,'7.1') in [(f['page'],f['token']) for f in findings]
