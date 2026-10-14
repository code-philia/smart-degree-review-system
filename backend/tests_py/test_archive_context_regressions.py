"""General regressions from independently inspected archive page structures."""
from pathlib import Path
from dataclasses import replace
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.numbering import normalize_text
from pdf_rules.text_fragments import merge_reference_fragments
from pdf_rules.native_layout import merge_caption_fragments
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject


def line(text, box=(60,100,540,115), **kw):
    return PdfLine(1,text,box,600,800,**kw)

def doc(lines=(), images=(), tables=()):
    return PdfDocument(Path('unseen.pdf'),(PdfPage(1,600,800,tuple(lines),images=tuple(images),tables=tuple(tables)),))

def obj(kind,box,text='',role=''):
    return LayoutObject(kind,1,box,text,600,800,role)

def local(lines):
    return detect_rules(build_index(doc(lines)),[11,15,16])

def captions(objects, lines=(), images=(), tables=()):
    d=doc(lines,images,tables)
    return detect_caption_rules(prepare_caption_layout(objects,d),[13,14],d)


def test_hyphenated_figure_number_can_wrap_after_separator():
    ls=[line('实验结果及具体的实现方法如图7-',(60,100,540,115)),line('8所示，以下讨论其结果。',(60,123,360,138)),line('图7-8 完整标题',(180,350,420,365))]
    r=local(merge_reference_fragments(ls))
    assert r['11']['findings']==[] and r['15']['findings']==[]

@pytest.mark.parametrize('text',['参见图7.8①所示。','参见图7.8²所示。'])
def test_footnote_glyph_cannot_change_figure_number(text):
    r=local([line(text),line('图7.8 完整标题',(180,350,420,365))])
    assert r['11']['findings']==[] and r['15']['findings']==[]

@pytest.mark.parametrize('text',['增强视图1','对视图G1进行计算。','构图2个维度','摄影、绘画、AIGC 图 8 个维度'])
def test_technical_nouns_and_quantities_are_not_figure_references(text):
    assert local([line(text)])['11']['findings']==[]

@pytest.mark.parametrize('text',['引自文献[31]的图2。','Figure 7.8 Example. Cited from Fig. 2 in[31].','参考文献[31]中的图2。'])
def test_external_figure_is_not_local_missing_target(text):
    assert local([line(text)])['11']['findings']==[]


def test_external_reference_does_not_hide_local_reference_in_same_sentence():
    r=local([line('引自文献[31]的图2，与本论文图8.9对比。')])
    assert [f['token'] for f in r['11']['findings']]==['8.9']


def test_repeated_targets_on_one_row_have_distinct_character_rectangles():
    text='由图8.9(a)和图8.9(b)可知。'
    regions=tuple((i,i+1,(60+i*10,100,70+i*10,115)) for i in range(len(text)))
    found=local([line(text,text_regions=regions)])['11']['findings']
    assert len(found)==2
    assert found[0]['location']['bounding_rect']!=found[1]['location']['bounding_rect']


def test_caption_narrative_and_source_note_are_not_titles():
    r=local([line('表7.8列举一些现象并进行说明。'),line('图7.8引用自[31]',(80,720,210,731)),line('表7.8 参数汇总',(180,300,420,315)),line('图7.8 网络结构',(180,400,420,415))])
    assert r['15']['findings']==[] and r['16']['findings']==[]


def test_two_unlabelled_panels_with_full_width_shared_caption_are_one_figure():
    objects=[obj('figure',(60,150,270,250),role='chart_body'),obj('figure',(290,150,510,250),role='chart_body'),obj('figure_caption',(65,270,505,285),'Figure 7.8 Comparison of two experimental settings')]
    assert captions(objects)['13']['findings']==[]


def test_shared_panel_caption_does_not_cover_a_separate_lower_untitled_figure():
    objects=[obj('figure',(60,150,270,250)),obj('figure',(290,150,510,250)),obj('figure_caption',(65,270,505,285),'Figure 7.8 Comparison of two settings'),obj('figure',(60,330,510,450))]
    found=captions(objects)['13']['findings']
    assert len(found)==1 and found[0]['location']['bounding_rect']['y1']==330


def test_nearly_contained_native_fragment_is_not_an_extra_figure():
    objects=[obj('figure',(95,190,510,350),role='image_body'),obj('figure_caption',(190,365,420,380),'Figure 7.8 Workflow')]
    assert captions(objects,images=[(96,187,268,361)])['13']['findings']==[]


def test_raster_table_shape_with_figure_title_is_one_figure_not_extra_table():
    objects=[obj('table',(90,270,520,390),role='table_body'),obj('figure_caption',(215,410,415,435),'Figure 7.8 Generalisation')]
    result=captions(objects,images=[(85,262,529,399)])
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_incomplete_appendix_number_still_has_a_title():
    lines=merge_caption_fragments([line('表.2',(86,560,107,572)),line('规范流组件消融研究中的误差',(114,560,480,572))])
    found=captions([obj('table',(90,595,510,700),role='table_body')],lines)['14']['findings']
    assert found==[]


def test_real_missing_targets_and_titles_are_retained():
    assert len(local([line('如图9.3所示。')])['11']['findings'])==1
    r=captions([obj('figure',(80,200,520,350)),obj('table',(80,450,520,650))])
    assert len(r['13']['findings'])==len(r['14']['findings'])==1


def test_rotated_caption_fragments_are_joined_in_reading_direction():
    # Native PDF lines carry a vertical baseline, while boxes stay in page coordinates.
    a=line('Figure 7.8',(520,490,532,540))
    b=line('Complete diagram title',(520,280,532,480))
    # Use attribute-independent construction until direction metadata is added.
    if 'direction' in PdfLine.__dataclass_fields__:
        a=replace(a,direction=(0.,-1.));b=replace(b,direction=(0.,-1.))
    ls=merge_caption_fragments([a,b])
    result=captions([obj('figure',(80,120,490,710))],ls)
    assert result['13']['findings']==[]
    assert local(ls)['11']['findings']==[]


def test_plot_axes_do_not_prevent_same_paragraph_caption_fragments_joining():
    a=line('Figure 7.8',(85,261,130,272),block_id=3)
    b=line('Learning curves for two models',(140,261,495,272),block_id=3)
    lines=merge_caption_fragments([a,b],tables=[(94,198,276,300)])
    assert local(lines)['11']['findings']==[]


@pytest.mark.parametrize('word',['图','表'])
def test_caption_box_can_overlap_object_edge_by_font_descenders(word):
    kind='figure' if word=='图' else 'table';rule='13' if word=='图' else '14'
    objects=[obj(kind,(80,200,520,500)),obj(kind+'_caption',(110,170,490,204),word+'7.8 实验结果')]
    assert captions(objects)[rule]['findings']==[]


def test_contiguous_table_blocks_share_one_title():
    objects=[obj('table',(80,200,520,390),role='table_body'),obj('table',(80,390,520,520),role='table_body'),obj('table_caption',(180,160,450,185),'Table 7.8 Configuration')]
    assert captions(objects)['14']['findings']==[]


def test_stacked_panels_with_repeated_row_labels_are_one_table():
    lines=[line(text,(90,y,180,y+12)) for text,y in [('Method',220),('Alpha',250),('Beta',280),('Gamma',310),('Method',360),('Alpha',390),('Beta',420),('Gamma',450)]]
    lines += [line('Score',(300,220,360,232)),line('Score',(300,360,360,372))]
    objects=[obj('table',(80,200,520,335),role='table_body'),obj('table',(80,345,520,480),role='table_body'),obj('table_caption',(180,165,450,185),'Table 7.8 Comparison')]
    assert captions(objects,lines)['14']['findings']==[]


def test_separate_untitled_table_with_different_rows_is_retained():
    lines=[line(text,(90,y,180,y+12)) for text,y in [('Method',220),('Alpha',250),('Beta',280),('Gamma',310),('Method',360),('Delta',390),('Epsilon',420),('Zeta',450)]]
    objects=[obj('table',(80,200,520,335)),obj('table',(80,345,520,480)),obj('table_caption',(180,165,450,185),'Table 7.8 Comparison')]
    assert len(captions(objects,lines)['14']['findings'])==1


def test_illustration_phrase_is_a_real_reference():
    result=local([line('具体结构示意图7.8。'),line('图7.8 结构说明',(180,350,420,365))])
    assert result['15']['findings']==[]


def test_explicit_figure_directory_with_separate_page_numbers_is_not_a_caption_page():
    lines=[line('插 图',(260,65,320,85)),line('图7.8 长条目含数学公式',(60,130,530,145)),line('余下的解释................',(90,150,510,165)),line('23',(525,150,540,165)),line('图7.9 下一条目........24',(60,180,540,195)),line('图8.1 最后一条........30',(60,210,540,225))]
    result=local(lines)
    assert result['15']['findings']==[]


def test_icons_inside_captioned_table_are_not_separate_untitled_figures():
    objects=[obj('figure',(80,180,520,400),role='image_body'),obj('table_caption',(160,150,440,170),'Table 7.8 Widget types')]
    r=captions(objects,images=[(120,220,150,250),(200,220,235,255)],tables=[(80,180,520,400)])
    assert r['13']['findings']==[] and r['14']['findings']==[]


def test_algorithm_raster_with_explicit_parser_code_evidence_is_not_a_figure():
    objects=[obj('text',(80,200,520,500),'算法7.8 采样算法\n1: for x in input do\n2: return x\n3: end for',role='code_body')]
    assert captions(objects,images=[(80,200,520,350),(80,350,520,500)])['13']['findings']==[]


def test_touching_chart_rows_and_columns_share_a_full_width_caption():
    objects=[obj('figure',(x,y,x+140,y+100),role='chart_body') for y in (150,252,354) for x in (80,225,370)]
    objects.append(obj('figure_caption',(85,470,505,487),'Figure 7.8 Comparisons in different conditions'))
    assert captions(objects)['13']['findings']==[]


def test_side_by_side_separate_captions_prevent_grid_merge():
    objects=[obj('figure',(x,y,x+190,y+100),role='chart_body') for y in (150,250) for x in (80,300)]
    objects += [obj('figure_caption',(80,365,270,382),'Figure 7.8 First result'),obj('figure_caption',(300,365,490,382),'Figure 7.9 Second result')]
    assert captions(objects)['13']['findings']==[]


def test_overlapping_native_table_windows_form_one_table():
    objects=[obj('table',(80,200,520,245),role='native_table'),obj('table',(80,215,520,450),role='native_table'),obj('table',(80,450,520,600),role='native_table'),obj('table_caption',(160,150,440,195),'Table 7.8 Results')]
    assert captions(objects)['14']['findings']==[]


def test_directory_heading_and_other_entries_exclude_broken_leader_entry():
    lines=[line('插',(250,60,260,76)),line('图',(280,60,290,76)),line('图7.8 Long mathematical caption',(60,130,530,145)),line('Wrapped formula and text. 23',(90,150,540,165)),line('图7.9 Next entry........24',(60,180,540,195)),line('图8.1 Last entry........30',(60,210,540,225))]
    assert local(lines)['15']['findings']==[]


@pytest.mark.parametrize('sentence',['表格7.8中的结果表明模型有效。','表格7.8和表格7.9分别展示了比较结果。'])
def test_table_full_word_is_recognised_as_reference(sentence):
    r=local([line(sentence),line('表7.8 数据集比较',(180,300,450,315))])
    assert r['16']['findings']==[]

@pytest.mark.parametrize('sentence',['图7.8介绍了整个数据处理流程。','图7.8直观展示了实验结果。','图7.8可视化了模型在不同条件下的性能。','图7.8对各类方法进行了对比。'])
def test_finite_predicate_is_a_body_reference_not_an_extra_caption(sentence):
    r=local([line(sentence),line('图7.8 模型比较',(180,300,450,315))])
    assert r['15']['findings']==[]


def test_figure_number_after_shown_phrase_is_still_a_reference():
    r=local([line('如图所示7.8，我们观察到变化。'),line('图7.8 变化趋势',(180,300,450,315))])
    assert r['15']['findings']==[]


def test_spaced_dot_leaders_and_word_joiner_do_not_create_captions():
    assert local([line('表7.8 数据统计 . . . . . . \u206024')])['16']['findings']==[]


@pytest.mark.parametrize('sentence',[
    'As can be seen from Fig. 8.9, the error decreases.',
    '如网络结构图8.9所示。', '如网络拓扑图8.9所示。'])
def test_ordinary_reference_context_cannot_hide_a_missing_target(sentence):
    assert [f['token'] for f in local([line(sentence)])['11']['findings']]==['8.9']
    assert local([line(sentence),line('Figure 8.9 Complete title',(150,300,480,315))])['15']['findings']==[]


def test_restarted_panel_labels_prevent_merging_independent_figures():
    objects=[obj('figure',(80,200,520,350),role='chart_body'),obj('figure',(80,354,520,500),role='chart_body'),obj('figure_caption',(160,165,440,185),'Figure 7.8 First experiment')]
    lines=[line('(a)',(90,210,110,222)),line('(a)',(90,364,110,376))]
    found=captions(objects,lines)['13']['findings']
    assert len(found)==1 and found[0]['location']['bounding_rect']['y1']==354


def test_different_table_headers_prevent_merging_repeated_methods():
    lines=[line(text,(90,y,180,y+12)) for text,y in [('Method',220),('Alpha',250),('Beta',280),('Gamma',310),('Method',360),('Alpha',390),('Beta',420),('Gamma',450)]]
    lines += [line('Dataset A',(300,220,450,232)),line('Dataset B',(300,360,450,372))]
    objects=[obj('table',(80,200,520,335)),obj('table',(80,345,520,480)),obj('table_caption',(160,160,460,185),'Table 7.8 Results for dataset A')]
    assert len(captions(objects,lines)['14']['findings'])==1



def test_external_restarted_labels_prevent_vertical_panel_merge():
    objects=[obj('figure',(80,200,520,350),role='chart_body'),obj('figure',(80,354,520,500),role='chart_body'),obj('figure_caption',(160,165,440,185),'Figure 7.8 First experiment')]
    lines=[line('(a)',(90,350,110,362)),line('(a)',(90,500,110,512))]
    assert len(captions(objects,lines)['13']['findings'])==1


def test_restarted_labels_prevent_shared_horizontal_title_merge():
    objects=[obj('figure',(60,150,270,250),role='chart_body'),obj('figure',(290,150,510,250),role='chart_body'),obj('figure_caption',(65,270,505,285),'Figure 7.8 Comparison of two settings')]
    lines=[line('(a)',(90,160,110,172)),line('(a)',(320,160,340,172))]
    assert len(captions(objects,lines)['13']['findings'])==1


def test_incomplete_last_row_of_labelled_panels_shares_full_width_title():
    objects=[obj('figure',(90,240,245,400)),obj('figure',(325,240,480,400)),obj('figure',(90,430,245,530)),obj('figure_caption',(75,565,515,585),'Figure 7.8 Three examples')]
    lines=[line('(a) example',(90,409,240,420)),line('(b) example',(325,409,475,420)),line('(c) example',(90,540,240,551))]
    assert captions(objects,lines)['13']['findings']==[]


def test_uneven_image_grid_with_shared_title_rejoins_small_row_gaps():
    objects=[obj('figure',(x,y,x+w,y+h),role='image_body') for x,w in ((80,120),(220,300)) for y,h in ((100,180),(287,90))]
    objects.append(obj('figure_caption',(75,405,525,430),'Figure 7.8 Input, ground truth and reconstructed data'))
    assert captions(objects)['13']['findings']==[]


def test_centred_caption_continuation_can_be_a_separate_pdf_block():
    lines=[line('表7.8 多行中文标题中的各个内容',(70,100,530,112),block_id=1),line('由输入动态生成。',(260,118,340,130),block_id=2),line('Table 7.8 A long table title',(100,138,500,150),block_id=3)]
    assert len(local(lines)['16']['findings'])==1
