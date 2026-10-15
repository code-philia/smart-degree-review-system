from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.caption_context import contextual_caption
from pdf_rules.text_fragments import merge_reference_fragments


def line(text, box=(60,100,540,112), **kw):
    return PdfLine(1,text,box,600,800,**kw)


def run(lines, **page_args):
    doc=PdfDocument(Path('unseen.pdf'),(PdfPage(1,600,800,tuple(lines),**page_args),))
    return detect_rules(build_index(doc),[11,15,16])


@pytest.mark.parametrize('text,word,rule',[
    ('详见图7.2—图7.5的实验结果。','图','15'),
    ('性能结果列于表7.2至表7.5。','表','16'),
    ('The results appear in Figures 7.2 to Figure 7.5.','Figure','15'),
])
def test_explicit_same_kind_range_resolves_interior_members(text,word,rule):
    ls=[line(text)]+[line(f'{word}7.{n} Experimental results',(170,250+n*40,430,261+n*40)) for n in (2,3,4,5)]
    assert run(ls)[rule]['findings']==[]


def test_range_with_missing_middle_still_reports_the_missing_figure():
    r=run([line('实验如图7.2至图7.4所示。'),line('图7.2 初始实验',(170,300,430,311)),line('图7.4 最后实验',(170,400,430,411))])
    assert [f['token'] for f in r['11']['findings']]==['7.3']


def test_mixed_kind_range_cannot_mark_intermediate_figures_referenced():
    r=run([line('比较图7.2与表7.4所示的数据。'),line('图7.2 初始实验',(170,300,430,311)),line('图7.3 未引用实验',(170,400,430,411)),line('表7.4 性能指标',(170,500,430,511))])
    assert [f['token'] for f in r['15']['findings']]==['7.3']


def test_short_punctuation_tail_completes_wrapped_reference():
    ls=merge_reference_fragments([line('这些算法可分成以下几类，详见表7-',(60,100,540,112)),line('2：',(60,120,81,132))])
    r=run([*ls,line('表7-2 算法分类',(170,300,430,311))])
    assert r['16']['findings']==[]
    assert r['11']['findings']==[]


@pytest.mark.parametrize('text,word,rule',[
    ('图7.2所展示的算法能够实现跨设备的数据对齐，并且保证结果一致。','图','15'),
    ('表7.2对不同任务上的多个性能指标以及平均输入长度和输出长度','表','16'),
    ('图7.2、图7.3和图7.4所示，在其他条件下则可进一步观察。','图','15'),
])
def test_flush_left_body_continuation_counts_as_reference(text,word,rule):
    ls=[line('前一行正文介绍实验条件和指标定义，以及模型在不同任务下的表现。',(60,100,540,112),font_size=12),
        line(text,(60,120,540,133),font_size=12),
        line('进行了统计，可以看到不同配置下的结果存在稳定的一致性。',(60,140,540,152),font_size=12),
        line(f'{word}7.2 实验结果',(180,300,420,311),font_size=10.5,bold=True)]
    assert run(ls)[rule]['findings']==[]


def test_wide_caption_beside_visual_is_not_reclassified_as_body_continuation():
    ls=[line('上方正文解释实验中需要记录的参数和性能指标定义。',(60,100,540,112),font_size=12),
        line('表7.2 不同采样条件与各组基线的实验数据及统计误差',(60,136,540,148),font_size=12)]
    r=run(ls,tables=((60,158,540,280),))
    assert [f['token'] for f in r['16']['findings']]==['7.2']


def test_smaller_bold_caption_keeps_identity_without_detected_table_body():
    body=line('上一段正文解释仿真实验中的各个参数及最终评估方法。',(60,280,540,292),font_size=12)
    caption=line('表7.2 不同操作的实验成功率。数据格式：训练类别与未见类别。',(80,310,527,321.4),font_size=10.5,bold=True)
    page=PdfPage(1,600,800,(body,caption))
    assert contextual_caption(caption,page,'table') is not None
    assert [f['token'] for f in run([body,caption])['16']['findings']]==['7.2']


def test_elliptic_coordinated_subject_is_prose_on_graphics_only_page():
    ls=[line('图7.2 不同实验方法对数据的结果对比及综合性能可视化',(80,300,520,312),font_size=10.5,bold=True),
        line('图7.3 不同实验方法对数据的结果对比及综合性能可视化',(80,500,520,512),font_size=10.5,bold=True),
        line('图7.2 和7.3 展示了所有实验方法在不同任务上的结果',(84,720,540,733),font_size=12)]
    assert run(ls,images=((80,160,520,280),(80,360,520,480)))['15']['findings']==[]


def test_function_predicate_is_reference_even_without_other_body_text():
    ls=[line('表7.2 不同方案适用条件',(180,300,420,311),font_size=10.5,bold=True),
        line('表7.2 用于说明不同方案在精度与资源需求方面的适用差异。',(84,720,540,733),font_size=12)]
    assert run(ls)['16']['findings']==[]


def test_directory_range_is_not_body_reference():
    ls=[line('图7.2至图7.4 实验数据................... 18'),line('图7.3 中间一组实验',(180,300,420,311))]
    assert [f['token'] for f in run(ls)['15']['findings']]==['7.3']


def test_purpose_noun_caption_keeps_identity_with_typographic_support():
    ls=[line('这段正文介绍模型验证所采用的基本方法与测量指标。',(60,100,540,112),font_size=12),
        line('图7.2 用于模型验证的实验装置',(180,300,420,310.5),font_size=10.5,bold=True)]
    assert [f['token'] for f in run(ls,images=((80,140,520,280),))['15']['findings']]==['7.2']


def test_body_continuation_after_indented_first_line_counts_as_reference():
    ls=[line('除了方法的准确率，推理效率也是部署中需要关注的因素。',(84,100,540,112),font_size=12),
        line('表7.2 对不同任务的平均输入长度与输出长度以及多个指标',(60,120,540,135),font_size=12),
        line('进行了统计，较大模型的推理耗时通常会随规模增加。',(60,140,540,155),font_size=12),
        line('表7.2 效率对比',(180,300,420,311),font_size=10.5,bold=True)]
    assert run(ls)['16']['findings']==[]



def test_enumeration_comma_keeps_coordinated_subject_on_graphics_only_page():
    ls=[line('图7.2 不同算法下的实验结果',(180,300,420,311),font_size=10.5,bold=True),
        line('图7.3 不同数据下的实验结果',(180,500,420,511),font_size=10.5,bold=True),
        line('图7.2、7.3 展示了各个模型的结果',(84,720,530,733),font_size=12)]
    assert run(ls)['15']['findings']==[]


@pytest.mark.parametrize('separator',['、',':','：'])
def test_caption_separator_before_noun_title_is_still_a_caption(separator):
    assert [f['token'] for f in run([line(f'图7.2{separator}实验方法比较',(180,300,420,311))])['15']['findings']]==['7.2']



@pytest.mark.parametrize('title',['图7.2 用于模型验证的实验装置','图7.2 用于模型验证的实验装置。'])
def test_purpose_noun_caption_on_graphics_only_page_stays_unreferenced(title):
    r=run([line(title,(160,400,440,411),font_size=10.5,bold=True)],images=((80,100,520,380),))
    assert [f['token'] for f in r['15']['findings']]==['7.2']
    assert r['11']['findings']==[]


def test_purpose_body_reference_to_missing_figure_is_not_invented_as_caption():
    ls=[line('正文说明实验条件与流程，各个步骤的相关设置如下。',(60,100,540,112),font_size=12),
        line('图7.2 用于说明模型验证的完整流程和多项性能指标。',(60,120,540,132),font_size=12)]
    r=run(ls)
    assert [f['token'] for f in r['11']['findings']]==['7.2']
    assert r['15']['findings']==[]



@pytest.mark.parametrize('prefix',['如','见'])
def test_explicit_citation_wrap_near_table_keeps_body_reference(prefix):
    ls=[line(f'模型性能的差异在以下实验结果中也有明显体现{prefix}',(60,100,540,112),font_size=12),
        line('表7.2：当移除该组件时，模型性能出现了明显下降。',(60,120,540,132),font_size=12),
        line('表7.2 模型消融实验结果',(180,280,420,291),font_size=10.5,bold=True)]
    assert run(ls,tables=((80,40,520,80),(80,300,520,400)))['16']['findings']==[]


def test_independent_caption_spacing_is_not_cross_line_body_citation():
    ls=[line('这是上一段正文描述的结果，并且其他设置详见',(60,100,540,112),font_size=12),
        line('表7.2 模型消融实验结果',(60,148,540,160),font_size=12)]
    assert [f['token'] for f in run(ls,tables=((80,175,520,300),))['16']['findings']]==['7.2']


@pytest.mark.parametrize('predicate',['指明了','解释了','阐述了'])
def test_short_continued_table_page_recognizes_larger_finite_body_sentence(predicate):
 ls=[line('表7.2（续）',(100,100,160,111),font_size=10.5),
     line('符号',(100,140,122,151),font_size=10.5),
     line('含义',(220,140,242,151),font_size=10.5),
     line('x',(100,180,108,191),font_size=10.5),
     line('输入数据',(220,180,260,191),font_size=10.5),
     line(f'表7.2 {predicate}各个符号对应的物理含义。',(90,690,360,703),font_size=12)]
 assert run(ls,tables=((95,125,500,300),))['16']['findings']==[]

def test_larger_finite_title_on_independent_visual_is_not_its_own_citation():
 ls=[line('表7.2（续）',(100,100,160,111),font_size=10.5),
     line('表7.2 解释了不同条件下的物理含义。',(180,690,420,703),font_size=12)]
 r=run(ls,tables=((95,125,500,300),(150,710,450,770)))
 assert r['16']['findings']


def test_parser_only_independent_visual_keeps_larger_finite_title_obligation():
 from pdf_rules.mineru_layout import LayoutObject
 ls=[line('表7.2（续）',(100,100,160,111),font_size=10.5),
     line('表7.2 解释了不同条件下的物理含义。',(180,690,420,703),font_size=12)]
 page=PdfPage(1,600,800,tuple(ls),tables=((95,125,500,300),))
 obj=LayoutObject('table',1,(150,710,450,770),'独立新表',600,800)
 assert contextual_caption(ls[1],page,'table',(obj,)) is not None
 doc=PdfDocument(Path('unseen-parser-table.pdf'),(page,))
 assert detect_rules(build_index(doc,(obj,)),[16])['16']['findings']

@pytest.mark.parametrize('title',['表7.2 持续增长的实验结果','表7.2 连续测量的物理参数'])
def test_continuation_word_inside_noun_title_is_not_a_continuation_marker(title):
 ls=[line(title,(100,100,280,111),font_size=10.5),
     line('表7.2 解释了不同条件下的物理含义。',(180,690,420,703),font_size=12)]
 page=PdfPage(1,600,800,tuple(ls),tables=((95,125,500,300),))
 assert contextual_caption(ls[1],page,'table') is not None


@pytest.mark.parametrize('source',['native','parser'])
def test_short_known_body_predicate_next_to_table_is_not_forced_into_title(source):
 from pdf_rules.mineru_layout import LayoutObject
 ls=[line('表7.2 两种方案性能比较',(180,100,420,111),font_size=10.5),
     line('表7.2 展示了两种方案的性能结果。',(90,310,360,323),font_size=12)]
 native=((95,125,500,300),) if source=='native' else ()
 objects=() if source=='native' else (LayoutObject('table',1,(95,125,500,300),'独立表',600,800),)
 page=PdfPage(1,600,800,tuple(ls),tables=native)
 assert contextual_caption(ls[1],page,'table',objects) is None
 doc=PdfDocument(Path('unseen-short-ordinary-body.pdf'),(page,))
 assert detect_rules(build_index(doc,objects),[16])['16']['findings']==[]
