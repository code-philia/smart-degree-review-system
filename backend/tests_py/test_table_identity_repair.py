"""Physical table identity repair must retain genuinely untitled independent tables."""
from pathlib import Path
import importlib
import pytest
from pdf_rules.caption_rules import detect_caption_rules
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.model import PdfDocument, PdfLine, PdfPage

W, H = 600, 800
def obj(kind, box, text="", page=1, role="", **kwargs):
    return LayoutObject(kind, page, box, text, W, H, role, **kwargs)
def line(text, box, page=1, **kwargs):
    return PdfLine(page, text, box, W, H, **kwargs)
def doc(*lines):
    numbers = sorted({l.page_number for l in lines} or {1})
    return PdfDocument(Path("unrelated-name.pdf"), tuple(
        PdfPage(n, W, H, tuple(l for l in lines if l.page_number == n)) for n in numbers))
def repair(objects, document):
    try:
        module = importlib.import_module("pdf_rules.table_identity_repair")
    except ModuleNotFoundError:
        pytest.fail("The physical identity repair is not implemented")
    return module.repair_table_identity(objects, document)
def alarms(objects, document):
    return detect_caption_rules(objects, (14,), document)["14"]["findings"]
def cells(box, page=1, cols=(100, 260), names=("CPU", "GPU")):
    return [line(value, (x, y, x+40, y+10), page)
            for y, name in zip(range(int(box[1]+8), int(box[3]-4), 20), names)
            for x, value in zip(cols, (name, "符号的含义与定义" if name in "αβγδε" else "24", "0.5"))]

def test_native_fragment_of_explicit_figure_is_not_a_second_table():
    graphic = obj("figure", (85, 240, 295, 470), parent_id="left", parent_bbox=(85,240,295,470))
    caption = obj("figure_caption", (81, 100, 297, 239), "图5.4 模型欺诈易感率", parent_id="left", parent_bbox=graphic.bbox)
    fragment = obj("table", (87, 394, 294, 472), role="native_table")
    repaired = repair([graphic, caption, fragment], doc(*cells(fragment.bbox)))
    assert alarms(repaired, doc()) == []
    assert sum(o.kind == "figure" for o in repaired) == 1

def test_nearby_captioned_figure_cannot_consume_an_independent_table():
    objects = [obj("figure", (80,100,260,300)),
               obj("figure_caption", (80,310,260,330), "图1.1 散点图"),
               obj("table", (310,100,520,300), role="table_body")]
    document = doc(*cells(objects[-1].bbox, cols=(330,450)))
    assert len(alarms(repair(objects, document), document)) == 1

def test_last_average_row_inside_titled_table_is_one_object():
    whole = obj("table", (83,130,524,377), "Attack CA ASR", role="table_body")
    fragment = obj("table", (85,357,524,379), role="native_table")
    caption = obj("table_caption", (128,109,481,125), "表5.1 防御结果")
    repaired = repair([whole, fragment, caption], doc(*cells(whole.bbox)))
    assert len([o for o in repaired if o.kind == "table"]) == 1
    assert alarms(repaired, doc()) == []
    assert repaired[0].bbox[3] >= 379

def test_common_main_title_owns_two_explicit_panels():
    first = obj("table", (80,130,280,300), "(a) Accuracy")
    second = obj("table", (320,130,520,300), "(b) Latency")
    caption = obj("table_caption", (150,320,450,335), "Table 2.1 Results: (a) accuracy and (b) latency")
    document = doc(line("(a) Accuracy",(120,125,220,140)), line("(b) Latency",(360,125,460,140)),
                   *cells(first.bbox), *cells(second.bbox, cols=(340,450)))
    repaired = repair([first, second, caption], document)
    assert len([o for o in repaired if o.kind == "table"]) == 1
    assert alarms(repaired, document) == []

def test_two_independent_tables_never_share_one_title_without_panel_evidence():
    first, second = obj("table",(80,150,260,290)), obj("table",(320,150,520,290))
    caption = obj("table_caption",(80,120,260,135),"Table 2.1 Scores")
    document = doc(*cells(first.bbox), *cells(second.bbox,cols=(340,450)))
    repaired = repair([first, second, caption], document)
    assert len([o for o in repaired if o.kind == "table"]) == 2
    assert len(alarms(repaired, document)) == 1

def test_input_only_algorithm_fragment_retains_declared_non_table_identity():
    target = obj("table",(80,720,520,745),"Input: dataset",role="native_table")
    document = doc(line("算法4.2 模型更新",(80,695,300,710)),
                   line("Input: dataset",(90,725,240,737)))
    repaired = repair([target], document)
    assert not any(o.kind == "table" for o in repaired)
    assert any(o.bbox == target.bbox for o in repaired)

def test_algorithm_word_in_an_experimental_table_is_not_a_declaration():
    target = obj("table",(80,200,520,400),"Algorithm Runtime\nInput 20\nOutput 30",role="table_body")
    document = doc(line("Algorithm",(90,210,150,220)), *cells(target.bbox))
    assert len(alarms(repair([target], document), document)) == 1

@pytest.mark.parametrize("title,body",[
    ("Listing 2: exception handling", "try { execute(); } catch (IOException e) { return; }"),
    ("代码列表 A.2 检索式", 'TI=(network OR learning) AND TS=("deep learning")'),
    ("Prompt Template", "Role: assistant\nContext: question\nConstraints: answer only\nOutput: result"),
    ("ε-GAP-2CSP 定义", "Input: variables and constraints\nParameters: ε\nYES: satisfiable\nNO: unsatisfiable"),
])
def test_explicit_program_prompt_and_definition_frames_are_not_data_tables(title, body):
    target = obj("table",(80,150,520,350),body,role="table_body")
    document = doc(line(title,(80,125,400,142),role="title"),
                   line(body,(90,160,500,330)))
    assert alarms(repair([target], document), document) == []

def test_single_configuration_table_accepts_its_exclusive_section_title():
    first = obj("table",(83,209,524,296),"硬件 配置 CPU Xeon GPU RTX 4090",role="table_body")
    second = obj("table",(83,382,524,456),"软件 版本 Pytorch 2.3 Python 3.10",role="table_body")
    document = doc(line("A.1 硬件配置",(85,169,180,185),font_size=14),
                   *cells(first.bbox), line("A.2 软件工具",(85,343,180,359),font_size=14),
                   *cells(second.bbox,names=("Pytorch","Python")))
    repaired = repair([first,second],document)
    assert alarms(repaired,document) == []
    assert {o.text for o in repaired if o.kind == "table_caption"} == {"A.1 硬件配置","A.2 软件工具"}

def test_section_title_with_intervening_body_cannot_replace_a_table_title():
    target = obj("table",(83,209,524,296),role="table_body")
    document = doc(line("A.1 硬件配置",(85,140,180,156),font_size=14),
                   line("以下介绍硬件的选择原则。",(85,170,400,184)),*cells(target.bbox))
    assert len(alarms(repair([target],document),document)) == 1

def test_section_title_over_two_independent_tables_cannot_replace_both_titles():
    a,b=obj("table",(80,200,270,350)),obj("table",(320,200,520,350))
    document=doc(line("A.1 硬件配置",(80,160,180,175),font_size=14),*cells(a.bbox),*cells(b.bbox,cols=(340,450)))
    assert len(alarms(repair([a,b],document),document)) == 2

def test_glossary_scope_continues_until_research_chapter_and_preserves_research_table():
    a,b,c=obj("table",(80,150,520,730)),obj("table",(80,100,520,500),page=2),obj("table",(80,150,520,350),page=3)
    document=doc(line("主要符号对照表",(200,110,400,130),font_size=16),
                 *cells(a.bbox,names=("α","β")), *cells(b.bbox,page=2,names=("γ","δ","ε")),
                 line("第1章 绪论",(200,100,400,120),page=3,font_size=16),*cells(c.bbox,page=3))
    repaired=repair([a,b,c],document)
    assert [o.page_number for o in repaired if o.kind=="table"] == [3]
    assert len(alarms(repaired,document)) == 1

def test_textual_three_column_table_continues_across_page_boundary():
    a,b=obj("table",(80,150,520,730)),obj("table",(80,100,520,350),page=2)
    caption=obj("table_caption",(150,120,450,135),"Table 6.1 System properties")
    document=doc(*cells(a.bbox,cols=(100,260,420),names=("GUI","Storage","Runtime","Language")),
                 *cells(b.bbox,page=2,cols=(100,260,420),names=("Hosting","Platform","License")))
    repaired=repair([a,b,caption],document)
    assert alarms(repaired,document)==[]

def test_cross_page_table_with_different_column_structure_remains_independent():
    a,b=obj("table",(80,150,520,730)),obj("table",(80,100,520,350),page=2)
    caption=obj("table_caption",(150,120,450,135),"Table 6.1 Properties")
    document=doc(*cells(a.bbox,cols=(100,260,420),names=("A","B","C")),
                 *cells(b.bbox,page=2,cols=(100,420),names=("D","E","F")))
    assert len(alarms(repair([a,b,caption],document),document))==1

def test_intervening_paragraph_prevents_cross_page_table_continuation():
    a,b=obj("table",(80,150,520,730)),obj("table",(80,100,520,350),page=2)
    caption=obj("table_caption",(150,120,450,135),"Table 6.1 Properties")
    document=doc(*cells(a.bbox,cols=(100,260,420),names=("A","B","C")),
                 line("Now we describe another independent experiment.",(80,740,520,756)),
                 *cells(b.bbox,page=2,cols=(100,260,420),names=("D","E","F")))
    assert len(alarms(repair([a,b,caption],document),document))==1

def test_true_untitled_table_is_preserved_with_all_source_evidence():
    target=obj("table",(80,250,520,500),"Method A B",role="table_body",source_id="original",parent_id="object")
    document=doc(*cells(target.bbox))
    repaired=repair([target],document)
    assert repaired == [target]
    assert len(alarms(repaired,document))==1


def test_panel_grid_with_one_main_title_and_distinct_parser_parents():
    a,b=obj("table",(80,160,260,280),parent_id="a"),obj("table",(320,160,520,280),parent_id="b")
    caption=obj("table_caption",(100,120,500,145),"Table 4.1 Comparison of methods")
    document=doc(line("(a) First dataset",(100,148,220,158)),line("(b) Second dataset",(340,148,480,158)),
                 *cells(a.bbox),*cells(b.bbox,cols=(340,450)))
    repaired=repair([a,b,caption],document)
    assert len([o for o in repaired if o.kind=="table"])==1
    assert alarms(repaired,document)==[]

def test_glossary_chapter_group_heading_does_not_end_the_glossary():
    a,b=obj("table",(80,200,520,730)),obj("table",(80,200,520,500),page=2)
    document=doc(line("符号对照表",(200,120,400,140)),*cells(a.bbox,names=("α","β")),
                 line("第五章：规划方法的符号",(100,160,400,180),page=2),*cells(b.bbox,page=2,names=("γ","δ","ε")))
    assert alarms(repair([a,b],document),document)==[]

def test_bold_narrative_title_still_declares_one_table():
    target=obj("table",(80,150,520,350),role="table_body")
    document=doc(line("表5.12 展示了不同模型在基准上的性能。",(80,115,500,130),bold=True,font_size=10.5),
                 line("该表中的数值代表交并比指标。",(80,130,500,142),bold=True,font_size=10.5),
                 *cells(target.bbox))
    assert alarms(repair([target],document),document)==[]

def test_normal_body_table_reference_is_not_recovered_as_a_title():
    target=obj("table",(80,150,520,350),role="table_body")
    document=doc(line("表5.12 展示了不同模型在基准上的性能。",(80,115,500,130),font_size=12),
                 *cells(target.bbox))
    assert len(alarms(repair([target],document),document))==1

def test_short_sideways_continued_table_title_uses_baseline_direction():
    target=obj("table",(120,100,500,700),role="table_body")
    document=doc(line("续表2.2",(104,390,117,430),direction=(0,-1),bold=True),
                 *cells(target.bbox))
    assert alarms(repair([target],document),document)==[]

def test_existing_figure_title_declaration_does_not_create_an_unmatched_duplicate_figure():
    graphic=obj("figure",(70,390,510,485),role="native_figure")
    table=obj("table",(67,292,500,479),parent_id="qa")
    title=obj("figure_caption",(171,490,407,504),"图5.6 多模态可视化",parent_id="qa",parent_bbox=table.bbox)
    document=doc(*cells(table.bbox))
    repaired=repair([graphic,table,title],document)
    assert alarms(repaired,document)==[]
    assert detect_caption_rules(repaired,(13,),document)["13"]["findings"]==[]

def test_caption_parent_with_explanatory_note_can_own_its_unique_table():
    target=obj("table",(80,220,520,400),parent_id="main")
    caption=obj("table_caption",(180,100,420,115),"表2.1 方法对比",parent_id="main",parent_bbox=target.bbox)
    document=doc(line("表2.1 方法对比",caption.bbox,bold=True),
                 line("注：√ 表示支持，开销以复杂度衡量。",(80,125,520,145)),
                 line("该比较使用统一的评估任务。",(80,150,520,168)),
                 *cells(target.bbox))
    assert alarms(repair([target,caption],document),document)==[]

def test_explicit_upper_bottom_caption_owns_stacked_subtables_without_panel_letters():
    a,b=obj("table",(140,200,460,300)),obj("table",(240,310,370,390))
    caption=obj("table_caption",(80,150,520,190),"Table 3.2 Results. Upper: performance. Bottom: number of persons.")
    document=doc(*cells(a.bbox,cols=(160,340)),*cells(b.bbox,cols=(250,320)))
    repaired=repair([a,b,caption],document)
    assert len([o for o in repaired if o.kind=="table"])==1
    assert alarms(repaired,document)==[]

def test_repeated_math_fragments_with_equation_numbers_are_not_a_table():
    target=obj("table",(340,210,455,450),role="native_table")
    document=doc(line("v log(m/v) + log(1/δ)",(344,213,453,226)),
                 line("2m",(390,230,405,242)),line("(A.8)",(499,220,524,234)),
                 line("v log(m/v) + log(1/δ)",(344,320,453,333)),line("m",(390,338,400,350)),
                 line("(A.9)",(499,329,524,342)))
    assert alarms(repair([target],document),document)==[]


def test_table_shaped_panel_and_adjacent_plot_share_an_explicit_figure_declaration():
    plot=obj("figure",(80,120,270,300),parent_id="plot")
    table=obj("table",(310,120,510,300),parent_id="data")
    title=obj("figure_caption",(110,320,490,350),"Figure 3.11 Analysis of area",parent_id="data",parent_bbox=table.bbox)
    document=doc(*cells(table.bbox,cols=(330,440)))
    repaired=repair([plot,table,title],document)
    assert alarms(repaired,document)==[]
    assert detect_caption_rules(repaired,(13,),document)["13"]["findings"]==[]

def test_a_figure_title_listing_panels_owns_a_distant_heatmap_component():
    matrix=obj("table",(80,110,520,330))
    plots=obj("figure",(80,340,520,650))
    title=obj("figure_caption",(90,660,510,715),"Figure 4.4 (a) heatmap, (b) ROC, (c) output map")
    document=doc(*cells(matrix.bbox))
    repaired=repair([matrix,plots,title],document)
    assert alarms(repaired,document)==[]
    assert len([o for o in repaired if o.kind=="figure"])==1

def test_centered_shared_comparison_title_owns_parallel_grids_with_matching_metric_headers():
    a,b=obj("table",(100,180,270,320)),obj("table",(310,180,480,320))
    caption=obj("table_caption",(130,135,450,165),"Table 3.4 Comparison across data categories")
    document=doc(line("Class",(105,188,145,200)),line("Acc",(180,188,210,200)),line("ASR",(235,188,265,200)),
                 line("Class",(315,188,355,200)),line("Acc",(390,188,420,200)),line("ASR",(445,188,475,200)),
                 *cells((100,200,270,320),cols=(110,190,240),names=("A","B","C")),
                 *cells((310,200,480,320),cols=(320,400,450),names=("D","E","F")))
    repaired=repair([a,b,caption],document)
    assert len([o for o in repaired if o.kind=="table"])==1
    assert alarms(repaired,document)==[]

def test_explicit_main_title_lists_the_unique_semantic_headings_of_stacked_subtables():
    a,b=obj("table",(80,200,520,280),"Flow estimation"),obj("table",(80,290,520,380),"Road estimation")
    caption=obj("table_caption",(80,130,520,190),"Table 4.4 Flow estimation and Road estimation performance")
    document=doc(line("Flow estimation",(80,204,200,216)),line("Road estimation",(80,294,200,306)),
                 *cells((80,220,520,280)),*cells((80,310,520,380)))
    assert alarms(repair([a,b,caption],document),document)==[]

def test_untitled_vertical_table_with_a_clear_empty_gap_remains_independent():
    a,b=obj("table",(80,200,520,300)),obj("table",(80,360,520,440))
    title=obj("table_caption",(150,170,450,188),"Table 4.4 Scores")
    document=doc(*cells(a.bbox,cols=(100,200,300,400),names=("A","B","C")),
                 *cells(b.bbox,cols=(100,200,300,400),names=("D","E","F")))
    assert len(alarms(repair([a,b,title],document),document))==1

def test_example_frame_continuation_retains_its_previous_page_declaration():
    target=obj("table",(80,100,520,350),"抽取得到的语义三元组 〈用户A,居住地,纽约〉←原文 〈用户A,担忧,孩子〉←原文",page=2)
    document=doc(line("三元组提取模块示例",(80,660,280,680)),
                 line("输入文本",(80,686,150,700)),
                 line("用户：此前在纽约生活",(80,720,510,740)),
                 line(target.text,(80,110,510,340),page=2))
    assert alarms(repair([target],document),document)==[]


def test_continuous_dense_columns_between_table_windows_form_one_physical_grid():
    a,b=obj("table",(80,180,520,300)),obj("table",(80,365,520,430))
    title=obj("table_caption",(140,145,460,170),"Table 4.14 Benchmark results")
    rows=[line(value,(x,y,x+30,y+10)) for y in range(190,421,20)
          for x,value in zip((100,220,340,460),("Method","0.8","0.7","0.9"))]
    document=doc(*rows)
    repaired=repair([a,b,title],document)
    assert len([o for o in repaired if o.kind=="table"])==1
    assert alarms(repaired,document)==[]


def test_a_narrow_centered_figure_title_owns_its_explicit_a_b_panel_namespace():
    a=obj("table",(110,100,490,130))
    b=obj("figure",(80,150,520,320))
    title=obj("figure_caption",(200,350,400,375),"Figure 3.8 Instruction set")
    document=doc(line("(a) Instruction format",(270,135,340,145)),line("(b) Instruction summary",(270,330,340,342)))
    repaired=repair([a,b,title],document)
    assert alarms(repaired,document)==[]
    assert detect_caption_rules(repaired,(13,),document)["13"]["findings"]==[]

def test_parallel_table_group_ends_before_a_separately_captioned_plot_below():
    a,b=obj("table",(100,180,270,320)),obj("table",(310,180,480,320))
    title=obj("table_caption",(130,135,450,165),"Table 3.4 Comparison across categories")
    plot=obj("figure",(110,340,480,460))
    plot_title=obj("figure_caption",(140,485,440,505),"Figure 3.7 Trigger types")
    document=doc(line("Class",(105,188,145,200)),line("Acc",(180,188,210,200)),line("ASR",(235,188,265,200)),
                 line("Class",(315,188,355,200)),line("Acc",(390,188,420,200)),line("ASR",(445,188,475,200)),
                 line("(a) Plot legend",(200,470,300,482)),line("Trigger number",(220,445,320,455)))
    repaired=repair([a,b,title,plot,plot_title],document)
    assert alarms(repaired,document)==[]
    assert any(o.kind=="figure" and o.bbox==plot.bbox for o in repaired)


def test_bare_a_b_panel_marks_establish_one_captioned_figure():
    plot=obj("figure",(80,120,270,300))
    table=obj("table",(310,120,510,300),parent_id="data")
    title=obj("figure_caption",(110,330,490,350),"Figure 3.15 Comparison",parent_id="data",parent_bbox=table.bbox)
    document=doc(line("(a)",(160,310,180,320)),line("(b)",(400,310,420,320)),*cells(table.bbox,cols=(330,450)))
    repaired=repair([plot,table,title],document)
    assert alarms(repaired,document)==[]
    assert detect_caption_rules(repaired,(13,),document)["13"]["findings"]==[]


@pytest.mark.parametrize("transition", ["1 Introduction", "2 Experiments", "This section compares the observed performance."])
def test_glossary_scope_does_not_swallow_a_research_transition_with_an_untitled_table(transition):
    glossary=obj("table",(80,200,520,730))
    research=obj("table",(80,200,520,380),page=2)
    document=doc(line("符号对照表",(200,125,400,145)),*cells(glossary.bbox,names=("α","β")),
                 line(transition,(80,110,520,135),page=2,font_size=16),
                 *cells(research.bbox,page=2,names=("MethodA","MethodB")))
    repaired=repair([glossary,research],document)
    assert [o.page_number for o in repaired if o.kind=="table"]==[2]
    assert len(alarms(repaired,document))==1

def test_untitled_comparison_table_algorithm_label_is_a_cell_not_a_frame_declaration():
    target=obj("table",(80,150,520,330),role="table_body")
    document=doc(line("Algorithm 1",(90,160,180,172)),line("Input",(220,160,260,172)),
                 line("Output",(340,160,390,172)),line("32",(460,160,480,172)),
                 line("Algorithm 2",(90,190,180,202)),line("40",(220,190,260,202)),
                 line("50",(340,190,390,202)),line("60",(460,190,480,202)))
    repaired=repair([target],document)
    assert repaired==[target]
    assert len(alarms(repaired,document))==1

def test_section_title_with_body_after_the_table_is_not_an_exclusive_table_name():
    target=obj("table",(80,200,520,350))
    document=doc(line("3.1 Hardware configuration",(80,165,360,185),font_size=14),
                 *cells(target.bbox),line("We then explain how the hardware influences the results.",(80,370,520,385)))
    assert len(alarms(repair([target],document),document))==1

def test_an_explicit_table_title_wins_over_algorithm_named_rows():
    target=obj("table",(80,150,520,330),role="table_body")
    title=obj("table_caption",(150,120,450,138),"Table 4.1 Input and output statistics")
    document=doc(line("Algorithm 1",(90,160,180,172)),line("Input",(220,160,260,172)),
                 line("Output",(340,160,390,172)),line("32",(460,160,480,172)))
    repaired=repair([target,title],document)
    assert any(o.kind=="table" and o.bbox==target.bbox for o in repaired)
    assert alarms(repaired,document)==[]

def test_repair_is_idempotent_and_retains_input_when_no_document_is_available():
    target=obj("table",(83,209,524,296),"硬件 配置 CPU GPU")
    document=doc(line("A.1 硬件配置",(85,169,180,185),font_size=14),*cells(target.bbox))
    repaired=repair([target],document)
    assert repair(repaired,document)==repaired
    assert repair([target],None)==[target]


def translated_restarted_table_fixture(barrier=False):
    first=obj("table",(80,306,500,424),panel_boxes=((80,338,270,424),(310,338,500,424)))
    second=obj("table",(195,469,385,555))
    title=obj("table_caption",(195,285,385,300),"表4.4 不同条件下的性能比较")
    boxes=((80,338,270,424),(310,338,500,424),second.bbox)
    lines=[]
    for box,tag in zip(boxes,("a","b","c" if barrier else "a")):
        cx=(box[0]+box[2])/2
        lines.extend([line(f"({tag}) 条件比较",(cx-30,box[1]-32,cx+30,box[1]-19)),
                      line(f"({tag}) Condition comparison",(cx-50,box[1]-17,cx+50,box[1]-5))])
    if barrier:
        lines.append(line("The following results concern a separate experiment.",(80,427,500,439)))
    return [first,second,title],doc(*lines)


def test_restarted_bilingual_panel_namespace_preserves_an_independent_lower_table():
    objects,document=translated_restarted_table_fixture()
    repaired=repair(objects,document)
    assert len([o for o in repaired if o.kind=="table"])==2
    assert len(alarms(repaired,document))==1


def test_body_paragraph_between_translated_table_panels_blocks_the_join():
    objects,document=translated_restarted_table_fixture(barrier=True)
    assert repair(objects,document)==objects


def test_independent_figure_title_covering_real_panel_text_cannot_redeclare_the_table():
    boxes=((40,100,140,220),(160,100,260,220),(40,270,140,390),(160,270,260,390))
    objects=[obj("table" if i==1 else "figure",box) for i,box in enumerate(boxes)]
    objects.extend([obj("figure_caption",(40,410,260,426),"Figure 9.8 Comparisons"),
                    obj("figure",(350,80,570,205)),
                    obj("figure_caption",(100,230,220,245),"Figure 9.9 Independent experiment")])
    document=doc(*(line(f"({tag}) condition",(box[0]+15,box[3]+5,box[2]-15,box[3]+17))
                   for box,tag in zip(boxes,"abcd")))
    document=PdfDocument(document.path,(PdfPage(1,600,840,document.pages[0].lines),))
    assert any(o.kind=="table" for o in repair(objects,document))


def test_foreign_column_panel_letters_do_not_establish_a_table_figure_namespace():
    objects=[obj("table",(100,100,220,220)),obj("figure",(380,100,500,220)),
             obj("figure_caption",(240,250,360,265),"Figure 9.8 Measurements")]
    document=doc(line("(a) Other",(530,225,580,237)),line("(b) Other",(530,242,580,254)))
    assert repair(objects,document)==objects

def test_different_semantic_column_headers_block_a_numeric_page_continuation():
    first=obj("table",(80,620,520,704))
    second=obj("table",(80,100,520,220),page=2)
    title=obj("table_caption",(180,597,440,614),"Table 8.2 Timing")
    rows=[line(t,(x,625,x+60,637)) for x,t in zip((100,220,340,450),("Batch","Time","Cost","Total"))]
    rows.extend(line(str(v),(x,688,x+40,700)) for x,v in zip((100,220,340,450),(300,123,234,357)))
    rows.extend(line(t,(x,104,x+60,116),page=2) for x,t in zip((100,220,340,450),("Samples","Accuracy","Recall","F1")))
    rows.extend(line(str(v),(x,y,x+40,y+12),page=2)
                for y,values in ((145,(400,456,567,1023)),(186,(500,678,789,1467)))
                for x,v in zip((100,220,340,450),values))
    document=doc(*rows)
    repaired=repair([first,second,title],document)
    assert any(o.kind=="table" and o.page_number==2 for o in repaired)
    assert len(alarms(repaired,document))==1


def test_one_printed_label_seen_by_overlapping_table_windows_is_not_a_namespace_restart():
    first=obj("table",(100,175,500,250))
    second=obj("table",(100,231,500,372),panel_boxes=((100,281,500,357),(100,231,500,283)))
    title=obj("table_caption",(80,100,520,169),"Table 4.3 Input understanding")
    document=doc(line("(a) Input as string",(240,254,340,265)),line("(b) Input as queue",(245,361,335,372)))
    repaired=repair([first,second,title],document)
    assert len([o for o in repaired if o.kind=="table"])==1
    assert alarms(repaired,document)==[]

@pytest.mark.parametrize("role",("table_body","native_table"))
def test_a_neighbour_figure_owns_its_title_before_the_untitled_table_above(role):
    table=obj("table",(80,150,520,350),role=role)
    figure=obj("figure",(80,410,520,550),role="native_figure" if role=="native_table" else "image_body")
    title=obj("figure_caption",(180,373,420,388),"Figure 2.1 Separate example")
    document=doc(*cells(table.bbox,names=("MethodA","MethodB")))
    repaired=repair([table,figure,title],document)
    assert any(o.kind=="table" and o.bbox==table.bbox for o in repaired)
    assert len(alarms(repaired,document))==1


def test_a_sole_table_shaped_figure_retains_its_exclusive_figure_title():
    table=obj("table",(80,150,520,350))
    title=obj("figure_caption",(180,373,420,388),"Figure 2.1 Tabular schematic")
    document=doc(*cells(table.bbox))
    repaired=repair([table,title],document)
    assert not any(o.kind=="table" for o in repaired)
    assert detect_caption_rules(repaired,(13,14),document)["13"]["findings"]==[]


def test_a_comparison_table_with_one_c_code_cell_is_not_a_listing():
    texts=["Method Latency Result","baseline 24 struct Message { ItemType type; }","new 16 true"]
    target=obj("table",(70,120,520,280)," ".join(texts))
    document=doc(line("代码 8.4",(180,90,420,104)),
                 *(line(text,(90,130+i*18,500,144+i*18)) for i,text in enumerate(texts)))
    assert repair([target],document)==[target]
    assert len(alarms([target],document))==1


def test_input_output_placeholder_columns_are_not_a_listing_instruction_template():
    texts=["Name Value","Input {first_input}","Output {result_value}","Model {model_id}"]
    target=obj("table",(70,120,520,280),"\n".join(texts),role="native_table")
    document=doc(line("Listing 12 Parameter comparison",(180,90,420,104)),
                 *(line(text,(90,130+i*18,500,144+i*18)) for i,text in enumerate(texts)))
    assert repair([target],document)==[target]
    assert len(alarms([target],document))==1


def test_a_complete_c_struct_body_supplies_positive_listing_evidence():
    texts=["1 struct Message {","2 ItemType type;","3 OpKind op;","4 uint64_t sequence;","5 Arguments args;","6 };"]
    target=obj("table",(70,120,520,280),"\n".join(texts))
    document=doc(line("代码 8.4",(180,90,420,104)),
                 *(line(text,(90,130+i*18,500,144+i*18)) for i,text in enumerate(texts)))
    assert alarms(repair([target],document),document)==[]


def test_a_listing_instruction_schema_has_a_task_and_semantic_input_output_sections():
    texts=["1 [当前任务] 你现在处于 {task_prompt} 阶段。",
           "2 [输入] 当前轮次: {iteration_id}；模型: {model_state}",
           "3 [处理要求] 分析输入并判断变化范围。",
           '4 [输出要求] 仅返回 JSON: {"result": []}']
    target=obj("table",(70,120,520,280),"\n".join(texts),role="native_table")
    document=doc(line("Listing 12 判定提示词",(180,90,420,104)),
                 *(line(text,(90,130+i*18,500,144+i*18)) for i,text in enumerate(texts)))
    assert alarms(repair([target],document),document)==[]

def test_a_separate_figure_with_its_own_closer_title_does_not_compete_for_a_table_shaped_figure():
    heatmap=obj("table",(100,100,500,350))
    heatmap_title=obj("figure_caption",(220,360,380,375),"Figure 4.24 Parameter sensitivity")
    plot=obj("figure",(90,385,510,490))
    plot_title=obj("figure_caption",(210,494,390,507),"Figure 4.25 Scheduling frequency")
    document=doc(*cells(heatmap.bbox))
    repaired=repair([heatmap,plot,heatmap_title,plot_title],document)
    assert alarms(repaired,document)==[]
    assert detect_caption_rules(repaired,(13,),document)["13"]["findings"]==[]


def test_a_wrapped_boolean_query_keeps_code_identity_through_quoted_natural_words():
    texts=['TI=(("physically unclonable function*" OR "puf") AND ("design"',
           'OR "architecture")) AND DT=(Article OR "Proceedings',
           'Paper") NOT TI=("polyurethane foam" OR polyurethane OR "',
           'polyurea-formaldehyde" OR "PUF protein*" OR pumilio OR FBF OR "multi-',
           'part natural query text',
           'continued searchable words',
           'query phrase" OR "RNA-binding")']
    target=obj("table",(70,120,520,280))
    document=doc(line("代码列表 A.2 检索式",(180,90,420,104)),
                 *(line(text,(90,130+i*18,500,144+i*18)) for i,text in enumerate(texts)))
    assert alarms(repair([target],document),document)==[]
