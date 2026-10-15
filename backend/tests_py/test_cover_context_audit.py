from pathlib import Path
import pytest
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.layout_context import nonresearch_page,prepare_caption_layout
from pdf_rules.mineru_layout import LayoutObject

def line(text,y,x1=80,x2=520):
 return PdfLine(1,text,(x1,y,x2,y+20),600,840)

def fields():
 return [line('姓名：某同学',570),line('学号：2026001',600),line('导师：某教授',630),line('学院：计算机',660)]

@pytest.mark.parametrize('title_y',[310,420,510])
def test_degree_cover_title_below_logo_still_excludes_logo(title_y):
 page=PdfPage(1,600,840,tuple([line('示例大学学位论文',title_y,190,410)]+fields()),images=((235,135,360,263),))
 assert nonresearch_page(page)
 layout=prepare_caption_layout([LayoutObject('figure',1,(235,135,360,263),'',600,840,'image_body')],PdfDocument(Path('independent-cover.pdf'),(page,)))
 assert not any(o.kind=='figure' for o in layout)

def test_research_header_and_identity_variables_are_not_a_degree_cover():
 page=PdfPage(1,600,840,tuple([line('示例大学学位论文',15),line('我们评估姓名、学号、学院字段的关联质量。',160)]+fields()),images=((100,220,500,450),))
 assert not nonresearch_page(page)

def test_actual_caption_on_degree_cover_style_research_page_is_preserved():
 page=PdfPage(1,600,840,tuple([line('示例大学学位论文',310)]+fields()+[line('图2.1 数据字段的关系',480)]),images=((100,200,500,450),))
 assert not nonresearch_page(page)


@pytest.mark.parametrize('degree',['硕士','博士'])
def test_specific_degree_cover_heading_below_logo(degree):
 page=PdfPage(1,600,840,tuple([line('示例大学'+degree+'学位论文',355,190,410)]+fields()))
 assert nonresearch_page(page)


@pytest.mark.parametrize('degree',['专业','专业学位硕士','专业学位博士'])
def test_professional_degree_cover_heading_below_logo(degree):
 page=PdfPage(1,600,840,tuple([line('独立示例大学'+degree+'学位论文',355,160,440)]+fields()),images=((235,135,360,263),))
 assert nonresearch_page(page)
 layout=prepare_caption_layout([LayoutObject('figure',1,(235,135,360,263),'',600,840,'image_body')],PdfDocument(Path('professional-cover.pdf'),(page,)))
 assert not any(o.kind=='figure' for o in layout)
