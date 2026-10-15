from dataclasses import replace
from pathlib import Path
from hashlib import sha256
import json
import pytest
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

CASES=json.loads((Path(__file__).parent/'fixtures/caption_native_geometry_followup_cases.json').read_text(encoding='utf-8'))
def tuples(value):
 if isinstance(value,list):return tuple(tuples(x) for x in value)
 if isinstance(value,dict):return {k:tuples(v) for k,v in value.items()}
 return value

def load(case):
 path=Path(case['path'])
 if not path.is_file():pytest.skip('Original immutable PDF is required')
 assert sha256(path.read_bytes()).hexdigest()==case['sha']
 pages=[]
 for v in case['pages']:
  kw=tuples(v);kw['lines']=tuple(PdfLine(**l) for l in kw['lines']);pages.append(PdfPage(**kw))
 return [LayoutObject(**tuples(o)) for o in case['objects']],PdfDocument(path,tuple(pages))
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['case'])
def test_original_numbered_formula_and_printed_captions_do_not_report_missing_titles(case):
 objects,doc=load(case)
 fixed=prepare_caption_layout(objects,doc)
 found=detect_caption_rules(fixed,[case['rule']],doc)[str(case['rule'])]['findings']
 assert not [f for f in found if f['page']==case['page']]

@pytest.mark.parametrize('case',[c for c in CASES if c['case']!='220-36'],ids=lambda c:c['case'])
def test_deleting_the_printed_total_titles_keeps_real_figure_or_table_obligations(case):
 objects,doc=load(case)
 objects=[o for o in objects if 'caption' not in o.kind]
 pages=tuple(replace(p,lines=tuple(l for l in p.lines if not l.text.lstrip().startswith(('图','表','Figure','Table')))) for p in doc.pages)
 doc=replace(doc,pages=pages)
 found=detect_caption_rules(prepare_caption_layout(objects,doc),[case['rule']],doc)[str(case['rule'])]['findings']
 assert [f for f in found if f['page']==case['page']]

def test_math_labels_without_an_independent_equation_number_keep_the_unknown_graphic():
 case=next(c for c in CASES if c['case']=='220-36');objects,doc=load(case)
 doc=replace(doc,pages=tuple(replace(p,lines=tuple(l for l in p.lines if l.text.strip()!='(3.13)')) for p in doc.pages))
 objects=[o for o in objects if '(3.13)' not in o.text]
 found=detect_caption_rules(prepare_caption_layout(objects,doc),[13],doc)['13']['findings']
 assert [f for f in found if f['page']==36]

@pytest.mark.parametrize('bold,visual,connected,expected',[(True,True,False,True),(False,True,False,False),(True,False,False,False),(True,True,True,False)])
def test_same_size_native_bold_title_requires_actual_visual_and_paragraph_separation(bold,visual,connected,expected):
 from pdf_rules.caption_context import contextual_caption
 title=PdfLine(1,'图 9.7 可见/在用卫星数量对比',(180,220,420,232),600,840,source='native',font_size=12,bold=bold,block_id=2)
 body=PdfLine(1,'后续正文讨论实验测量结果以及对应的统计特性，继续说明方法和实验条件。',(70,236 if connected else 270,530,248 if connected else 282),600,840,source='native',font_size=12,block_id=2 if connected else 3)
 page=PdfPage(1,600,840,(title,body),images=((150,100,450,210),) if visual else ())
 assert bool(contextual_caption(title,page,'figure'))==expected


@pytest.mark.parametrize('text',[
 '图 9.7 与图 9.8 给出了A/B实验结果',
 '图 9.7 显示了A/B实验结果',
 '图 9.7 为A/B系统提供了实验结果',
])
def test_slash_in_isolated_bold_body_reference_cannot_supply_a_title(text):
 from pdf_rules.caption_context import _isolated_native_bold_title
 line=PdfLine(1,text,(180,220,420,232),600,840,source='native',font_size=12,bold=True)
 body=PdfLine(1,'后续正文讨论实验测量结果以及对应的统计特性，继续说明方法和实验条件。',
              (70,270,530,282),600,840,source='native',font_size=12)
 page=PdfPage(1,600,840,(line,body),images=((150,100,450,210),))
 assert not _isolated_native_bold_title(line,page,'figure')
