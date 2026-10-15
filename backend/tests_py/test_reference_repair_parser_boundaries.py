"""The repair stage must preserve the shared citation parser boundaries."""
from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.reference_identity_repair import repair_reference_identity
from pdf_rules.local_rules import detect_rules

def run(prose,figures=(),tables=()):
 lines=[PdfLine(1,prose,(60,100,540,114),600,900,font_size=12)]
 for kind,numbers in [('图',figures),('表',tables)]:
  for number in numbers:
   y=220+len(lines)*45
   lines.append(PdfLine(1,f'{kind}{number} 独立实验结果',(180,y,420,y+11),600,900,font_size=10.5,bold=True))
 doc=PdfDocument(Path('parser-boundary-control.pdf'),(PdfPage(1,600,900,tuple(lines)),))
 raw=build_index(doc);repaired=repair_reference_identity(raw)
 return raw,repaired,detect_rules(repaired,[11,15,16])

@pytest.mark.parametrize('text',[
 '单调上升关系。在混合结构图（0.4-0.6）上标准差增大。',
 '各样本覆盖摄影、绘画、AIGC 图 8 个维度。',
 '专家视图（1，2，3，4，3）转化成视图（1，2，3，4，2）。',
])
def test_existing_non_citation_context_does_not_reappear_in_repair(text):
 raw,repaired,result=run(text)
 assert not raw.figure_refs
 assert not repaired.figure_refs
 assert result['11']['findings']==[]

@pytest.mark.parametrize('text',[
 '混合结构图（0.4-0.6）上标准差增大，另见图9.2。',
 '摄影、绘画、AIGC 图 8 个维度；实验请见图9.2。',
 '专家视图（1，2，3，4，3）发生变化，随后见图9.2所示。',
])
def test_domain_noun_does_not_hide_a_later_real_missing_citation(text):
 _,_,result=run(text)
 assert [f['token'] for f in result['11']['findings']]==['9.2']

@pytest.mark.parametrize('text',[
 '图4.2-4.4所示。','如图（4.2 - 4.4）所示。',
 'As shown in Figures 4.2-4.4, the results agree.','图4 . 2 - 4 . 4所示。',
])
def test_repair_uses_complete_range_endpoints(text):
 _,index,result=run(text,figures=('4.2','4.3','4.4'))
 assert not result['11']['findings']
 assert not result['15']['findings']
 assert {r.number for r in index.figure_refs}=={'4.2','4.3','4.4'}

@pytest.mark.parametrize('text',['图4.2-4.4所示。','如图（4.2 - 4.4）所示。'])
def test_real_missing_middle_range_member_still_alarms(text):
 _,_,result=run(text,figures=('4.2','4.4'))
 assert [f['token'] for f in result['11']['findings']]==['4.3']

@pytest.mark.parametrize('text',[
 '如图3.6, 3.7 和表3.11, 3.12 所示。',
 'See Figures 3.6, 3.7 and Tables 3.11, 3.12 for results.',
])
def test_mixed_figure_table_lists_do_not_inherit_across_type_word(text):
 _,index,result=run(text,figures=('3.6','3.7','3.11','3.12'),tables=('3.11','3.12'))
 assert {r.number for r in index.figure_refs}=={'3.6','3.7'}
 assert {r.number for r in index.table_refs}=={'3.11','3.12'}
 assert sorted(f['token'] for f in result['15']['findings'])==['3.11','3.12']
 assert not result['16']['findings']
 assert not result['11']['findings']

@pytest.mark.parametrize('text',[
 '如表3.6, 3.7 和图3.11, 3.12 所示。',
 'See Tables 3.6, 3.7 and Figures 3.11, 3.12 for results.',
])
def test_inverse_mixed_list_preserves_uncited_table_controls(text):
 _,index,result=run(text,figures=('3.11','3.12'),tables=('3.6','3.7','3.11','3.12'))
 assert {r.number for r in index.table_refs}=={'3.6','3.7'}
 assert sorted(f['token'] for f in result['16']['findings'])==['3.11','3.12']
 assert not result['15']['findings']
 assert not result['11']['findings']

@pytest.mark.parametrize('text,expected',[
 ('如结构图（0.4）所示。','0.4'),('图8展示了各个维度。','8'),
 ('专家视图发生变化，图1所示流程仍适用。','1'),
])
def test_real_graphical_citation_is_preserved_without_a_target(text,expected):
 _,_,result=run(text)
 assert [f['token'] for f in result['11']['findings']]==[expected]

@pytest.mark.parametrize('text',['如表7.2 7.3所示。','如表7 . 2、7 . 3所示。'])
def test_repair_retains_ocr_spaced_complete_table_identifiers(text):
 _,_,result=run(text,tables=('7.2','7.3'))
 assert not result['16']['findings']

@pytest.mark.parametrize('text',['如表7.2 7.3 7.4结果所示。','如表7 . 2 7 . 3 7 . 4结果所示。'])
def test_shared_complete_list_retains_result_predicate(text):
 _,_,result=run(text,tables=('7.2','7.3','7.4'))
 assert result['16']['findings']==[]

def test_numeric_result_list_does_not_inherit_across_percent_measurement():
 _,_,result=run('如表7.2 7.3 7.4%的样本更稳定。',tables=('7.2','7.3','7.4'))
 assert sorted(f['token'] for f in result['16']['findings'])==['7.3','7.4']
