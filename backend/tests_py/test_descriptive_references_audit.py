from pathlib import Path
from pdf_rules.model import PdfDocument,PdfPage,PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
from pdf_rules.text_fragments import merge_reference_fragments
from pdf_rules.mineru_layout import LayoutObject

def line(text,y,page=1):return PdfLine(page,text,(70,y,520,y+12),600,840)
def run(lines,objects=()):
 pages=tuple(PdfPage(n,600,840,tuple(l for l in lines if l.page_number==n)) for n in range(1,max(l.page_number for l in lines)+1))
 return detect_rules(build_index(PdfDocument(Path('evidence.pdf'),pages),objects),[11,15,16])

def test_word_shown_may_soft_wrap_inside_numbered_figure_reference():
 ls=[line('方法调用流程如图所',100),line('示4.9。该模块以独立线程运行。',122),line('图4.9 方法调用流程',300)]
 assert run(merge_reference_fragments(ls))['15']['findings']==[]

def test_bare_number_pair_with_shown_cue_resolves_unique_nearby_figures():
 ls=[line('图5.1 QPS变化曲线',300),line('图5.2 副本变化曲线',500),line('实验结果如5.1与5.2所示。',600),line('表5.1 参数配置',100,3)]
 assert run(ls)['15']['findings']==[]
 assert len(run(ls)['16']['findings'])==1

def test_bare_numbers_cannot_pick_a_kind_when_both_objects_are_equally_close():
 ls=[line('图3.1 实验结果',280),line('表3.1 实验结果',320),line('实验结果如3.1所示。',300)]
 assert len(run(ls)['15']['findings'])==len(run(ls)['16']['findings'])==1

def test_combined_word_graphics_with_number_uses_the_one_existing_kind():
 assert run([line('结果见如下图表6.6。',100),line('图6.6 模型得分',300)])['15']['findings']==[]

def test_title_name_followed_by_visual_predicate_is_usage():
 ls=[line('奖励值趋势图反映了模型打分。',400),line('图6.3 奖励值趋势图',300)]
 assert run(ls)['15']['findings']==[]

def test_merely_discussing_same_topic_does_not_mark_a_picture_referenced():
 ls=[line('本算法改善了模型奖励值的收敛趋势。',400),line('图6.3 奖励值趋势图',300)]
 assert len(run(ls)['15']['findings'])==1

def test_technical_graph_or_view_noun_is_not_a_picture_reference():
 ls=[line('同质图表示了邻居的属性，视图展示了系统状态。',400),line('图6.3 同质图趋势图',300)]
 assert len(run(ls)['15']['findings'])==1

def test_named_table_immediately_after_here_are_cue_is_usage():
 assert run([line('本文使用的软件环境如下：',100),line('表6.2 软件环境',140)])['16']['findings']==[]

def test_here_are_cue_cannot_cover_unrelated_table_title():
 assert len(run([line('本文使用的软件环境如下：',100),line('表6.2 模型准确率',140)])['16']['findings'])==1

def test_explicit_plural_tables_declaration_is_scoped_to_its_section():
 ls=[line('3.1 实验配置',100),line('下面的表格提供了实验配置。',160),line('表3.1 硬件配置',300),line('表3.2 软件配置',100,2),line('3.2 实验结果',300,2),line('表3.3 准确率',500,2)]
 assert [f['token'] for f in run(ls)['16']['findings']]==['3.3']

def test_plural_graph_terms_without_deictic_are_not_usage():
 ls=[line('3.1 实验配置',100),line('图表包含软件环境的信息。',160),line('表3.1 硬件配置',300)]
 assert len(run(ls)['16']['findings'])==1

def test_large_figure_body_on_next_page_can_resolve_deictic():
 ls=[line('静态特征框架，如图所示。',420),line('图3.3 预测框架',360,2)]
 objs=[LayoutObject('figure',2,(70,100,520,340),'',600,840,'chart_body')]
 assert run(ls,objs)['15']['findings']==[]


def test_running_chapter_headers_and_page_numbers_do_not_break_plural_usage():
 ls=[line('3.1 实验配置',100),line('下文的图表提供了测试结果。',160),line('表3.1 单线程结果',300),line('第3章',74),line('11',750),line('第3章',74,2),line('12',750,2),line('表3.2 多线程结果',140,2),line('3.2 后续实验',300,2),line('表3.3 后续结果',500,2)]
 assert [f['token'] for f in run(ls)['16']['findings']]==['3.3']

def test_plot_axis_number_is_not_a_section_boundary():
 ls=[line('KL散度变化图反映了偏差。',400),line('0.1',300),line('图6.4 KL散度变化图',350)]
 objs=[LayoutObject('figure',1,(70,200,520,330),'',600,840,'chart_body')]
 assert run(ls,objs)['15']['findings']==[]


def test_bare_shown_cue_reconstructs_one_native_prose_paragraph():
 from dataclasses import replace
 ls=[replace(line('这些表达形式与原子映射的概览如2.1',120),font_size=12),replace(line('所示。下面讨论模型架构。',142),font_size=12),line('图2.1 化学反应表达式',300)]
 assert run(ls)['15']['findings']==[]

def test_soft_wrap_does_not_join_different_columns_or_font_styles():
 from dataclasses import replace
 ls=[replace(line('这些表达形式与原子映射的概览如2.1',120),font_size=12),replace(line('所示。下面讨论模型架构。',142),font_size=10),line('图2.1 化学反应表达式',300)]
 assert len(run(ls)['15']['findings'])==1

def test_recorded_in_next_table_without_shown_suffix_is_usage():
 assert run([line('所有方法的运行时间记录于下表供比较。',100),line('表5.4 方法运行时间',300)])['16']['findings']==[]

def test_this_diagram_explanation_uses_closest_separate_figure():
 ls=[line('图3.7 前一张示意图',100),line('图3.8 当前示意图',400),line('这张示意图展示了采样方法。',430)]
 assert [f['token'] for f in run(ls)['15']['findings']]==['3.7']


def test_inline_subheading_reference_is_prose_not_a_caption():
 from dataclasses import replace
 ls=[replace(line('图5.2以两种内核为例，展示了',350),bbox=(280,350,520,362),font_size=12),replace(line('虚拟缓存的适配流程。开发者无需修改内核。',372),font_size=12),replace(line('图5.2 两种内核适配流程',180),font_size=10.5,bold=True)]
 assert run(ls)['15']['findings']==[]


def test_explicit_appendix_content_citation_covers_its_named_visual_contents():
 ls=[line('角色提示的详细内容与模板在附录A中给出。',100),line('附录A 提示模板',100,2),line('图A.1 医生提示模板',300,2),line('附录B 实验结果',100,3),line('图B.1 误差曲线',300,3)]
 assert [f['token'] for f in run(ls)['15']['findings']]==['B.1']


def test_colon_number_cue_needs_shared_title_when_object_kinds_conflict():
 ls=[line('原始文本如3.1：',600),line('图3.1 推理流程',650),line('表3.1 新闻原始文本',100,2)]
 assert run(ls)['16']['findings']==[]
 assert len(run(ls)['15']['findings'])==1

def test_summary_number_cue_and_corresponding_number_cue_are_usage():
 ls=[line('架构的对比分析具体汇总于1.1。',100),line('表1.1 主流架构对比分析',150),line('设计消融实验（对应5.3）：移除关键模块。',600),line('表5.3 模块消融实验结果',100,2)]
 assert run(ls)['16']['findings']==[]

def test_generic_number_cue_cannot_be_a_section_or_unrelated_subject():
 ls=[line('详细推导对应5.3节。',100),line('原始文本如3.1：',300),line('表5.3 消融实验结果',150),line('表3.1 精度对比',350)]
 assert len(run(ls)['16']['findings'])==2

def test_parameters_here_are_cue_has_table_subject_evidence():
 assert run([line('相关参数分别设置如下：',100),line('表6.1 默认超参数设置',140)])['16']['findings']==[]

def test_named_diagram_explanation_with_panel_cue_is_usage():
 ls=[line('Panda数据集预处理与训练样本生成流程示意图中(a)图为原始图像。',400),line('图3.7 Panda数据集预处理后训练样本图像块采样示意图',300)]
 assert run(ls)['15']['findings']==[]

def test_explicit_deictic_can_follow_a_float_across_page_boundary():
 ls=[line('图3.13 多级池化和卷积并行示意图',630),line('如图所示，第一条支路采用卷积。',400,2)]
 objs=[LayoutObject('figure',1,(70,440,520,610),'',600,840,'chart_body')]
 assert run(ls,objs)['15']['findings']==[]

def test_cross_page_deictic_cannot_choose_between_two_figures():
 ls=[line('图3.12 前一支路示意图',610),line('图3.13 后一支路示意图',660),line('如图所示，第一条支路采用卷积。',400,2)]
 objs=[LayoutObject('figure',1,(70,440,280,600),'',600,840,'chart_body'),LayoutObject('figure',1,(300,440,520,650),'',600,840,'chart_body')]
 assert len(run(ls,objs)['15']['findings'])==2


def test_body_scale_number_does_not_create_section_boundary():
 ls=[line('图3.7 图像块采样示意图',300),line('2 尺度的缩略图与采样密度用于说明处理方法。',360),line('图像块采样示意图中(a)图为原始图像。',400)]
 assert run(ls)['15']['findings']==[]


def test_short_finite_prose_predicate_is_not_a_second_caption():
 from dataclasses import replace
 ls=[replace(line('图5.3揭示了一个相变现象：',350),bbox=(94,350,301,362),font_size=12),replace(line('多个智能体设置的实验结果保持一致。',380),font_size=12),replace(line('图5.3 群体规模的非线性影响',100,2),font_size=10.5,bold=True)]
 assert run(ls)['15']['findings']==[]

def test_prose_predicate_on_last_page_line_is_still_a_reference():
 from dataclasses import replace
 ls=[replace(line('相关架构通过过滤减少知识传播范围。',600),font_size=12),replace(line('图3.2更直观地展现了框架设计的演化。',720),font_size=12),replace(line('图3.2 双层过滤结构',300,2),font_size=10.5,bold=True)]
 assert run(ls)['15']['findings']==[]

def test_summary_cue_can_resolve_one_immediately_following_table():
 assert run([line('为全面对比这些架构，本文从性能和内存维度进行分析，具体汇总于1.1。',100),line('表1.1 主流设备端架构对比分析',140)])['16']['findings']==[]


def test_local_table_subject_beats_earlier_picture_name_in_long_paragraph():
 ls=[line('频段互补图对比学习框架是本章的方法，采用典型数据集，统计数据如4.1所示。',200),line('图4.1 频段互补图对比学习框架',400),line('表4.1 数据集统计数据',100,4)]
 assert run(ls)['16']['findings']==[]
 assert len(run(ls)['15']['findings'])==1


def test_composed_prompt_pair_resolves_omitted_object_prefix():
 ls=[line('附录B 提示词',80),line('完整提示词由B.4和B.5拼接而成。',100),line('图B.4 复杂研究计划提示词第一部分',300),line('图B.5 复杂研究计划提示词第二部分',300,2)]
 assert run(ls)['15']['findings']==[]


def test_composition_with_ambiguous_figure_table_numbers_does_not_guess():
 ls=[line('附录B 提示词',80),line('完整提示词由B.4和B.5拼接而成。',100),line('图B.4 复杂研究计划提示词',300),line('表B.4 复杂研究计划提示词',500),line('图B.5 复杂研究计划提示词',300,2),line('表B.5 复杂研究计划提示词',500,2)]
 assert len(run(ls)['15']['findings'])==len(run(ls)['16']['findings'])==2


def test_chapter_composition_cannot_be_mistaken_for_visual_usage():
 ls=[line('本章节由3.1和3.2组成。',100),line('图3.1 本章节组织结构',300),line('图3.2 本章节组织结构',500)]
 assert len(run(ls)['15']['findings'])==2


def test_section_explicitly_provides_a_named_series_of_tables():
 ls=[line('本节给出各方法在任务序列上的完整准确率矩阵。',100),line('表3.2 方法一准确率矩阵',300),line('表3.3 方法二准确率矩阵',500),line('3.5 小结',700),line('表3.4 方法三准确率矩阵',100,2),line('表3.5 参数配置',300,2)]
 assert [x['token'] for x in run(ls)['16']['findings']]==['3.5']


def test_topic_discussion_is_not_a_named_table_series_reference():
 ls=[line('本节研究各方法的准确率矩阵。',100),line('表3.2 方法一准确率矩阵',300),line('表3.3 方法二准确率矩阵',500)]
 assert len(run(ls)['16']['findings'])==2


def test_series_declaration_cannot_guess_when_both_kinds_have_same_names():
 ls=[line('本节给出各方法的准确率矩阵。',100),line('表3.2 方法一准确率矩阵',300),line('表3.3 方法二准确率矩阵',500),line('图3.2 方法一准确率矩阵',300,2),line('图3.3 方法二准确率矩阵',500,2)]
 assert len(run(ls)['16']['findings'])==len(run(ls)['15']['findings'])==2


def test_untyped_as_follows_cue_points_to_the_one_adjacent_visual():
 ls=[line('本文共分六章，具体组织如下所示：',100),line('图1.1 全文组织结构',600)]
 objects=[LayoutObject('figure',1,(80,130,520,580),'',600,840,'image_body')]
 assert run(ls,objects)['15']['findings']==[]


def test_intervening_prose_list_prevents_untyped_visual_reference():
 ls=[line('本文步骤如下所示：',100),line('第一步初始化参数，第二步计算模型输出。',130),line('图1.1 全文组织结构',600)]
 objects=[LayoutObject('figure',1,(80,180,520,580),'',600,840,'image_body')]
 assert len(run(ls,objects)['15']['findings'])==1


def test_untyped_cue_does_not_pick_between_two_adjacent_visuals():
 ls=[line('本文具体组织如下所示：',100),line('图1.1 全文组织结构',400),line('图1.2 计算结构',600)]
 objects=[LayoutObject('figure',1,(80,130,280,380),'',600,840,'image_body'),LayoutObject('figure',1,(320,130,520,580),'',600,840,'image_body')]
 assert len(run(ls,objects)['15']['findings'])==2



def test_bare_number_with_reporting_predicate_uses_distinct_title_subject():
 ls=[line('评论文本的词频与词云分析结果3.5显示了分布差异。',600),
     line('图3.5 词云统计对比',300,2),line('表3.5 标注一致性统计结果',100)]
 r=run(ls)
 assert r['15']['findings']==[]
 assert [x['token'] for x in r['16']['findings']]==['3.5']


def test_reporting_predicate_cannot_choose_equal_subjects_across_kinds():
 ls=[line('性能对比分析结果3.5显示了方法间的差异。',100),line('图3.5 性能对比',300),line('表3.5 性能对比',500)]
 r=run(ls)
 assert len(r['15']['findings'])==len(r['16']['findings'])==1


def test_generic_decimal_result_is_not_a_visual_reference():
 ls=[line('实验分析结果3.5显示了显著变化。',100),line('图3.5 模型误差趋势',300)]
 assert len(run(ls)['15']['findings'])==1


def test_section_and_formula_suffixes_do_not_become_visual_usage():
 ls=[line('分析结果3.5节显示了误差趋势；计算结果如式3.5所示。',100),line('图3.5 模型误差趋势',300)]
 assert len(run(ls)['15']['findings'])==1


def test_explicit_named_visualization_usage_can_span_float_page():
 ls=[line('本文通过频段拓扑图对不同睡眠状态进行了可视化分析。',600),
     line('图6.1 不同频段和睡眠状态的空间分布',300,2)]
 assert run(ls)['15']['findings']==[]


def test_visualization_cue_cannot_pick_two_equal_subjects():
 ls=[line('本文通过拓扑图对不同睡眠状态进行了可视化分析。',100),
     line('图6.1 不同睡眠状态的能量分布',300),line('图6.2 不同睡眠状态的频段分布',500)]
 assert len(run(ls)['15']['findings'])==2


def test_technical_graph_training_does_not_reference_a_picture():
 ls=[line('本文利用知识图对睡眠状态进行分类训练，并分析模型误差。',100),
     line('图6.1 不同睡眠状态的能量分布',300)]
 assert len(run(ls)['15']['findings'])==1


def test_visualization_cue_cannot_cross_a_new_section():
 ls=[line('本文通过频段拓扑图对不同睡眠状态进行了可视化分析。',100),
     line('6.4 另一组实验',250),line('图6.1 不同睡眠状态的能量分布',400)]
 assert len(run(ls)['15']['findings'])==1


def test_explicit_bare_architecture_cue_uses_framework_caption_despite_table_id_collision():
 ls=[line('模型的整体架构如7.1所示。',500),line('图7.1 模型整体框架',300,2),line('表7.1 运行参数配置',100,3)]
 assert run(ls)['15']['findings']==[]
 assert len(run(ls)['16']['findings'])==1


def test_explicit_bare_framework_cue_uses_architecture_caption():
 ls=[line('模型的整体框架如7.1所示。',500),line('图7.1 模型整体架构',300,2),line('表7.1 运行参数配置',100,3)]
 assert run(ls)['15']['findings']==[]


def test_bare_architecture_cue_cannot_resolve_equally_matching_object_kinds():
 ls=[line('整体架构如7.1所示。',300),line('图7.1 模型整体框架',270),line('表7.1 模型整体架构',330)]
 assert len(run(ls)['15']['findings'])==len(run(ls)['16']['findings'])==1
