from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
try:
 from pdf_rules.page_policy import exclude_signature_pages,signature_page_reasons
except ModuleNotFoundError:
 def exclude_signature_pages(document,objects=()):return document,list(objects),{}
 def signature_page_reasons(document,objects=()):return {}
def l(n,text,y=80,role=''):
 return PdfLine(n,text,(60,y,540,y+18),600,800,role=role,font_size=12)
def form():
 return PdfPage(1,600,800,(l(1,'学位论文答辩决议书'),l(1,'姓名 学号 所在学科 指导教师 答辩日期 答辩地点 论文题目 评语和决议 答辩委员会 无记名投票 同意通过学位论文答辩 建议授予硕士学位',130,'table_body')))
def roster():
 return PdfPage(2,600,800,(l(2,'答辩委员会 工作职务 姓名 职称 工作单位 签名 主席 委员 委员 委员 秘书',80,'table_body'),l(2,'如图9.9所示，表8.8以及附录Z。',500)),unreadable=True,images=((0,0,600,800),),graphics=((10,10,100,100),))
@pytest.mark.parametrize('declaration',['学位论文原创性声明','学位论文使用授权声明'])
def test_standalone_signed_legal_page_is_excluded(declaration):
 p=PdfPage(5,600,800,(l(5,declaration),l(5,'本人郑重声明：本学位论文作者同意学校保留论文，供查阅借阅。本声明的法律责任由本人承担。作者签名：日期：',140),l(5,'图9.9',300)))
 d=PdfDocument(Path('original.pdf'),(p,));before=d
 out,objects,reasons=exclude_signature_pages(d,[LayoutObject('figure',5,(60,500,200,650),'',600,800)])
 assert reasons and out.pages[0].lines==() and objects==[] and not out.pages[0].unreadable
 assert d==before and out.path==d.path and out.pages[0].number==5

def test_complete_committee_continuation_excludes_all_content():
 d=PdfDocument(Path('original.pdf'),(form(),roster(),PdfPage(3,600,800,(l(3,'第六章 实验'),l(3,'如图9.9所示',130)))))
 out,objects,reasons=exclude_signature_pages(d,[LayoutObject('figure',2,(60,500,200,650),'',600,800),LayoutObject('figure',3,(60,500,200,650),'',600,800)])
 assert set(reasons)=={1,2};assert len(out.pages)==3
 assert out.pages[1].lines==() and not out.pages[1].unreadable and out.pages[1].images==()
 assert out.pages[2]==d.pages[2] and [o.page_number for o in objects]==[3]
@pytest.mark.parametrize('kind',['isolated_roster','research_chapter','sparse_secretary','generic_signature','title_in_prose'])
def test_research_or_unproved_page_is_preserved(kind):
 if kind=='isolated_roster':p=roster();pages=(p,)
 elif kind=='research_chapter':p=replace(roster(),lines=(l(2,'第六章 签名识别实验'),*roster().lines));pages=(form(),p)
 elif kind=='sparse_secretary':p=replace(roster(),lines=(l(2,'秘书 李同学 计算机学院'),));pages=(form(),p)
 elif kind=='generic_signature':p=replace(roster(),lines=(l(2,'图2.3 手写签名识别结果'),));pages=(p,)
 else:p=replace(roster(),lines=(l(2,'本章讨论学位论文原创性声明的签字问题。'),));pages=(p,)
 d=PdfDocument(Path('research.pdf'),pages);out,_,reasons=exclude_signature_pages(d)
 assert p.number not in reasons and out.pages[-1]==p

def test_all_six_engine_skips_signing_pages_but_keeps_research_reference(tmp_path):
 import pymupdf
 from unittest.mock import patch
 from pdf_rules.engine import detect
 path=tmp_path/'paper.pdf'
 with pymupdf.open() as pdf:
  for _ in range(3):pdf.new_page(width=600,height=800)
  pdf.save(path)
 third=PdfPage(3,600,800,(l(3,'第六章 实验'),l(3,'如图9.9所示，详见附录Z。',130)))
 document=PdfDocument(path,(form(),roster(),third))
 objects=[LayoutObject('figure',2,(60,500,200,650),'',600,800),LayoutObject('table',2,(60,500,200,650),'',600,800),LayoutObject('text',3,(60,130,540,148),'实验正文',600,800)]
 with patch('pdf_rules.engine.extract_pdf',return_value=document),patch('pdf_rules.engine.parse_layout',return_value=objects),patch('pdf_rules.engine._ocr_missing_pages',side_effect=AssertionError('excluded signing scan must not OCR')),patch('pdf_rules.signature_ocr.recover_signature_pages',side_effect=AssertionError('excluded signing scan must not OCR')):
  result=detect(path,[11,13,14,15,16,29],token='fixture')
 assert result['pages']==3
 assert {x['page'] for x in result['excluded_signature_pages']}=={1,2}
 assert all(rule['status']=='completed' for rule in result['rules'].values())
 assert [(x['page'],x['token']) for x in result['rules']['11']['findings']]==[(3,'9.9')]
 assert [(x['page'],x['token']) for x in result['rules']['29']['findings']]==[(3,'Z')]
 assert all(x['page']==3 for rule in result['rules'].values() for x in rule['findings'])

from c7_runtime_ownership import assert_runtime_ownership as _assert_c7_runtime
_assert_c7_runtime()
