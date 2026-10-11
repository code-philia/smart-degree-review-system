"""Regressions for declared figure namespaces and positively identified text."""
from importlib import import_module, util
from pathlib import Path
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfPage, PdfLine


def obj(kind, box, text='', role='chart_body', **kw):
    return LayoutObject(kind, 1, box, text, 600, 840, role, **kw)


def line(text, box):
    return PdfLine(1, text, box, 600, 840)


def repair(objects, lines=(), images=(), graphics=()):
    assert util.find_spec('pdf_rules.figure_identity_repair') is not None, 'Figure identity repair is not implemented'
    document = PdfDocument(Path('layout-only-fixture.pdf'), (PdfPage(1,600,840,tuple(lines),images=tuple(images),graphics=tuple(graphics)),))
    fixed = import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,document)
    return fixed, detect_caption_rules(fixed,[13,14],document)


def stacked_panels(with_title=True):
    objects=[obj('figure',(155.28,99.18,453.24,220.74),role='image_body'),
             obj('figure',(215.11,240.26,392.4,329.52),role='image_body')]
    if with_title:
        objects.append(obj('figure_caption',(84.04,355.38,523.26,428.46),
                           'Figure 3.8 Region sampling. (a) Sliding window. (b) Class probability. (c) Patches.',role='image_caption'))
    lines=[line('(a)',(298.08,226.62,311.32,242.76)),
           line('(b)',(210.12,335.34,224.08,351.48)),
           line('(c)',(383.19,335.34,397.08,351.48))]
    return objects,lines


def test_stacked_subpanels_share_their_explicit_total_title():
    objects,lines=stacked_panels()
    fixed,result=repair(objects,lines)
    assert result['13']['findings']==[]
    figures=[o for o in fixed if o.kind=='figure']
    assert len(figures)==1 and len(figures[0].panel_boxes)==2


def test_main_figure_losing_its_title_still_reports_missing_caption():
    objects,lines=stacked_panels(False)
    _,result=repair(objects,lines)
    assert result['13']['findings']


def test_independent_chart_beside_a_captioned_chart_is_retained():
    objects=[obj('figure',(70,100,270,220)),obj('figure',(330,100,530,220)),
             obj('figure_caption',(330,230,530,245),'Figure 2.1 Right experiment')]
    fixed,result=repair(objects)
    assert len([o for o in fixed if o.kind=='figure'])==2
    assert len(result['13']['findings'])==1
    assert result['13']['findings'][0]['location']['bounding_rect']['x1']==70


def test_shared_row_labels_cover_all_curve_panels_in_each_band():
    objects=[obj('figure',(x,y,x+130,y+80)) for y in (100,190,305,395) for x in (100,240,380)]
    objects.append(obj('figure_caption',(90,505,525,523),'Figure 5.14 (a) Baseline. (b) Improved model.'))
    lines=[line('(a) Baseline',(160,278,455,291)),line('(b) Improved model',(160,485,455,498))]
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_dense_chart_stack_uses_the_declared_table_namespace():
    objects=[obj('figure',(174,241,431,312)),obj('figure',(174,322,431,396)),obj('figure',(174,406,431,475)),
             obj('table_caption',(186,484,421,512),'Table 4.9 Linear schedule applied in BlockShuffle.')]
    fixed,result=repair(objects)
    assert not any(o.kind=='figure' for o in fixed)
    assert len([o for o in fixed if o.kind=='table'])==1
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_a_dedicated_table_title_reclassifies_one_chart():
    objects=[obj('figure',(188,101,420,275)),obj('table_caption',(171,285,436,313),'Table 4.11 Comparisons of training loss.')]
    fixed,result=repair(objects)
    assert [o.kind for o in fixed].count('table')==1
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_nearby_table_title_does_not_claim_an_independent_figure():
    objects=[obj('figure',(330,180,530,300)),obj('table',(70,180,270,300)),
             obj('table_caption',(70,140,270,160),'Table 4.2 Accuracy comparison')]
    fixed,result=repair(objects)
    assert len([o for o in fixed if o.kind=='figure'])==1
    assert len(result['13']['findings'])==1


def test_sample_photos_belong_to_declared_result_table_cells():
    objects=[obj('table',(80,160,180,225)),obj('figure',(190,165,270,240),role='image_body'),
             obj('table',(290,160,390,225)),obj('figure',(400,165,480,240),role='image_body'),
             obj('table_caption',(70,100,515,125),'Table 4.4 Comparing classification methods on image datasets.')]
    _,result=repair(objects)
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_inline_formula_bitmap_is_text_not_a_figure():
    objects=[obj('figure',(225,330,238,343),role='native_figure')]
    lines=[PdfLine(1,'The state is h = f(x) after this transformation.',(80,328,520,345),600,840,
                   text_regions=((13,14,(225,330,238,343)),))]
    fixed,result=repair(objects,lines)
    assert not any(o.kind=='figure' for o in fixed)
    assert result['13']['findings']==[]


def prompt_fixture(introduction):
    objects=[obj('figure',(80,200,520,450),role='image_body')]
    contents=['Prompt for Masked Text Prediction','You are an expert in text generation.',
              'Your task is to generate a new sentence.','1. Preserve the preceding context.',
              '2. Return the output as JSON.','Now please return the generated content.']
    lines=[line(introduction,(80,170,520,188))]
    lines += [line(s,(95,215+i*33,505,230+i*33)) for i,s in enumerate(contents)]
    return objects,lines


def test_explicitly_introduced_prompt_template_is_a_text_block():
    objects,lines=prompt_fixture('用于再生的提示模板如下：')
    fixed,result=repair(objects,lines)
    assert not any(o.kind=='figure' for o in fixed)
    assert result['13']['findings']==[]


def test_body_text_screenshot_declared_as_an_academic_figure_remains_reported():
    objects,lines=prompt_fixture('图3.4展示了提示词界面的完整截图。')
    _,result=repair(objects,lines)
    assert len(result['13']['findings'])==1


def test_dense_english_text_without_prompt_declaration_is_not_exempt():
    objects,lines=prompt_fixture('The following screenshot illustrates the user interface.')
    _,result=repair(objects,lines)
    assert len(result['13']['findings'])==1


def test_numbered_math_expression_preserves_the_equation_namespace():
    objects=[obj('figure',(220,300,440,333),role='image_body')]
    lines=[line('p(B|A) = p(A|B)p(B) / p(A)',(225,307,425,321)),line('(3.13)',(500,307,535,321))]
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_a_graph_with_math_axis_labels_is_still_a_figure():
    objects=[obj('figure',(90,200,500,460),role='chart_body')]
    lines=[line('x',(285,440,295,456)),line('p(x)',(90,280,120,295))]
    _,result=repair(objects,lines,graphics=[(100,220,480,420)])
    assert len(result['13']['findings'])==1


def test_prior_captioned_table_does_not_block_later_declared_chart_stack():
    objects=[obj('table',(80,150,220,205)),obj('table_caption',(80,105,220,135),'Table 4.8 Existing data'),
             obj('figure',(174,241,431,312)),obj('figure',(174,322,431,396)),obj('figure',(174,406,431,475)),
             obj('table_caption',(186,484,421,512),'Table 4.9 Linear schedule applied in BlockShuffle.')]
    _,result=repair(objects)
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_explicitly_designed_aspects_are_quoted_instruction_text():
    objects,lines=prompt_fixture('手动设计了以下五个视角：')
    lines[1]=line('Aspect I: Analyze the key information.',(95,215,505,230))
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_simulation_response_follows_a_structured_response_instruction():
    objects,lines=prompt_fixture('Step 4: Provide a response in the following JSON format:')
    lines[1]=line('Step 1: As a traveler, I choose to rest.',(95,215,505,230))
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_paragraph_edge_collision_without_glyph_proof_is_retained():
    objects=[obj('figure',(49,574,79,604),role='native_figure')]
    lines=[line('上传至服务器，用于在服务器端重建真实建筑的三维模型。',(70,585,382,597))]
    _,result=repair(objects,lines)
    assert len(result['13']['findings'])==1


def test_image_result_table_keeps_its_lower_cells_before_the_next_title():
    objects=[obj('table',(80,160,180,225)),obj('figure',(190,160,270,240),role='image_body'),
             obj('table',(80,270,180,336)),obj('figure',(190,270,270,345),role='image_body'),
             obj('table_caption',(70,100,280,125),'Table 4.4 Comparing image classification results'),
             obj('table_caption',(70,370,280,395),'Table 4.5 Comparing other classification results'),
             obj('table',(80,430,180,500)),obj('figure',(190,430,270,510),role='image_body')]
    _,result=repair(objects)
    assert result['13']['findings']==[] and result['14']['findings']==[]


def test_three_independent_charts_cannot_share_a_narrow_middle_title():
    objects=[obj('figure',(x,100,x+120,220)) for x in (80,210,340)]
    objects.append(obj('figure_caption',(175,230,365,245),'Figure 2.1 Experimental results'))
    _,result=repair(objects)
    assert len(result['13']['findings'])==2


def test_rotated_labelled_subpanels_share_the_vertical_total_title():
    def turn(box):
        return (600-box[3],box[0],600-box[1],box[2])
    original,lines=stacked_panels()
    objects=[obj(o.kind,turn(o.bbox),o.text,o.role) for o in original]
    native=[line(l.text,turn(l.bbox)) for l in lines]
    _,result=repair(objects,native)
    assert result['13']['findings']==[]


def test_vector_subpanel_named_by_total_title_is_recovered_before_grouping():
    objects=[obj('figure',(100,100,470,220),role='image_body'),
             obj('figure_caption',(100,430,470,450),'Figure 3.27 (a) Hit rate. (b) Accuracy.')]
    lines=[line('(a) Hit rate',(200,230,350,245)),line('(b) Accuracy',(200,395,350,410))]
    fixed,result=repair(objects,lines,graphics=[(100,270,470,390)])
    assert result['13']['findings']==[]
    assert len([o for o in fixed if o.kind=='figure'])==1


def cross_page_grid(tmp_path, title=True, separated=False):
    import pymupdf
    source=tmp_path/'grid.pdf'
    rows=[(80,400,520,530),(80,550 if separated else 531,520,681 if separated else 661)]
    last=(80,100,520,220)
    with pymupdf.open() as pdf:
        for index,boxes in enumerate([rows,[last]]):
            page=pdf.new_page(width=600,height=840)
            for row in boxes:
                for x in (90,235,380):
                    page.draw_rect(pymupdf.Rect(x,row[1]+10,x+125,row[3]-10),color=(0,0,0),width=1)
        pdf.save(source)
    first=LayoutObject('figure',1,(80,400,520,rows[-1][3]),'',600,840,'continuous_chart_panels')
    second=LayoutObject('figure',2,last,'',600,840,'chart_body',source_id='parsed-last-panel')
    objects=[first,second]
    if title:objects.append(LayoutObject('figure_caption',2,(100,230,500,250),'Figure 5.5 Comparing distributions',600,840))
    doc=PdfDocument(source,(PdfPage(1,600,840,(),images=tuple(rows)),PdfPage(2,600,840,(),images=(last,))))
    return objects,doc


def test_cross_page_contiguous_plot_grid_uses_the_last_part_title(tmp_path):
    objects,doc=cross_page_grid(tmp_path)
    fixed=import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,doc)
    assert detect_caption_rules(fixed,[13],doc)['13']['findings']==[]
    part=next(o for o in fixed if o.page_number==1)
    assert part.kind=='text' and part.parent_id=='parsed-last-panel'


def test_cross_page_grid_missing_its_main_title_is_still_reported(tmp_path):
    objects,doc=cross_page_grid(tmp_path,title=False)
    fixed=import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,doc)
    assert detect_caption_rules(fixed,[13],doc)['13']['findings']


def test_independent_plot_grid_before_a_titled_next_page_is_not_claimed(tmp_path):
    objects,doc=cross_page_grid(tmp_path,separated=True)
    fixed=import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,doc)
    assert len(detect_caption_rules(fixed,[13],doc)['13']['findings'])==1


def test_glyph_carrier_at_algorithm_heading_belongs_to_the_algorithm():
    objects=[obj('figure',(392,92,418,118),role='native_figure')]
    lines=[line('算法3.1 实时飞行高度决策算法',(82,104,391,117)),
           line('Data: a set of images and trained models',(95,122,492,135))]
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_pale_native_figure_with_gray_242_structure_remains_reported(tmp_path):
    import pymupdf
    source=tmp_path/'pale-plot.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        page.draw_rect(pymupdf.Rect(110,210,145,245),color=(242/255,)*3,width=2)
        pdf.save(source)
    box=(100,200,150,250)
    objects=[obj('figure',box,role='native_figure')]
    doc=PdfDocument(source,(PdfPage(1,600,840,(),images=(box,)),))
    fixed=import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,doc)
    assert len(detect_caption_rules(fixed,[13],doc)['13']['findings'])==1


def test_short_independent_native_figure_touching_body_is_retained():
    objects=[obj('figure',(290,328,420,350),role='native_figure')]
    native=PdfLine(1,'Body before the independent plot and then after the plot.',(80,330,520,344),600,840,
                   text_regions=((0,12,(80,330,280,344)),(12,30,(425,330,520,344))))
    _,result=repair(objects,[native])
    assert len(result['13']['findings'])==1


def test_commutative_mapping_is_part_of_a_mathematical_statement():
    objects=[obj('figure',(180,250,430,360),role='image_body')]
    lines=[line('下面的交换图成立：',(80,225,500,242)),
           line('R    GRN',(190,260,420,274)),line('𝜙    𝜎R',(200,290,410,305)),
           line('R    GRN',(190,325,420,339)),line('𝜙',(285,340,300,355))]
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]


def test_explicitly_numbered_code_listing_keeps_its_code_namespace():
    objects=[obj('figure',(80,200,520,450),role='image_body')]
    lines=[line('代码C.1 OpenCLIP特征提取实现',(180,470,470,490))]
    lines += [line(t,(95,210+i*30,510,230+i*30)) for i,t in enumerate([
        '88 return hooked ViT block outputs.', '89 Dict[str, Tensor]', '90 self.clear()',
        '91 self.model.eval()', '92 output = self.model.encode_image(images)', '93 return output, dict(self.features)'])]
    _,result=repair(objects,lines)
    assert result['13']['findings']==[]



def translated_table_row_boundary_fixture(body=''):
    panels=((80,338,270,424),(310,338,500,424),(195,469,385,555))
    upper=obj('table',(80,306,500,424),role='table_body',panel_boxes=panels[:2])
    lower=obj('table',panels[2],role='table_body')
    title=obj('table_caption',(195,285,385,300),'表4.4 不同条件下的性能比较')
    lines=[]
    for b,t in zip(panels,'abc'):
        x=(b[0]+b[2])/2
        lines += [line(f'({t}) 条件比较',(x-30,b[1]-32,x+30,b[1]-19)),
                  line(f'({t}) Condition comparison',(x-50,b[1]-17,x+50,b[1]-5))]
    if body:lines.append(line(body,(80,427,500,439)))
    return [upper,lower,title],lines


def test_short_body_paragraph_preserves_separate_translated_lower_table():
    objects,lines=translated_table_row_boundary_fixture('The following results concern a separate experiment.')
    fixed,result=repair(objects,lines)
    assert len([o for o in fixed if o.kind=='table'])==2
    assert len(result['14']['findings'])==1


def test_translated_table_rows_without_intervening_prose_keep_the_common_title():
    objects,lines=translated_table_row_boundary_fixture()
    fixed,result=repair(objects,lines)
    assert len([o for o in fixed if o.kind=='table'])==1
    assert result['14']['findings']==[]


def test_short_single_column_body_sentence_is_an_ownership_boundary():
    objects,lines=translated_table_row_boundary_fixture()
    lines.append(line('A new trial starts.',(195,427,385,439)))
    fixed,result=repair(objects,lines)
    assert len([o for o in fixed if o.kind=='table'])==2
    assert len(result['14']['findings'])==1



def test_title_owned_by_an_independent_nearer_table_keeps_the_untitled_figure():
    objects=[obj('table',(80,200,520,350),role='table_body'),
             obj('table_caption',(170,180,430,194),'Table 8.2 Results'),
             obj('figure',(80,95,520,160),role='image_body')]
    fixed,result=repair(objects)
    assert len([o for o in fixed if o.kind=='figure'])==1
    assert len(result['13']['findings'])==1
    assert result['14']['findings']==[]


def test_internal_panel_letters_cannot_claim_an_external_thin_chart(tmp_path):
    import pymupdf
    source=tmp_path/'independent-thin-chart.pdf'
    with pymupdf.open() as pdf:
        page=pdf.new_page(width=600,height=840)
        page.draw_line((145,188),(445,188),color=(0,0,0))
        for dy,color in [(0,(1,.4,.1)),(6,(.1,.5,1))]:
            page.draw_polyline([(155,184-dy),(210,176-dy),(310,181-dy),(430,169-dy)],color=color)
        pdf.save(source)
    objects=[obj('figure',(100,205,500,560),role='chart_body'),
             obj('figure',(145,160,445,190),role='native_figure'),
             obj('figure_caption',(210,585,390,600),'Figure 9.9 Comparison')]
    lines=[line('(a) First',(120,355,230,368)),line('(b) Second',(320,355,430,368))]
    doc=PdfDocument(source,(PdfPage(1,600,840,tuple(lines)),))
    fixed=import_module('pdf_rules.figure_identity_repair').repair_figure_identity(objects,doc)
    result=detect_caption_rules(fixed,[13],doc)
    assert len([o for o in fixed if o.kind=='figure'])==2
    assert len(result['13']['findings'])==1
    assert result['13']['findings'][0]['location']['bounding_rect']['y1']==160


def test_table_title_between_legend_strip_and_captioned_chart_is_not_exclusive():
    objects=[obj('figure',(100,205,500,560),role='chart_body'),
             obj('figure',(145,170,445,190),role='native_figure'),
             obj('figure_caption',(210,585,390,600),'Figure 9.9 Comparison'),
             obj('table_caption',(140,191,460,204),'Table 9.3 A different experiment')]
    lines=[line('(a) First',(120,355,230,368)),line('(b) Second',(320,355,430,368))]
    fixed,result=repair(objects,lines)
    assert len([o for o in fixed if o.kind=='figure'])==2
    assert len(result['13']['findings'])==1
