from pathlib import Path
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.mineru_layout import LayoutObject
import pytest

def line(text, box=(60,100,540,112), **kw):
    return PdfLine(1,text,box,600,800,**kw)
def run(lines, objects=None, images=()):
    d=PdfDocument(Path('unseen.pdf'),(PdfPage(1,600,800,tuple(lines),images=images),))
    return detect_rules(build_index(d,objects),[11,15,16])

@pytest.mark.parametrize('text',['如图7.2-7.4所示。','如图(7-2)所示，另见图7-3与7-4。','图7.2, 7.3和7.4呈现了结果。'])
def test_grouped_citations_resolve_every_target(text):
    ls=[line(text)]+[line(f'图7.{n} 实验对照',(180,250+50*n,420,261+50*n)) for n in (2,3,4)]
    r=run(ls)
    assert r['11']['findings']==[] and r['15']['findings']==[]

def test_range_keeps_a_missing_member_and_precise_anchor():
    text='如图7.2-7.4所示。'
    regions=tuple((i,i+1,(60+i*10,100,70+i*10,112)) for i in range(len(text)))
    ls=[line(text,text_regions=regions),line('图7.2 起点',(180,300,420,311)),line('图7.4 终点',(180,500,420,511))]
    f=run(ls)['11']['findings']
    assert [x['token'] for x in f]==['7.3']
    assert f[0]['location']['bounding_rect']['x1']>=80

def test_table_list_does_not_consume_other_numbers():
    r=run([line('如表7.2、7.3和7.4所示，精度提高2.8。')]+[line(f'表7.{n} 结果',(180,250+n*50,420,261+n*50)) for n in (2,3,4)])
    assert r['16']['findings']==[]

def test_english_word_containing_fig_is_not_a_reference():
    assert run([line('(a) Bandwidth Result for Config1')])['11']['findings']==[]

@pytest.mark.parametrize('text',['该图援引自SMITH的Some Title[17]的图3','文献中的结构见Some Title[17]的图3-C'])
def test_external_source_possessive_is_not_local_reference(text):
    assert run([line(text)])['11']['findings']==[]

def test_external_source_does_not_hide_a_later_local_target():
    f=run([line('援引自Some Title[17]的图3，与本文图9.9比较。')])['11']['findings']
    assert [x['token'] for x in f]==['9.9']

@pytest.mark.parametrize('word,rule',[('图','15'),('表','16')])
def test_paragraph_first_line_is_a_reference_even_without_known_verb(word,rule):
    ls=[line(f'{word}7.2 汇报了不同方法的性能对比，可以看到我们所',(84,100,540,112)),line('提出的方法在所有任务上效果较好。',(60,120,540,132)),line(f'{word}7.2 对照结果',(180,300,420,311))]
    assert run(ls)[rule]['findings']==[]

@pytest.mark.parametrize('text',['图7.2 为了实现模型加速而对网络结构的修改','图7.2 引自Smith[17]工作的频谱示意图'])
def test_centered_caption_is_not_rejected_by_a_narrative_prefix(text):
    ls=[line('具体架构如图7.2所示。',(60,400,540,412)),line(text,(165,320,435,330)),line('另一段正文介绍研究背景与主要问题。',(60,420,540,432))]
    r=run(ls,images=((80,170,520,300),))
    assert r['11']['findings']==[] and r['15']['findings']==[]

def test_diagram_interior_labels_are_not_body_references():
    ls=[line('调用图8',(150,180,220,192)),line('如图9.2所示。',(60,430,540,442)),line('图7.2 关系结构',(180,360,420,371))]
    objs=[LayoutObject('figure',1,(80,140,520,340),'',600,800)]
    f=run(ls,objs)['11']['findings']
    assert [x['token'] for x in f]==['9.2']


def test_standalone_indented_body_sentence_above_table_is_not_a_caption():
    ls=[line('上一段正文用于说明实验方法与性能指标。',(60,100,540,112)),line('表7.2将两种方法的性能进行了对比。',(84,180,522,192)),line('表7.2 两种方法的性能对比',(160,218,440,229))]
    assert run(ls)['16']['findings']==[]

def test_unindented_caption_with_sentence_punctuation_remains_a_caption():
    ls=[line('上一段正文用于说明实验方法与性能指标。',(60,100,540,112)),line('图7.2 实验结果对比。',(180,218,420,229))]
    assert len(run(ls)['15']['findings'])==1


def test_native_vector_diagram_interior_is_excluded_when_only_rule11_selected(tmp_path):
    import pymupdf
    from pdf_rules.engine import detect
    path=tmp_path/'vector.pdf'
    with pymupdf.open() as pdf:
        p=pdf.new_page(width=600,height=800)
        p.insert_text((60,100),'Introduction to the system, as shown in Figure 7.2.',fontsize=12)
        p.draw_rect((80,160,520,320))
        p.draw_circle((180,220),25)
        p.draw_circle((400,220),25)
        p.draw_line((205,220),(375,220))
        p.insert_text((150,285),'Fig 9',fontsize=10)
        p.insert_text((200,350),'Figure 7.2 Graph structure',fontsize=11)
        p.insert_text((60,420),'The next experiment is shown in Figure 8.8.',fontsize=12)
        pdf.save(path)
    f=detect(path,[11])['rules']['11']['findings']
    assert [x['token'] for x in f]==['8.8']


@pytest.mark.parametrize('left,right',[('实验结果可以参见图(7-', '2)所示。'),('实验结果可以参见图7.2、','7.3所示。')])
def test_grouped_and_parenthesized_reference_can_soft_wrap(left,right):
    from pdf_rules.text_fragments import merge_reference_fragments
    ls=merge_reference_fragments([line(left,(60,100,540,112)),line(right,(60,120,400,132))])
    ls=(*ls,line('图7.2 第一组',(180,300,420,311)),line('图7.3 第二组',(180,400,420,411)))
    r=run(ls)
    assert r['11']['findings']==[]
    assert '7.2' not in [f['token'] for f in r['15']['findings']]
    if '、' in left:assert r['15']['findings']==[]

def test_figure_ru_number_word_order():
    r=run([line('其架构示意图如7.2所示。'),line('图7.2 模型结构',(180,300,420,311))])
    assert r['15']['findings']==[]


@pytest.mark.parametrize('word,rule',[('图','15'),('表','16')])
def test_unique_nearby_unnumbered_deictic_is_a_reference(word,rule):
    ls=[line(f'本方法的实验对比结果如{word}所示。',(60,180,540,192)),line(f'{word}7.2 方法比较',(180,300,420,311))]
    assert run(ls)[rule]['findings']==[]

def test_ambiguous_unnumbered_reference_does_not_mark_every_figure_referenced():
    ls=[line('实验结果如图所示。'),line('图7.2 方法一',(180,250,420,261)),line('图7.3 方法二',(180,350,420,361))]
    assert len(run(ls)['15']['findings'])==2

def test_distant_unnumbered_reference_cannot_hide_an_unrelated_figure():
    ls=[line('实验结果如图所示。',(60,90,540,102)),line('图7.2 另一个实验',(180,650,420,661))]
    assert len(run(ls)['15']['findings'])==1


@pytest.mark.parametrize('heading',['第八章 新实验','  第八章 新实验','8 New experiment'])
def test_unnumbered_reference_cannot_cross_a_chapter_heading(heading):
    ls=[line('结果如图所示。'),line(heading,(60,160,250,180)),line('图8.1 新实验结果',(180,250,420,261))]
    assert len(run(ls)['15']['findings'])==1


def test_numeric_measurement_after_comma_is_not_a_second_citation():
    ls=[line('根据图7.2，7.3%的样本出现误差。'),line('图7.2 已被引用',(180,300,420,311)),line('图7.3 未被引用',(180,400,420,411))]
    r=run(ls)
    assert r['11']['findings']==[]
    assert [f['token'] for f in r['15']['findings']]==['7.3']

@pytest.mark.parametrize('title',['图7.2 Experimental measurements and system architecture','图7.2 Experimental measurements of temperature, pressure and airflow'])
def test_two_line_indented_caption_with_visual_support_stays_a_caption(title):
    ls=[line(title,(84,100,540,112),block_id=1),line('Comparison across multiple datasets and acquisition conditions',(60,120,540,132),block_id=1),line('Further discussion describes system design and methodology.',(60,300,540,312),block_id=2)]
    r=run(ls,images=((60,40,540,80),))
    assert r['11']['findings']==[] and [f['token'] for f in r['15']['findings']]==['7.2']

def test_small_centered_body_reference_cannot_create_a_missing_figure():
    ls=[line('Further discussion describes system design and methodology.',(60,100,540,112)),line('图9.9显示了本方法的优势',(190,220,410,230)),line('Another paragraph describes system design and methodology.',(60,300,540,312))]
    r=run(ls)
    assert [f['token'] for f in r['11']['findings']]==['9.9']
    assert r['15']['findings']==[]


def test_figure_caption_cannot_hide_citation_inside_adjacent_real_table():
    ls=[line('图7.2 模型结构',(180,280,420,291)),line('See Fig 9.9',(160,360,300,372)),line('Further discussion describes system design and methodology.',(60,500,540,512))]
    page=PdfPage(1,600,800,tuple(ls),images=((80,140,520,260),),tables=((80,320,520,450),),graphics=((80,320,520,450),))
    d=PdfDocument(Path('unseen.pdf'),(page,))
    f=detect_rules(build_index(d),[11])['11']['findings']
    assert [x['token'] for x in f]==['9.9']


def test_body_column_edge_uses_typical_margin_not_one_overflowing_line():
    ls=[line('第一段介绍实验方法及环境设置与实现细节。',(60,100,540,112)),line('第二段说明样本来源和实验参数取值范围。',(60,120,540,132)),line('这里有略微伸出版心边界的英文长词句子。',(60,140,550,152)),line('表7.2将两种方法的性能进行了对比。',(84,180,527,192)),line('表7.2 两种方法的性能对比',(160,218,440,229))]
    assert run(ls)['16']['findings']==[]


def measured(text,box,size,bold=False,**kw):
    from dataclasses import dataclass
    @dataclass(frozen=True)
    class MeasuredLine(PdfLine):
        font_size: float|None=None
        bold: bool=False
    return MeasuredLine(1,text,box,600,800,font_size=size,bold=bold,**kw)

def test_smaller_bold_multiline_sentence_caption_is_not_body_prose():
    ls=[measured('图7.2 过渡态结构示意图。过渡态结构是临界状态。',(81,100,540,111),10.5,True,block_id=1),measured('各种构型对应不同反应路径和计算结果。',(60,120,540,131),10.5,True,block_id=1),measured('后续正文讨论实验细节和不同参数下的观测结果。',(60,300,540,312),12)]
    r=run(ls,images=((60,40,540,80),))
    assert r['11']['findings']==[] and len(r['15']['findings'])==1

def test_body_reference_at_page_bottom_uses_body_typography():
    ls=[measured('上方正文介绍研究方法和性能指标的测量方法。',(60,100,540,112),12),measured('图7.2 和7.3 展示了两种方法的实验对比与结果',(84,730,540,742),12),measured('图7.2 第一组实验',(180,300,420,311),10.5,True),measured('图7.3 第二组实验',(180,500,420,511),10.5,True)]
    assert run(ls)['15']['findings']==[]

def test_parenthesized_3d_description_is_not_a_figure_number():
    assert run([line('创新性地提出了图（3D 几何）结构。')])['11']['findings']==[]


def test_parenthesized_list_keeps_all_members_including_a_missing_first_one():
    r=run([line('如图（7.2、7.3）所示。'),line('图7.3 实验结果',(180,300,420,311))])
    assert [f['token'] for f in r['11']['findings']]==['7.2']
    assert r['15']['findings']==[]


def test_bold_small_prose_reference_beside_table_does_not_create_figure():
    ls=[measured('普通正文介绍系统设计及实验方法和参数。',(60,100,540,112),12),measured('图9.9汇报了不同方法的性能对比，可以看到结果差异。',(84,250,540,261),10.5,True),measured('普通正文解释实验结果和性能差异的原因。',(60,400,540,412),12)]
    page=PdfPage(1,600,800,tuple(ls),tables=((80,160,520,240),))
    r=detect_rules(build_index(PdfDocument(Path('unseen.pdf'),(page,))),[11,15])
    assert [f['token'] for f in r['11']['findings']]==['9.9'] and r['15']['findings']==[]


def test_parenthesized_spaced_range_retains_a_missing_middle_member():
    r=run([line('如图（7.2 - 7.4）所示。'),line('图7.2 第一组',(180,300,420,311)),line('图7.4 最后一组',(180,500,420,511))])
    assert [f['token'] for f in r['11']['findings']]==['7.3']
    assert r['15']['findings']==[]


@pytest.mark.parametrize('word,kind',[('图','figure'),('表','table')])
def test_centered_bold_sentence_caption_on_graphics_only_page(word,kind):
    from pdf_rules.caption_context import contextual_caption
    # A graphics-only page has a table header and other wide titles, not prose.
    header=line('方法和各项实验指标 measurement interval throughput',(110,130,535,142),font_size=10.5)
    other=line('图7.1 不同参数设置下各组模型的计算代价与结果',(70,430,510,442),font_size=10.5,bold=True)
    title=line(f'{word}7.2 不同任务分组的平均响应时间与模型性能对比。',(94,700,494,712),font_size=10.5,bold=True)
    page=PdfPage(1,600,800,(header,other,title),images=((158,490,421,690),),tables=((70,125,510,220),))
    assert contextual_caption(title,page,kind) is not None


def test_bold_indented_body_sentence_is_not_recovered_as_centered_caption():
    from pdf_rules.caption_context import contextual_caption
    body=line('正文介绍实验方法和指标，下面讨论不同配置。',(60,100,540,112),font_size=12)
    prose=line('图7.2 汇报了不同任务分组的平均响应时间与模型性能。',(84,700,540,712),font_size=12,bold=True)
    page=PdfPage(1,600,800,(body,prose),images=((158,490,421,690),))
    assert contextual_caption(prose,page,'figure') is None


def test_balanced_bold_body_sentence_keeps_missing_reference():
    body=line('正文介绍实验方法和指标，下面讨论不同配置。',(60,100,540,112),font_size=12)
    prose=line('图9.9 所包含的模块依次为数据采集、特征计算和结果分析。',(84,700,522,712),font_size=12,bold=True)
    r=run([body,prose],images=((158,490,421,690),))
    assert [f['token'] for f in r['11']['findings']]==['9.9']
    assert r['15']['findings']==[]


def test_figure_prefixed_prose_blocks_bold_caption_recovery():
    body=line('图7.2 展示了实验装置和所有测量指标，下面讨论不同配置。',(60,100,540,112),font_size=12)
    prose=line('图9.9 所包含的模块依次为数据采集、特征计算和结果分析。',(84,700,522,712),font_size=12,bold=True)
    r=run([body,prose],images=((158,490,421,690),))
    assert [f['token'] for f in r['11']['findings']]==['7.2','9.9']
    assert r['15']['findings']==[]


@pytest.mark.parametrize('text', [
    '资料来源：https://example.org/experiment_fig2',
    'Source: https://example.org/article/figure9',
    'See user_fig8@example.org for details.',
    'The file experiment_fig3.png stores the measurements.',
])
def test_resource_identifiers_do_not_create_local_figure_citations(text):
    assert run([line(text)])['11']['findings'] == []


def test_resource_identifier_does_not_hide_later_local_citation():
    findings = run([line('https://example.org/x_fig2，实验如图9.9所示。')])['11']['findings']
    assert [f['token'] for f in findings] == ['9.9']


def test_real_english_figure_citation_without_space_remains_detected():
    findings = run([line('The experiment is shown in Figure9.')])['11']['findings']
    assert [f['token'] for f in findings] == ['9']



def test_explicit_next_table_colon_is_a_reference():
    r=run([line('得到的不同类别的样本数如下表：',(60,180,520,192)),
           line('表4.2 示例数量',(160,215,440,228))])
    assert r['16']['findings']==[]


def test_next_table_colon_does_not_resolve_two_tables():
    r=run([line('比较结果如下表：',(60,180,520,192)),
           line('表4.2 方法一',(160,215,440,228)),line('表4.3 方法二',(160,300,440,313))])
    assert [f['token'] for f in r['16']['findings']]==['4.2','4.3']


@pytest.mark.parametrize('symbol',['A\u0de9','B\u0de8','C\u0662'])
def test_math_font_foreign_digit_mapping_does_not_create_a_figure_number(symbol):
    # Some math fonts map an accent to an unrelated Unicode decimal digit.
    # Chinese/English academic labels use normalized ASCII Arabic numerals.
    assert run([line(f'得到平滑后的显著性图{symbol}，随后进行数值截断。')])['11']['findings']==[]

@pytest.mark.parametrize('number',['A9','A.9','9.9','９．９'])
def test_standard_and_fullwidth_missing_figure_labels_remain_detected(number):
    assert len(run([line(f'结果如图{number}所示。')])['11']['findings'])==1


@pytest.mark.parametrize('word,rule',[('表','16'),('图','15')])
def test_whitespace_separated_same_chapter_citation_series(word,rule):
    ls=[line(f'基准数据集的结果如{word}7.2 7.3 7.4，各方法的指标如下。')]
    ls += [line(f'{word}7.{i} 数据集{i}结果',(180,250+i*50,420,261+i*50)) for i in (2,3,4)]
    assert run(ls)[rule]['findings']==[]

def test_numeric_measurement_after_reference_is_not_whitespace_list():
    ls=[line('如图7.2，得分7.3。'),line('图7.2 主结果',(180,300,420,311)),line('图7.3 另一实验',(180,400,420,411))]
    assert [x['token'] for x in run(ls)['15']['findings']]==['7.3']

def test_whitespace_citation_does_not_consume_cross_chapter_decimal():
    ls=[line('如图7.2 0.95的置信水平所示。'),line('图7.2 主结果',(180,300,420,311)),line('图0.95 另一结果',(180,400,420,411))]
    assert [x['token'] for x in run(ls)['15']['findings']]==['0.95']



def test_styled_empty_caption_fragment_is_not_a_body_reference_or_target():
    from dataclasses import replace
    ls=[line('本文分析模型之间的差异与相关实验条件。',(60,100,540,112),font_size=12),
        line('图7.1 完整实验结果',(190,300,410,311),font_size=10.5,bold=True),
        line('图7.2',(280,332,320,343),font_size=10.5,bold=True),
        line('图7.2展示了另一组结果。',(84,420,420,432),font_size=12)]
    findings=run(ls)['11']['findings']
    assert len(findings)==1 and findings[0]['page']==1
    assert findings[0]['location']['bounding_rect']['y1']>=420



def test_short_body_reference_near_caption_is_not_discarded():
    ls=[line('本文分析模型之间的差异与相关实验条件。',(60,100,540,112),font_size=12),
        line('图7.1 完整实验结果',(190,300,410,311),font_size=10.5,bold=True),
        line('图7.2',(60,332,100,344),font_size=12)]
    assert len(run(ls)['11']['findings'])==1
