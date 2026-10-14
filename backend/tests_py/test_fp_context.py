"""FP regressions: distinguish references, object identity and layout noise."""
import unittest
from pathlib import Path
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.model import PdfDocument, PdfLine, PdfPage
from pdf_rules.numbering import caption_match, FIGURE_REFERENCE, normalize_text
from pdf_rules.text_fragments import merge_reference_fragments
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.layout_context import prepare_caption_layout
from pdf_rules.caption_rules import detect_caption_rules

class ReferenceContextTests(unittest.TestCase):
    def line(self,text,box=(60,100,540,115)):
        return PdfLine(1,text,box,600,800)
    def test_feature_map_variable_is_not_partial_figure_number(self):
        self.assertEqual(list(FIGURE_REFERENCE.finditer(normalize_text('高维度的特征图𝐹2𝐷'))),[])
        self.assertEqual([m.group('number') for m in FIGURE_REFERENCE.finditer('参见图A2和图4.7。')],['A2','4.7'])
    def test_narrative_references_at_start_of_line_are_not_captions(self):
        texts=[('figure','图2.1概括为四个关键阶段。'),('figure','图5.2以柱状图形式直观展示三种方法。'),
          ('figure','图2.9研究了用户数量对性能的影响。'),('figure','图3.15通过箱线图展示统计分布。'),
          ('figure','图4.8绘制了误差分布。'),('figure','图4.10定义了波束角。'),
          ('figure','图4.5对比展示了优化前后的质量。'),('table','表5.1和表5.2展示了结果。'),
          ('table','表5.2与表5.3分别给出了分类结果。'),('table','表4.3总结了各工具及其功能。'),
          ('table','表4.7的实验数据清晰地反映了性能差异。'),('table','表3.3区分了私有输入和公开输入。'),
          ('table','表5.1系统性地展示了程序样例。')]
        for kind,text in texts:
            with self.subTest(text=text):self.assertIsNone(caption_match(text,kind))
    def test_real_captions_keep_self_number_excluded_from_references(self):
        lines=tuple(self.line(t,(100,y,450,y+15)) for t,y in [('图3.8 概括性框架',120),('表7.6 系统配置参数',300)])
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
        rules=detect_rules(build_index(doc),[15,16])
        self.assertEqual([f['token'] for f in rules['15']['findings']],['3.8'])
        self.assertEqual([f['token'] for f in rules['16']['findings']],['7.6'])
    def test_wrapped_body_reference_resolves_and_keeps_number_bbox(self):
        lines=(self.line('本节在相同数据集上进行统一评估，实验结果如表',(60,100,540,115)),
               self.line('7.6所示。两组实验采用相同的输入。',(60,123,340,138)),
               self.line('表7.6 系统配置参数',(200,300,440,315)))
        joined=merge_reference_fragments(lines)
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,joined),))
        self.assertEqual(detect_rules(build_index(doc),[16])['16']['findings'],[])
        ref=build_index(doc).table_refs[0];self.assertEqual(ref.number,'7.6');self.assertGreaterEqual(ref.line.bbox[1],123)
    def test_a_subpanel_reference_counts_as_a_reference_to_its_parent(self):
        lines=(self.line('由图7.3a和图7.3b可知实验结果。'),self.line('图7.3 系统测量结果',(180,400,460,415)))
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
        self.assertEqual(detect_rules(build_index(doc),[15])['15']['findings'],[])
    def test_split_subpanel_reference_resolves_to_its_parent(self):
        lines=(self.line('See Figure',(60,100,120,115)),self.line('5.6a for the measurement.',(125,100,300,115)),self.line('Figure 5.6 Result',(180,400,450,415)))
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,merge_reference_fragments(lines)),))
        self.assertEqual(detect_rules(build_index(doc),[15])['15']['findings'],[])
    def test_finite_description_verbs_remain_body_references(self):
        for text in ('图7.3进一步刻画了随时间的变化。','图7.3描绘了整个传输时段。'):
            self.assertIsNone(caption_match(text,'figure'))
    def test_caption_prefix_and_unrelated_next_line_are_not_body_reference(self):
        lines=(self.line('Figure',(260,100,295,115)),self.line('7.6',(60,130,90,145)))
        self.assertEqual(merge_reference_fragments(lines),lines)

    def test_same_row_reference_has_priority_over_a_wrapped_number(self):
        lines=(self.line('A long experimental sentence ends with Figure',(60,100,480,115)),
               self.line('1.2',(490,100,515,115)),self.line('3.4 describes the next paragraph.',(60,123,480,138)),
               self.line('Figure 3.4 Existing result',(200,400,450,415)))
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,merge_reference_fragments(lines)),))
        self.assertEqual([f['token'] for f in detect_rules(build_index(doc),[11])['11']['findings']],['1.2'])

class ObjectIdentityTests(unittest.TestCase):
    def obj(self,kind,box,text='',role=''):
        return LayoutObject(kind,1,box,text,600,800,role)
    def detect(self,objects,lines=(),images=(),tables=()):
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,tuple(lines),images=images,tables=tables),))
        return detect_caption_rules(prepare_caption_layout(objects,doc),[13,14],doc)
    def line(self,text,box):return PdfLine(1,text,box,600,800)
    def test_panels_with_labels_inside_plot_use_one_shared_title(self):
        boxes=[(70,200,210,320),(220,200,360,320),(370,200,510,320)]
        lines=[self.line(f'({letter}) Model', (box[0]+20,205,box[2]-5,219)) for letter,box in zip('abc',boxes)]
        objects=[self.obj('figure',box,role='chart_body') for box in boxes]+[self.obj('figure_caption',(150,330,450,347),'Figure 8.3 Results')]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_panel_envelope_can_contain_multiple_next_tags(self):
        objects=[self.obj('figure',(80,200,185,290)),self.obj('figure',(190,200,520,290)),self.obj('figure_caption',(100,325,530,343),'Figure 2.6 Comparison')]
        lines=[self.line(f'({letter}) Output',(x,297,x+75,309)) for letter,x in zip('abcd',(100,200,310,430))]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_double_parentheses_panel_labels_are_supported(self):
        boxes=[(80,200,210,320),(235,200,380,320),(400,200,520,320)]
        lines=[self.line(f'(({letter})) Example',(box[0]+5,325,box[2]-5,340)) for letter,box in zip('abc',boxes)]
        objects=[self.obj('figure',box) for box in boxes]+[self.obj('figure_caption',(100,355,530,373),'Figure 8.3 Results')]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_unlabelled_independent_figures_do_not_share_one_title(self):
        objects=[self.obj('figure',(60,150,270,250)),self.obj('figure',(300,150,510,250)),self.obj('figure_caption',(220,280,440,300),'Figure 2.1 One result')]
        self.assertEqual(len(self.detect(objects)['13']['findings']),1)
    def test_minor_caption_box_overlap_is_not_a_missing_table_title(self):
        objects=[self.obj('table',(80,200,520,360)),self.obj('table_caption',(160,173,440,201),'Table 3.7 Results')]
        self.assertEqual(self.detect(objects)['14']['findings'],[])
    def test_body_inside_table_cannot_supply_a_title(self):
        objects=[self.obj('table',(80,200,520,360)),self.obj('table_caption',(160,250,440,270),'Table 3.7 Cell label')]
        self.assertEqual(len(self.detect(objects)['14']['findings']),1)
    def test_algorithm_frame_is_not_a_research_table(self):
        lines=[self.line('算法2.4 数据处理流程',(80,200,440,215)),self.line('Input: samples',(80,220,300,235)),self.line('for each sample do',(80,245,300,260)),self.line('return output',(80,310,300,325))]
        objects=[self.obj('table',(80,195,520,345))]
        self.assertEqual(self.detect(objects,lines)['14']['findings'],[])
    def test_real_untitled_table_containing_algorithm_names_still_reports(self):
        lines=[self.line('算法2.4',(90,220,180,235)),self.line('Accuracy 0.9',(300,220,430,235))]
        objects=[self.obj('table',(80,195,520,345))]
        self.assertEqual(len(self.detect(objects,lines)['14']['findings']),1)
    def test_native_plot_grid_inside_parsed_chart_is_not_a_table(self):
        objects=[self.obj('figure',(80,150,520,350),role='chart_body'),self.obj('figure_caption',(160,363,470,380),'Figure 6.4 Results')]
        self.assertEqual(self.detect(objects,tables=((85,220,490,342),))['14']['findings'],[])
    def test_table_rendered_as_image_keeps_its_table_identity(self):
        objects=[self.obj('table',(80,150,520,350),role='table_body')]
        result=self.detect(objects,images=((80,150,520,350),))
        self.assertEqual(result['13']['findings'],[]);self.assertEqual(len(result['14']['findings']),1)

    def test_a_chart_misparsed_as_table_uses_explicit_figure_title(self):
        objects=[self.obj('table',(80,150,520,350),role='table_body'),
                 self.obj('figure_caption',(160,363,470,380),'Figure 6.4 Layout')]
        result=self.detect(objects,images=((80,150,520,350),))
        self.assertEqual(result['13']['findings'],[]);self.assertEqual(result['14']['findings'],[])
    def test_an_unnumbered_glossary_title_counts_as_table_title(self):
        objects=[self.obj('table',(160,200,440,600),role='table_body')]
        lines=[self.line('中英文术语对照表',(220,160,380,180))]
        self.assertEqual(self.detect(objects,lines)['14']['findings'],[])

    def test_algorithm_data_table_is_not_suppressed_as_pseudocode(self):
        lines=[self.line('Algorithm 2.4',(80,200,440,215)),self.line('Input size',(80,225,280,240)),self.line('Return accuracy',(80,250,290,265)),self.line('0.9',(300,275,335,290))]
        self.assertEqual(len(self.detect([self.obj('table',(80,195,520,345))],lines)['14']['findings']),1)
    def test_neighbour_figure_title_cannot_hide_an_untitled_raster_table(self):
        objects=[self.obj('table',(80,150,520,350),role='table_body'),self.obj('figure',(80,410,520,550),role='image_body'),self.obj('figure_caption',(180,373,420,388),'Figure 2.1 Lower plot')]
        result=self.detect(objects,images=((80,150,520,350),(80,410,520,550)))
        self.assertEqual(len(result['14']['findings']),1)
    def test_internal_panel_labels_cannot_borrow_a_title_only_under_the_first_object(self):
        objects=[self.obj('figure',(60,150,270,250)),self.obj('figure',(300,150,510,250)),self.obj('figure_caption',(80,265,260,283),'Figure 2.1 First result')]
        lines=[self.line('(a) Model',(90,180,240,195)),self.line('(b) Model',(330,180,480,195))]
        self.assertEqual(len(self.detect(objects,lines)['13']['findings']),1)

class PanelAndOwnershipBoundaryTests(unittest.TestCase):
    obj=ObjectIdentityTests.obj
    line=ObjectIdentityTests.line
    detect=ObjectIdentityTests.detect
    def test_native_neighbour_keeps_its_own_figure_title(self):
        objects=[self.obj('table',(80,150,520,350),role='table_body'),self.obj('figure_caption',(180,373,420,388),'Figure 2.1 Lower plot')]
        result=self.detect(objects,images=((80,150,520,350),(80,410,520,550)))
        self.assertEqual(len(result['14']['findings']),1)
    def test_small_vertical_offset_does_not_reverse_panel_order(self):
        boxes=[(80,225,230,320),(250,215,450,320)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(100,355,430,373),'Figure 2.1 Comparison')]
        lines=[self.line('(a) One',(100,327,205,340)),self.line('(b) Two',(280,327,400,340))]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_panels_can_be_lettered_by_column(self):
        boxes=[(60,200,270,310),(290,200,500,310),(60,340,270,450),(290,340,500,450)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(80,495,480,512),'Figure 2.1 Comparison')]
        lines=[self.line('('+letter+') Model',(b[0]+30,b[1]+5,b[2]-30,b[1]+20)) for b,letter in zip(boxes,'acbd')]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_labels_below_upper_panels_do_not_belong_to_lower_panels(self):
        boxes=[(60,200,270,310),(290,200,500,310),(60,340,270,450),(290,340,500,450)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(80,495,480,512),'Figure 2.1 Comparison')]
        lines=[self.line('('+letter+') Model',(b[0]+30,y,b[2]-30,y+13)) for b,letter,y in zip(boxes,'abcd',(325,325,455,455))]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_slight_overlap_title_keeps_above_orientation_vote(self):
        objects=[self.obj('figure',(80,100,520,270)),self.obj('figure',(180,310,420,550)),self.obj('figure_caption',(200,275,400,290),'Figure 1.1 Lower result'),
                 LayoutObject('figure',2,(100,120,500,350),'',600,800),LayoutObject('figure_caption',2,(200,100,400,121),'Figure 2.1 Above',600,800)]
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,()),PdfPage(2,600,800,())))
        result=detect_caption_rules(objects,[13],doc)
        self.assertEqual(len(result['13']['findings']),1)
        box=result['13']['findings'][0]['location']['bounding_rect']
        self.assertEqual([box[k] for k in ('x1','y1','x2','y2')],[80,100,520,270])

class AdditionalPhysicalEvidenceTests(unittest.TestCase):
    obj=ObjectIdentityTests.obj
    line=ObjectIdentityTests.line
    detect=ObjectIdentityTests.detect
    def test_offset_independent_panel_columns_do_not_cross_merge(self):
        boxes=[(60,200,240,300),(60,350,240,450),(270,120,450,220),(270,270,450,370)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(70,465,230,483),'Figure 2.1 Left column')]
        lines=[self.line('('+t+') Model',(b[0]+15,b[1]+10,b[2]-15,b[1]+25)) for b,t in zip(boxes,'abab')]
        result=self.detect(objects,lines)['13']['findings']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['location']['bounding_rect']['x1'],270)
    def test_pseudocode_supports_foreach_and_glued_do(self):
        lines=[self.line('算法2.4 流量过滤',(80,170,400,185)),self.line('Input: flows',(80,200,300,215)),self.line('2 foreach sample in Sdo',(80,230,400,245)),self.line('6 end',(80,270,140,285))]
        self.assertEqual(self.detect([self.obj('table',(80,195,520,345))],lines)['14']['findings'],[])
    def test_sequential_pseudocode_has_numbered_assignments(self):
        lines=[self.line('算法2.4 编码计算',(80,170,400,185)),self.line('1: 输入: X',(80,200,300,215)),self.line('3: Xemb ← Linear(X)',(80,230,400,245)),self.line('4: H ← Embed(Xemb)',(80,255,400,270)),self.line('5: Y ← Encode(H)',(80,280,400,295))]
        self.assertEqual(self.detect([self.obj('table',(80,195,520,345))],lines)['14']['findings'],[])
    def test_native_window_crossing_two_tables_and_their_caption_is_not_a_table(self):
        objects=[self.obj('table',(170,117,405,204),role='table_body'),self.obj('table_caption',(140,99,440,112),'Table 5.4 First',role='table_caption'),self.obj('table',(170,235,405,321),role='table_body'),self.obj('table_caption',(140,216,440,229),'Table 5.5 Second',role='table_caption')]
        self.assertEqual(self.detect(objects,tables=((175,183,403,237),))['14']['findings'],[])
    def test_separate_touching_figures_are_not_raster_tiles(self):
        boxes=((80,150,300,350),(300,150,520,350))
        objects=[self.obj('figure',b,role='image_body') for b in boxes]+[self.obj('figure_caption',(140,365,290,383),'Figure 2.1 Left')]
        self.assertEqual(len(self.detect(objects,images=boxes)['13']['findings']),1)
    def test_repeated_labels_use_complete_chains_instead_of_cross_group_links(self):
        boxes=[(60,250,240,350),(60,400,240,500),(270,100,450,200),(270,250,450,350)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(70,515,230,533),'Figure 2.1 Left column')]
        lines=[self.line('('+t+') Model',(b[0]+15,b[1]+10,b[2]-15,b[1]+25)) for b,t in zip(boxes,'abab')]
        self.assertEqual(len(self.detect(objects,lines)['13']['findings']),1)
    def test_top_panel_label_does_not_attach_below_the_previous_row(self):
        boxes=[(60,200,270,300),(290,200,500,300),(60,310,270,410),(290,315,500,410)]
        objects=[self.obj('figure',b) for b in boxes]+[self.obj('figure_caption',(80,440,480,455),'Figure 2.1 Grid')]
        lines=[self.line('('+t+') Model',(b[0]+25,y,b[2]-25,y+13)) for b,t,y in zip(boxes,'abcd',(205,205,305,305))]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_two_labelled_subtables_share_a_single_table_title(self):
        boxes=[(100,200,500,300),(100,330,500,430)]
        objects=[self.obj('table',b,role='table_body') for b in boxes]+[self.obj('table_caption',(130,160,470,175),'Table 2.1 Results')]
        lines=[self.line('(a) Accuracy',(210,182,390,195)),self.line('(b) Cost',(210,312,390,325))]
        self.assertEqual(self.detect(objects,lines)['14']['findings'],[])
    def test_table_component_inside_captioned_full_figure_is_not_separately_titled(self):
        objects=[self.obj('table',(300,150,500,260),role='table_body'),self.obj('figure_caption',(160,405,470,420),'Figure 2.1 System diagram')]
        self.assertEqual(self.detect(objects,images=((80,150,520,390),))['14']['findings'],[])
    def test_unambiguously_figure_captioned_vector_object_has_figure_identity(self):
        objects=[self.obj('table',(100,200,500,350),role='table_body'),self.obj('figure_caption',(180,365,440,380),'Figure 2.1 Bit layout')]
        self.assertEqual(self.detect(objects)['14']['findings'],[])
    def test_algorithm_without_input_header_requires_control_and_numbered_steps(self):
        lines=[self.line('算法2.4 Initialization',(80,170,450,185)),self.line('1 X ← 0',(80,200,300,215)),self.line('2 while True do',(80,230,400,245)),self.line('3 X ← NEXT(X)',(80,250,400,265)),self.line('4 end',(80,280,250,295))]
        self.assertEqual(self.detect([self.obj('table',(80,195,520,345))],lines)['14']['findings'],[])
    def test_native_table_in_an_adjacent_column_is_not_a_sliding_window(self):
        objects=[self.obj('table',(300,150,520,220),role='table_body'),self.obj('table_caption',(330,125,500,140),'Table 2.1 First',role='table_caption'),self.obj('table',(300,300,520,370),role='table_body'),self.obj('table_caption',(330,270,500,285),'Table 2.2 Second',role='table_caption')]
        self.assertEqual(len(self.detect(objects,tables=((60,180,302,340),))['14']['findings']),1)
    def test_tiled_raster_picture_has_one_caption(self):
        images=tuple((80+x*100,150+y*80,180+x*100,230+y*80) for y in range(3) for x in range(4))
        objects=[self.obj('figure',(85,150,475,375),role='image_body'),self.obj('figure_caption',(170,395,440,412),'Figure 2.1 Composite')]
        self.assertEqual(self.detect(objects,images=images)['13']['findings'],[])

class LegendIdentityTests(unittest.TestCase):
    def test_coloured_series_keys_next_to_plot_are_a_legend(self):
        table=LayoutObject('table',1,(90,100,490,124),'ART SMART SMART+C Sphinx',600,800,role='table_body')
        chart=LayoutObject('figure',1,(80,131,510,295),'',600,800,role='chart_body')
        caption=LayoutObject('figure_caption',1,(160,320,440,335),'Figure 5.6 Measurements',600,800)
        marks=((100,109,125,116),(200,109,225,116),(300,109,325,116))
        page=PdfPage(1,600,800,(PdfLine(1,'ART SMART SMART+C Sphinx',(130,105,480,118),600,800),),legend_marks=marks)
        doc=PdfDocument(Path('paper.pdf'),(page,))
        self.assertEqual(detect_caption_rules(prepare_caption_layout([table,chart,caption],doc),[14],doc)['14']['findings'],[])
    def test_numeric_table_data_is_not_removed_as_a_plot_legend(self):
        table=LayoutObject('table',1,(90,100,490,124),'Accuracy 0.95 Recall 0.90',600,800,role='table_body')
        chart=LayoutObject('figure',1,(80,131,510,295),'',600,800,role='chart_body')
        page=PdfPage(1,600,800,(),legend_marks=((100,109,125,116),(200,109,225,116)))
        doc=PdfDocument(Path('paper.pdf'),(page,))
        self.assertEqual(len(detect_caption_rules(prepare_caption_layout([table,chart],doc),[14],doc)['14']['findings']),1)

class GridWrapTests(unittest.TestCase):
    obj=ObjectIdentityTests.obj
    line=ObjectIdentityTests.line
    detect=ObjectIdentityTests.detect
    def test_three_column_grid_wraps_to_next_row_past_axis_ticks(self):
        boxes=[(60+x*150,200+y*140,195+x*150,320+y*140) for y in range(2) for x in range(3)]
        objects=[self.obj('figure',b,role='chart_body') for b in boxes]+[self.obj('figure_caption',(140,490,460,510),'Figure 2.1 Grid')]
        lines=[self.line('('+t+') Model',(b[0]+15,b[1]+3,b[2]-15,b[1]+16)) for b,t in zip(boxes,'abcdef')]
        lines.append(self.line('100',(70,329,95,337)))
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_narrow_centred_caption_belongs_to_all_three_panels(self):
        boxes=[(60+x*150,200,195+x*150,320) for x in range(3)]
        objects=[self.obj('figure',b,role='chart_body') for b in boxes]+[self.obj('figure_caption',(208,350,347,365),'Figure 2.1 Spectrum')]
        lines=[self.line('('+t+') Model',(b[0]+15,205,b[2]-15,218)) for b,t in zip(boxes,'abc')]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_native_window_through_two_plot_rows_and_caption_is_not_a_table(self):
        boxes=[(70+x*270,100+y*190,235+x*270,210+y*190) for y in range(2) for x in range(2)]
        objects=[self.obj('figure',b,role='chart_body') for b in boxes]+[self.obj('figure_caption',(230,250,375,270),'Figure 2.1 Two panels')]
        self.assertEqual(self.detect(objects,tables=((110,175,510,297),))['14']['findings'],[])
    def test_axis_tick_prefix_does_not_hide_a_subpanel_label(self):
        boxes=[(60+x*150,200,195+x*150,320) for x in range(3)]
        objects=[self.obj('figure',b,role='chart_body') for b in boxes]+[self.obj('figure_caption',(120,350,460,365),'Figure 2.1 Spectrum')]
        lines=[self.line('('+t+') Model' if t=='a' else '100.5('+t+') Model',(b[0]+10,205,b[2]-5,228)) for b,t in zip(boxes,'abc')]
        self.assertEqual(self.detect(objects,lines)['13']['findings'],[])
    def test_native_table_with_table_title_overrides_cloud_chart_identity(self):
        box=(100,150,500,260)
        objects=[self.obj('figure',box,role='chart_body'),self.obj('table_caption',(180,120,430,137),'Table 2.1 Measurements')]
        result=self.detect(objects,tables=(box,))
        self.assertEqual(result['13']['findings'],[])
        self.assertEqual(result['14']['findings'],[])
    def test_plot_caption_inside_a_native_rule_window_is_not_a_table_title(self):
        objects=[self.obj('figure',(70,200,530,350),role='chart_body'),self.obj('figure_caption',(150,360,450,376),'Figure 2.1 Measurements')]
        self.assertEqual(self.detect(objects,tables=((150,280,450,385),))['14']['findings'],[])
    def test_multiline_non_numeric_data_with_coloured_checks_is_a_table(self):
        table=self.obj('table',(90,100,490,140),'Algorithm Supports caching ART Yes Sphinx No',role='table_body')
        chart=self.obj('figure',(80,147,510,310),role='chart_body')
        caption=self.obj('figure_caption',(160,335,440,350),'Figure 5.6 Chart')
        lines=tuple(self.line(t,(110,y,470,y+12)) for t,y in zip(('Algorithm Supports caching','ART Yes','Sphinx No'),(101,115,129)))
        page=PdfPage(1,600,800,lines,legend_marks=((95,116,102,123),(95,130,102,137)))
        doc=PdfDocument(Path('paper.pdf'),(page,))
        self.assertEqual(len(detect_caption_rules(prepare_caption_layout([table,chart,caption],doc),[14],doc)['14']['findings']),1)

class PlotWindowIdentityTests(unittest.TestCase):
    obj=ObjectIdentityTests.obj
    line=ObjectIdentityTests.line
    detect=ObjectIdentityTests.detect
    def test_real_table_between_two_cloud_chart_edges_is_kept(self):
        objects=[self.obj('figure',(80,100,520,280),role='chart_body'),self.obj('figure',(80,380,520,550),role='chart_body'),
                 self.obj('figure_caption',(160,80,440,95),'Figure 2.1 Upper'),self.obj('figure_caption',(160,565,440,580),'Figure 2.2 Lower')]
        lines=[self.line(t,(x,y,x+100,y+15)) for y,a,b in ((295,'Method','Accuracy'),(325,'A','0.95'),(355,'B','0.90')) for x,t in ((100,a),(340,b))]
        self.assertEqual(len(self.detect(objects,lines,tables=((80,270,520,390),))['14']['findings']),1)
    def test_plot_axis_window_with_an_interior_side_caption_is_not_a_table(self):
        objects=[self.obj('figure',(340,100,510,210),role='chart_body'),self.obj('figure',(340,291,510,400),role='chart_body'),
                 self.obj('figure_caption',(190,250,420,277),'Figure 2.1 Upper')]
        self.assertEqual(self.detect(objects,tables=((363,179,507,296),))['14']['findings'],[])
    def test_false_native_window_cannot_capture_the_next_plot_panel_label(self):
        boxes=[(80+x*145,220+y*105,225+x*145,320+y*105) for y in range(2) for x in range(3)]
        boxes+= [(80+x*145,490+y*105,225+x*145,590+y*105) for y in range(2) for x in range(3)]
        boxes[8]=(381,501,524,591)
        objects=[self.obj('figure',b,role='chart_body') for b in boxes]+[self.obj('figure_caption',(100,438,500,466),'Figure 2.1 Upper'),self.obj('figure_caption',(180,704,420,727),'Figure 2.2 Lower')]
        lines=[self.line('('+letter+') Model',(b[0]+20,b[1]+3,b[2]-10,b[1]+16)) for letter,b in zip('abcdefabcdef',boxes)]
        self.assertEqual(self.detect(objects,lines,tables=((395,395,522,505),))['13']['findings'],[])

class FinalFullScanRegressions(unittest.TestCase):
    line=ReferenceContextTests.line
    def test_subtable_references_use_the_parent_table_number(self):
        lines=(self.line('如表4.3a和表4.3b可知。'),self.line('表4.3 消融实验结果',(180,400,460,415)))
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,lines),))
        self.assertEqual(detect_rules(build_index(doc),[16])['16']['findings'],[])
    def test_split_subtable_reference_uses_parent(self):
        lines=(self.line('See Table',(60,100,120,115)),self.line('4.3b for cost.',(125,100,300,115)),self.line('Table 4.3 Results',(180,400,460,415)))
        doc=PdfDocument(Path('paper.pdf'),(PdfPage(1,600,800,merge_reference_fragments(lines)),))
        self.assertEqual(detect_rules(build_index(doc),[16])['16']['findings'],[])
    def test_bare_prefix_variable_is_not_a_partial_table_reference(self):
        from pdf_rules.numbering import TABLE_REFERENCE
        self.assertEqual(list(TABLE_REFERENCE.finditer('Lookup Table T2D variable')),[])
    def form(self,extra=()):
        header=PdfLine(1,'姓名 学号 所在学科 指导教师 答辩日期 答辩地点 论文题目',(105,90,180,528),842,595,source='mineru',role='table_body')
        committee=PdfLine(1,'答辩委员会 工作职务 姓名 职称 工作单位 签名 主席 委员 委员 委员 秘书',(428,79,719,529),842,595,source='mineru',role='table_body')
        return PdfPage(1,842,595,(header,committee,*extra),unreadable=True)
    def test_complete_rotated_degree_form_schema_survives_missing_title(self):
        from pdf_rules.layout_context import nonresearch_page
        self.assertTrue(nonresearch_page(self.form()))
    def test_research_reference_outside_form_schema_is_preserved(self):
        from pdf_rules.layout_context import nonresearch_page
        line=PdfLine(1,'实验结果见图9.9和附录Z。',(300,80,320,540),842,595)
        self.assertFalse(nonresearch_page(self.form((line,))))

class RotatedAdministrativePositionTests(unittest.TestCase):
    def page(self,extra=(),rotation=180):
        title=PdfLine(1,'学位论文原创性声明',(130,700,450,724),600,800,source='mineru',role='title')
        return PdfPage(1,600,800,(title,*extra),unreadable=True,display_rotation=rotation)
    def test_viewer_top_admin_title_is_not_required_at_canonical_top(self):
        from pdf_rules.layout_context import nonresearch_page
        self.assertTrue(nonresearch_page(self.page()))
    def test_actual_bottom_admin_words_are_not_a_top_title(self):
        from pdf_rules.layout_context import nonresearch_page
        self.assertFalse(nonresearch_page(self.page(rotation=0)))
    def test_research_reference_on_rotated_page_prevents_title_exclusion(self):
        from pdf_rules.layout_context import nonresearch_page
        line=PdfLine(1,'实验比较见图9.9和附录Z。',(130,550,450,575),600,800)
        self.assertFalse(nonresearch_page(self.page((line,))))

class RotatedCoverReferenceTests(unittest.TestCase):
    def test_rotated_cover_title_does_not_hide_body_references(self):
        from pdf_rules.layout_context import nonresearch_page
        lines=(PdfLine(1,'硕士学位论文',(130,700,450,724),600,800),PdfLine(1,'作者 张某',(130,650,450,675),600,800),PdfLine(1,'实验比较见图9.9和附录Z。',(130,550,450,575),600,800))
        self.assertFalse(nonresearch_page(PdfPage(1,600,800,lines,display_rotation=180)))

class NativeImagePrimitiveTests(unittest.TestCase):
    def test_stretched_white_filler_is_not_a_standalone_figure(self):
        import io,tempfile,pymupdf
        from PIL import Image
        from pdf_rules.pdf_extract import extract_pdf
        white=io.BytesIO();Image.new('RGB',(1,20),'white').save(white,format='PNG')
        picture=io.BytesIO();Image.new('RGB',(60,40),'blue').save(picture,format='PNG')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'paper.pdf'
            pdf=pymupdf.open();page=pdf.new_page(width=600,height=800)
            page.insert_text((60,100),'Chapter 3 Experiments')
            page.insert_image((80,150,500,190),stream=white.getvalue(),keep_proportion=False)
            page.insert_image((100,220,400,420),stream=picture.getvalue())
            pdf.save(path);pdf.close()
            images=extract_pdf(path).pages[0].images
            self.assertEqual(len(images),1)
            self.assertGreater(images[0][1],200)

if __name__=='__main__':unittest.main()
