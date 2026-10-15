"""Real inherited citations keep their ink span, type and identifier boundaries."""
from pathlib import Path
import pytest
from pdf_rules.numbering import FIGURE_REFERENCE,TABLE_REFERENCE
from pdf_rules.reference_groups import reference_matches
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules

@pytest.mark.parametrize('pattern,text,expected',[
 (FIGURE_REFERENCE,'See Figures 9.2and9.4 for comparison.',['9.2','9.4']),
 (FIGURE_REFERENCE,'见图9.2and9.4中的示例。',['9.2','9.4']),
 (TABLE_REFERENCE,'Results in Tables 9.2 and 9.4.',['9.2','9.4']),
 (TABLE_REFERENCE,'表格9.4至9.6以及9.1至9.3展示结果。',['9.4','9.5','9.6','9.1','9.2','9.3']),
 (FIGURE_REFERENCE,'图9.2以及图9.4展示了对比结果。',['9.2','9.4']),
])
def test_explicit_conjunction_inherits_only_citation_type(pattern,text,expected):
 assert [m.group('number') for m in reference_matches(pattern,text)]==expected

@pytest.mark.parametrize('text', ['图F2D是变量。','图9.2android9.4不是引用。','图9.2analysis4也不是。'])
def test_alphanumeric_identifiers_do_not_become_partial_citations(text):
 assert list(reference_matches(FIGURE_REFERENCE,text))==[]

def test_inherited_citation_retains_each_number_original_offsets():
 text='详见图9.2and9.4中的实验。'
 matches=list(reference_matches(FIGURE_REFERENCE,text))
 assert [(m.group('number'),text[m.start('number'):m.end('number')]) for m in matches]==[('9.2','9.2'),('9.4','9.4')]

def test_type_change_does_not_create_unmentioned_figure():
 text='见图9.2以及表9.4所示结果。'
 assert [m.group('number') for m in reference_matches(FIGURE_REFERENCE,text)]==['9.2']

def test_adjacent_measurement_is_not_inherited_citation():
 assert [m.group('number') for m in reference_matches(FIGURE_REFERENCE,'图9.2以及9.4秒耗时。')]==['9.2']

@pytest.mark.parametrize('kind,rule,prose,numbers',[
 ('图','15','不同方法的可视化见图9.2and9.4。',(2,4)),
 ('表','16','表格9.4至9.6以及9.1至9.3详尽呈现结果。',(1,2,3,4,5,6)),
])
def test_full_index_marks_each_explicitly_cited_object(kind,rule,prose,numbers):
 lines=[PdfLine(1,prose,(60,70,540,84),600,800,font_size=12)]
 lines += [PdfLine(1,f'{kind}9.{n} 独立实验结果',(180,180+n*60,420,191+n*60),600,800,font_size=10.5,bold=True) for n in numbers]
 doc=PdfDocument(Path('unseen-format.pdf'),(PdfPage(1,600,800,tuple(lines)),))
 assert detect_rules(build_index(doc),[11,15,16])[rule]['findings']==[]

def test_list_does_not_hide_independent_uncited_middle_figure():
 lines=[PdfLine(1,'实验对比见图9.2and9.4。',(60,70,540,84),600,800,font_size=12)]
 lines += [PdfLine(1,f'图9.{n} 独立结果',(180,180+n*60,420,191+n*60),600,800,font_size=10.5,bold=True) for n in (2,3,4)]
 doc=PdfDocument(Path('unseen-missing-reference.pdf'),(PdfPage(1,600,800,tuple(lines)),))
 result=detect_rules(build_index(doc),[11,15,16])
 assert [f['token'] for f in result['15']['findings']]==['9.3']

def test_duplicate_parse_is_suppressed_but_distinct_ink_occurrences_remain():
 text='见图9.2以及图9.4所示。另见图9.4。'
 matches=list(reference_matches(FIGURE_REFERENCE,text))
 assert [m.group('number') for m in matches]==['9.2','9.4','9.4']
 assert len({m.start('number') for m in matches})==3


@pytest.mark.parametrize('quantity',['米','克','厘米','毫米','牛顿','焦耳','千克','公斤',' kg',' N',' ms',' Hz',' cm',' MB',' Pa',' J',' W',' V',' mA'])
def test_conjoined_measurement_with_chinese_explanation_is_not_a_citation(quantity):
 text=f'实验使用了图9.2以及9.4{quantity}的负载。'
 assert [m.group('number') for m in reference_matches(FIGURE_REFERENCE,text)]==['9.2']

@pytest.mark.parametrize('include_uncited',[False,True])
def test_measurement_does_not_invent_missing_target_or_hide_uncited_real_figure(include_uncited):
 lines=[PdfLine(1,'实验使用了图9.2以及9.4 kg的负载。',(60,70,540,84),600,800,font_size=12),
        PdfLine(1,'图9.2 实验装置',(180,300,420,311),600,800,font_size=10.5,bold=True)]
 if include_uncited: lines.append(PdfLine(1,'图9.4 未引用的实验结果',(180,500,420,511),600,800,font_size=10.5,bold=True))
 doc=PdfDocument(Path('unseen-quantity.pdf'),(PdfPage(1,600,800,tuple(lines)),))
 result=detect_rules(build_index(doc),[11,15,16])
 assert result['11']['findings']==[]
 assert [f['token'] for f in result['15']['findings']]==(['9.4'] if include_uncited else [])


@pytest.mark.parametrize('kind,rule',[('图','15'),('表','16')])
@pytest.mark.parametrize('repeated_word',[False,True])
def test_caption_own_number_filter_keeps_later_reference_to_another_object(kind,rule,repeated_word):
 second=kind if repeated_word else ''
 lines=[PdfLine(1,f'见{kind}9.2。',(60,70,540,84),600,800,font_size=12),
        PdfLine(1,f'{kind}9.2 与{second}9.4 的对比结果',(180,300,420,311),600,800,font_size=10.5,bold=True),
        PdfLine(1,f'{kind}9.4 独立结果',(180,500,420,511),600,800,font_size=10.5,bold=True)]
 doc=PdfDocument(Path('unseen-other-object-in-title.pdf'),(PdfPage(1,600,800,tuple(lines)),))
 assert detect_rules(build_index(doc),[11,15,16])[rule]['findings']==[]


@pytest.mark.parametrize('quantity',['m的深度','s的耗时','N的载荷'])
def test_glued_single_letter_unit_does_not_become_numeric_subpanel(quantity):
 text=f'实验使用了图9.2以及9.4{quantity}。'
 assert [m.group('number') for m in reference_matches(FIGURE_REFERENCE,text)]==['9.2']

@pytest.mark.parametrize('panel',['a','b','m','s'])
def test_numeric_subpanel_with_explicit_citation_pointer_still_resolves_parent(panel):
 text=f'见图9.2以及9.4{panel}所示。'
 assert [m.group('number') for m in reference_matches(FIGURE_REFERENCE,text)]==['9.2','9.4']
