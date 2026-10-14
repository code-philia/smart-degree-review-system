import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pdf_rules.model import PdfDocument,PdfPage,PdfLine,DocumentIndex,Label
from pdf_rules.local_rules import detect_rules
try:
 from pdf_rules.reference_identity_repair import repair_reference_identity
except ImportError:
 repair_reference_identity=None


def line(text,y=100,*,page=1,x=60,right=540,bold=False,size=12,role='',direction=(1.,0.)):
 return PdfLine(page,text,(x,y,right,y+14),600,800,bold=bold,font_size=size,role=role,direction=direction)

def index(*pages,figures=(),tables=(),refs=(),trefs=(),arefs=(),appendices=()):
 doc=PdfDocument(Path('unrelated-fixture.pdf'),tuple(pages))
 return DocumentIndex(doc,list(figures),list(tables),list(refs),list(trefs),appendices=list(appendices),appendix_refs=list(arefs))

def page(*lines,number=1,images=(),tables=(),graphics=()):
 return PdfPage(number,600,800,tuple(lines),images=tuple(images),tables=tuple(tables),graphics=tuple(graphics))

class ReferenceIdentityRepairTests(unittest.TestCase):
 def repair(self,i):
  self.assertIsNotNone(repair_reference_identity,'authorized independent repair entry point must exist')
  return repair_reference_identity(i)
 def alarms(self,i,rule):return detect_rules(i,{rule})[str(rule)]['findings']
 def test_genuinely_missing_figure_and_unreferenced_object_are_retained(self):
  cap=line('图1.1 系统结构',400,bold=True,size=10);ref=line('实验结果如图9所示。')
  i=index(page(cap,ref,images=((90,180,520,380),)),figures=[Label('1.1',cap,'body')],refs=[Label('9',ref,'body')])
  out=self.repair(i)
  self.assertEqual([x['token'] for x in self.alarms(out,11)],['9']);self.assertEqual([x['token'] for x in self.alarms(out,15)],['1.1'])
  self.assertEqual(i.figures,out.figures);self.assertIsNot(i,out)
 def test_external_appendix_and_figure_do_not_create_local_missing_targets(self):
  a=line('其具体描述可以在文献[29][附录B]中找到。');f=line('运行时间来自[71]图9。',130)
  i=index(page(a,f),refs=[Label('9',f,'body')],arefs=[Label('B',a,'body')])
  out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertFalse(self.alarms(out,29))
 def test_explicit_own_appendix_after_bibliography_reference_is_retained(self):
  a=line('对照文献[29]，详见本论文附录B。')
  out=self.repair(index(page(a),arefs=[Label('B',a,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,29)],['B'])
 def test_graph_variables_do_not_hide_real_numbered_citation_in_same_sentence(self):
  r=line('如图3.4所示，给定初始计算图G0，图G1中的顶点映射到G2。')
  i=index(page(r),refs=[Label('3.4',r,'body'),Label('0',r,'body','G'),Label('1',r,'body','G')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),11)],['3.4'])
 def test_math_variable_without_definition_tuple_is_filtered(self):
  r=line('对于图H1,H2，以下二者等价，hom(G,H1)不等于hom(G,H2)。')
  out=self.repair(index(page(r),refs=[Label('1',r,'body','H'),Label('2',r,'body','H')]))
  self.assertFalse(self.alarms(out,11))
 def test_algorithm_row_number_after_complete_graph_is_not_a_figure(self):
  r=line('Input:包含所有网络链路的完全图 1 Ok0 ←selectCache(i,-1);')
  out=self.repair(index(page(r),refs=[Label('1',r,'body')]))
  self.assertFalse(self.alarms(out,11))
 def test_metric_cell_after_graph_name_is_not_figure_number(self):
  r=line('w/o 位置图 0.223')
  out=self.repair(index(page(r,tables=((40,80,560,160),)),refs=[Label('0',r,'body')]))
  self.assertFalse(self.alarms(out,11))
 def test_real_decimal_figure_reference_in_table_cell_is_preserved(self):
  r=line('参见图82.9的参数配置。')
  out=self.repair(index(page(r,tables=((40,80,560,160),)),refs=[Label('82.9',r,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,11)],['82.9'])
 def test_missing_leader_directory_entry_does_not_become_object(self):
  head=line('插 图',50,x=260,right=340);rows=[line(f'图3.{j} 系统方法说明 {60+j}',100+j*30) for j in range(1,5)]
  i=index(page(head,*rows),figures=[Label(f'3.{j}',row,'body') for j,row in enumerate(rows,1)])
  self.assertFalse(self.alarms(self.repair(i),15))
 def test_real_page_with_visuals_is_not_treated_as_directory(self):
  head=line('插图',50);cap=line('图3.1 系统结构 61',400,bold=True,size=10)
  i=index(page(head,cap,images=((90,180,520,380),)),figures=[Label('3.1',cap,'body')])
  self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_english_appendix_scope_matches_letter_numbered_table_reference(self):
  h=line('APPENDIX A ADDITIONAL EXPERIMENTS',40,bold=True,size=14);c=line('Table A.1 Experimental configurations',400,bold=True,size=10);r=line('As shown in Table A.1, the outcomes improve.',450)
  i=index(page(h,c,r,tables=((80,150,520,380),)),tables=[Label('A.1',c,'body')],trefs=[Label('A.1',r,'body','A')])
  out=self.repair(i);self.assertEqual(out.tables[0].scope,'A');self.assertFalse(self.alarms(out,16))
 def test_english_appendix_body_sentence_does_not_open_scope(self):
  h=line('Appendix A describes further experiments.');c=line('表2.1 配置参数',400,bold=True,size=10)
  i=index(page(h,c,tables=((80,150,520,380),)),tables=[Label('2.1',c,'body')])
  self.assertEqual(self.repair(i).tables[0].scope,'body')
 def test_body_statement_is_not_a_caption_and_counts_as_reference(self):
  r=line('表3.4固定γ=0.5，扫描λ报告标准微调结果。',100);c=line('表3.4 正则强度的影响',400,bold=True,size=10)
  i=index(page(r,c,tables=((80,160,520,380),)),tables=[Label('3.4',r,'body'),Label('3.4',c,'body')])
  out=self.repair(i);self.assertEqual(len(out.tables),1);self.assertFalse(self.alarms(out,16))
 def test_narrative_word_in_physically_bold_title_is_not_own_reference(self):
  c=line('图3.1 消融实验：展示了各模块影响',400,bold=True,size=10)
  i=index(page(c,images=((80,170,520,380),)),refs=[Label('3.1',c,'body')])
  out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertEqual([x['token'] for x in self.alarms(out,15)],['3.1'])
 def test_extra_figure_period_and_tilde_are_recovered(self):
  c=line('图5.6 测试结果',400,bold=True,size=10);r=line('As shown in Figure. 5.6, the result improves; 图～5.6亦验证。')
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('5.6',c,'body')])
  self.assertFalse(self.alarms(self.repair(i),15))
 def test_shared_word_list_followed_by_result_predicate_counts_all_tables(self):
  cs=[line(f'表3.{j} 消融结果',300+j*80,bold=True,size=10) for j in (1,2,3)];r=line('如表3.1 3.2 3.3结果所示，我们的方法更稳定。')
  i=index(page(r,*cs),tables=[Label(f'3.{j}',c,'body') for j,c in enumerate(cs,1)])
  self.assertFalse(self.alarms(self.repair(i),16))
 def test_reference_number_across_page_boundary_is_repaired(self):
  r=line('相关实验结果如图6-',720);r2=line('11所示，噪声越大收益越明显。',90,page=2);c=line('图6.11 噪声变化',400,bold=True,size=10)
  i=index(page(c,r,images=((80,170,520,380),)),page(r2,number=2),figures=[Label('6.11',c,'body')],refs=[Label('6',r,'body')])
  out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertFalse(self.alarms(out,15))
 def test_unrelated_next_page_number_is_not_joined(self):
  r=line('如图6所示。',720);r2=line('11个实例用于验证。',90,page=2)
  out=self.repair(index(page(r),page(r2,number=2),refs=[Label('6',r,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,11)],['6'])
 def test_wrapped_missing_number_remains_a_real_missing_target(self):
  r=line('相关实验结果如图6-',720);r2=line('11所示，噪声越大收益越明显。',90,page=2)
  out=self.repair(index(page(r),page(r2,number=2),refs=[Label('6',r,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,11)],['6.11'])
 def test_untyped_named_visual_list_is_used(self):
  r=line('整个数据集的场景缩略图和地点分布图见3-5和3-6。');cs=[line(f'图3.{j} 数据集可视化',400+(j-5)*80,bold=True,size=10) for j in(5,6)]
  i=index(page(r,*cs),figures=[Label(f'3.{j}',c,'body') for j,c in zip((5,6),cs)])
  self.assertFalse(self.alarms(self.repair(i),15))
 def test_generic_pointer_requires_unique_physical_topic_matching_object(self):
  c=line('图3.3 用户请求判定流程',400,bold=True,size=10);r=line('图中所示的判定流程体现了这一思路。',450)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.3',c,'body')])
  self.assertFalse(self.alarms(self.repair(i),15))
 def test_generic_pointer_does_not_assign_usage_to_nearest_other_table(self):
  a=line('表6.1 性能对比',200,bold=True,size=10);b=line('表6.2 数据集规模',500,bold=True,size=10);r=line('从表中数据可见，我们的方法性能较优。',470)
  i=index(page(a,r,b,tables=((80,100,520,180),(80,520,520,700))),tables=[Label('6.1',a,'body'),Label('6.2',b,'body')])
  out=self.repair(i);self.assertIn('6.2',[x['token'] for x in self.alarms(out,16)])
 def test_wrong_literal_number_is_not_silently_remapped_to_nearest_object(self):
  c=line('图4.2 结果',400,bold=True,size=10);r=line('如图4.5所示，实验更好。')
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('4.2',c,'body')],refs=[Label('4.5',r,'body')])
  out=self.repair(i);self.assertEqual([x['token'] for x in self.alarms(out,11)],['4.5']);self.assertEqual([x['token'] for x in self.alarms(out,15)],['4.2'])
 def test_title_named_table_description_establishes_use(self):
  r=line('(1)用户管理表：用于记录用户基本信息。');c=line('表6.2 用户管理表',400,bold=True,size=10)
  i=index(page(r,c,tables=((80,420,520,650),)),tables=[Label('6.2',c,'body')])
  self.assertFalse(self.alarms(self.repair(i),16))
 def test_bilingual_same_physical_object_is_merged_even_with_misnumbered_alias(self):
  a=line('图6.6 数据集管理',400,bold=True,size=10);b=line('Figure 6.4 Dataset management',420,bold=True,size=10);r=line('图6.6展示了管理视图。',460)
  i=index(page(a,b,r,images=((80,170,520,380),)),figures=[Label('6.6',a,'body'),Label('6.4',b,'body')],refs=[Label('6.6',r,'body')])
  out=self.repair(i);self.assertEqual(len(out.figures),1);self.assertFalse(self.alarms(out,15))
 def test_identical_number_for_two_physical_objects_is_not_merged(self):
  a=line('图1.1 图像甲',300,bold=True,size=10,x=40,right=260);b=line('Figure 1.1 Image B',300,bold=True,size=10,x=340,right=570)
  i=index(page(a,b,images=((40,120,260,280),(340,120,570,280))),figures=[Label('1.1',a,'body'),Label('1.1',b,'body')])
  self.assertEqual(len(self.repair(i).figures),2)
 def test_continued_table_is_single_unreferenced_logical_object(self):
  a=line('表2.1 实验参数',400,bold=True,size=10);b=line('表2.1（续）',80,page=2,bold=True,size=10)
  i=index(page(a,tables=((80,420,520,730),)),page(b,number=2,tables=((80,100,520,700),)),tables=[Label('2.1',a,'body'),Label('2.1',b,'body')])
  out=self.repair(i);self.assertEqual([x['token'] for x in self.alarms(out,16)],['2.1'])
 def test_cross_page_headers_do_not_interrupt_wrapped_citation(self):
  r=line('相关实验结果如图6-',720);head=line('上海交通大学硕士学位论文',70,page=2,size=9);r2=line('11所示，影像分析结果得到验证。',105,page=2);c=line('图6.11 影像分析结果',400,bold=True,size=10)
  i=index(page(c,r,images=((80,170,520,380),)),page(head,r2,number=2),figures=[Label('6.11',c,'body')],refs=[Label('6',r,'body')])
  out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertFalse(self.alarms(out,15))
 def test_specific_short_topic_shared_by_generic_pointer_proves_same_object(self):
  c=line('图3.3 策略引擎判定逻辑示意图',400,bold=True,size=10);r=line('图中所示的判定流程体现了这一思路。',470)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.3',c,'body')])
  self.assertFalse(self.alarms(self.repair(i),15))
 def test_generic_system_words_alone_do_not_establish_pointer_ownership(self):
  c=line('图3.3 图像分类系统',400,bold=True,size=10);r=line('该图的另一种系统不在本文研究范围内。',470)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.3',c,'body')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),15)],['3.3'])
 def test_real_figure_one_is_retained_when_math_graph_g_one_occurs_together(self):
  r=line('如图1所示，初始计算图G1包含多个顶点。')
  i=index(page(r),refs=[Label('1',r,'body'),Label('1',r,'body','G')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),11)],['1'])
 def test_bilingual_alias_does_not_reassign_reference_to_distinct_same_numbered_object(self):
  original=line('图6.4 另外的实验',200,bold=True,size=10);a=line('图6.6 数据集管理',600,bold=True,size=10);b=line('Figure 6.4 Dataset management',620,bold=True,size=10);r=line('参见图6.4所示的另外的实验。',650)
  i=index(page(original,a,b,r,images=((80,40,520,180),(80,350,520,580))),figures=[Label('6.4',original,'body'),Label('6.6',a,'body'),Label('6.4',b,'body')],refs=[Label('6.4',r,'body')])
  out=self.repair(i);self.assertEqual([x['token'] for x in self.alarms(out,15)],['6.6'])
 def test_bold_body_missing_number_does_not_claim_nearby_existing_figure(self):
  c=line('图2.1 系统框架',400,bold=True,size=10);r=line('图9.9展示了本文研究的网络结构。',460,bold=True,size=12)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')],refs=[Label('9.9',r,'body')])
  out=self.repair(i);self.assertEqual([t.number for t in out.figures],['2.1']);self.assertEqual([x['token'] for x in self.alarms(out,11)],['9.9'])
 def test_real_appendix_g_compact_label_is_not_deleted_as_math_graph(self):
  h=line('附录G 补充图示',40,bold=True,size=14);c=line('图G1 网络结构示意',400,bold=True,size=10);r=line('网络复杂度的说明如图G1所示。',460)
  i=index(page(h,c,r,images=((80,170,520,380),)),figures=[Label('G1',c,'G')],refs=[Label('1',r,'G','G')],appendices=[Label('G',h,'G')])
  out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertFalse(self.alarms(out,15));self.assertTrue(out.figure_refs)
 def test_true_missing_appendix_g_figure_is_not_deleted_as_math_graph(self):
  h=line('附录G 补充图示',40,bold=True,size=14);c=line('图G1 网络结构示意',400,bold=True,size=10);r=line('网络复杂度的说明如图G2所示。',460)
  i=index(page(h,c,r,images=((80,170,520,380),)),figures=[Label('G1',c,'G')],refs=[Label('2',r,'G','G')],appendices=[Label('G',h,'G')])
  out=self.repair(i);self.assertEqual([x['token'] for x in self.alarms(out,11)],['G2']);self.assertEqual([x['token'] for x in self.alarms(out,15)],['G1'])
 def test_missing_appendix_g_target_without_any_existing_figures_is_retained(self):
  h=line('附录G 补充图示',40,bold=True,size=14);r=line('网络复杂度的说明如图G2所示。',460)
  i=index(page(h,r),refs=[Label('2',r,'G','G')],appendices=[Label('G',h,'G')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),11)],['G2'])
 def test_orphan_number_without_description_never_creates_target(self):
  c=line('图4.1 系统框架',400,bold=True,size=10);orphan=line('图4.2',440,bold=True,size=10);r=line('如图4.2所示。',500)
  i=index(page(c,orphan,r,images=((80,170,520,380),)),figures=[Label('4.1',c,'body')],refs=[Label('4.2',r,'body')])
  out=self.repair(i);self.assertEqual([t.number for t in out.figures],['4.1']);self.assertEqual([x['token'] for x in self.alarms(out,11)],['4.2'])
 def test_author_concatenated_complete_numbers_are_not_guessed_as_a_list(self):
  a=line('图4.5 结果甲',400,bold=True,size=10);b=line('图4.6 结果乙',600,bold=True,size=10);r=line('如图4.54.6所示。',700)
  i=index(page(a,b,r,images=((80,170,520,380),(80,460,520,580))),figures=[Label('4.5',a,'body'),Label('4.6',b,'body')],refs=[Label('4.54.6',r,'body')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),11)],['4.54.6'])
 def test_matching_bilingual_words_cannot_bridge_independent_body_prose(self):
  body=line('这是普通正文段落，图中的布局参数与本研究主题完全不同。',400,size=12);a=line('图9.9展示了网络结构',440,bold=True,size=10);b=line('Figure 9.9 Network structure',460,bold=True,size=10);r=line('如图9.9所示。',500)
  i=index(page(body,a,b,r,images=((80,170,520,380),)),refs=[Label('9.9',r,'body')])
  out=self.repair(i);self.assertFalse(out.figures);self.assertEqual([x['token'] for x in self.alarms(out,11)],['9.9'])
 def test_full_page_raster_carrier_is_not_an_independent_figure(self):
  a=line('图9.9 系统框架',440,bold=True,size=10);r=line('如图9.9所示。',500)
  i=index(page(a,r,images=((0,0,600,800),)),refs=[Label('9.9',r,'body')])
  out=self.repair(i);self.assertFalse(out.figures);self.assertEqual([x['token'] for x in self.alarms(out,11)],['9.9'])
 def test_appendix_directory_entry_does_not_open_scope_or_create_appendix(self):
  toc=line('附录G 补充材料 .......... 90',90);c=line('图2.1 系统框架',400,bold=True,size=10)
  i=index(page(toc,c,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')])
  out=self.repair(i);self.assertEqual(out.figures[0].scope,'body');self.assertFalse(out.appendices)
 def test_wrapped_range_repair_preserves_other_literal_number_in_same_paragraph(self):
  r=line('如图8所示，相关实验结果如图6-',720);r2=line('11所示，噪声越大收益越明显。',90,page=2);c=line('图6.11 噪声变化',400,bold=True,size=10)
  i=index(page(c,r,images=((80,170,520,380),)),page(r2,number=2),figures=[Label('6.11',c,'body')],refs=[Label('8',r,'body'),Label('6',r,'body')])
  self.assertEqual([x['token'] for x in self.alarms(self.repair(i),11)],['8'])
 def test_evidence_is_emitted_and_repair_is_idempotent(self):
  a=line('其具体描述可以在文献[29][附录B]中找到。');i=index(page(a),arefs=[Label('B',a,'body')]);events=[]
  self.assertIsNotNone(repair_reference_identity);out=repair_reference_identity(i,evidence=events)
  self.assertTrue(events);self.assertEqual(out,self.repair(out))


 def numeric_table(self,second=False,physical=True,common=False):
  c=line('表3.8 模型性能比较',120,bold=True,size=10)
  h=line('Model Accuracy AUC Accuracy AUC',170)
  a=line('RVT-Base 0.874 0.912 0.920 0.939',200)
  b=line('RVT-Large 0.889 0.928 0.926 0.947',230)
  r=line('RVT-Base在两任务准确率分别为0.874和0.920，AUC分别为0.912和0.939；RVT-Large准确率为0.889和0.926，AUC为0.928和0.947。',450)
  if common:r=line('RVT-Base与RVT-Large的准确率和AUC表现较好，数值0.874和0.912。',450)
  ls=[c,h,a,b,r];targets=[Label('3.8',c,'body')];boxes=[(60,155,540,255)] if physical else []
  if second:
   c2=line('表3.9 重复的模型性能数据',520,bold=True,size=10);h2=line(h.text,570);a2=line(a.text,600);b2=line(b.text,630);ls.extend([c2,h2,a2,b2]);targets.append(Label('3.9',c2,'body'));boxes.append((60,550,540,655))
  return index(page(*ls,tables=boxes),tables=targets)
 def test_eight_exact_values_two_named_rows_and_two_fields_prove_table_usage(self):
  out=self.repair(self.numeric_table());self.assertFalse(self.alarms(out,16));self.assertEqual(len(out.tables),1)
 def test_two_common_values_or_topic_alone_do_not_prove_table_usage(self):
  self.assertEqual([f['token'] for f in self.alarms(self.repair(self.numeric_table(common=True)),16)],['3.8'])
 def test_duplicate_physical_tables_with_same_eight_values_stay_ambiguous(self):
  self.assertEqual([f['token'] for f in self.alarms(self.repair(self.numeric_table(second=True)),16)],['3.8','3.9'])
 def test_eight_values_without_physical_table_structure_do_not_prove_usage(self):
  self.assertEqual([f['token'] for f in self.alarms(self.repair(self.numeric_table(physical=False)),16)],['3.8'])
 def test_explicit_heatmap_presentation_with_unique_model_cache_metadata_is_used(self):
  c=line('图3.6 Method的大海捞针性能（1B模型，缓存512词元）',400,bold=True,size=10)
  r=line('在Llama-1B模型上采用512的缓存，生成准确率热力图，一幅热力图对应全部210场景，横轴表示文本长度，纵轴表示深度。',460)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]);self.assertFalse(self.alarms(self.repair(i),15))
 def test_heatmap_topic_without_exact_model_cache_ownership_stays_unreferenced(self):
  c=line('图3.6 Method性能（1B模型，缓存512词元）',400,bold=True,size=10);r=line('本文研究了1B模型和512缓存；实验性能较好，另有热力图。',460)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]);self.assertEqual([f['token'] for f in self.alarms(self.repair(i),15)],['3.6'])
 def test_two_heatmaps_with_same_metadata_do_not_take_a_generic_pointer(self):
  a=line('图3.6 Method性能（1B模型，缓存512词元）',300,bold=True,size=10);b=line('图3.7 Alternative性能（1B模型，缓存512词元）',600,bold=True,size=10);r=line('在Llama-1B模型上采用512缓存，一幅热力图对应全部210场景，横轴表示文本长度，纵轴表示深度。',650)
  i=index(page(a,b,r,images=((80,100,520,280),(80,400,520,580))),figures=[Label('3.6',a,'body'),Label('3.7',b,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),2)
 def test_external_heatmap_metadata_does_not_use_own_figure(self):
  c=line('图3.6 Method性能（1B模型，缓存512词元）',400,bold=True,size=10);r=line('文献[22]在1B模型上采用512缓存，一幅热力图对应210场景，横轴表示长度。',460)
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_body_interpreting_specific_code_identifiers_and_rows_uses_code_figure(self):
  c=line('图3.11 空指针漏洞',400,bold=True,size=10);a=line('1 void ssl_conn_init() {',200,x=80,right=500);b=line('2 CHandler = new TLSConnectionHandler();',230,x=80,right=500);z=line('3 void ssl_conn_handle() { CHandler->handle(); }',260,x=80,right=500);r=line('先调用ssl_conn_init，在第2行初始化CHandler，再调用ssl_conn_handle并解引用TLSConnectionHandler句柄。',460)
  i=index(page(a,b,z,c,r,images=((70,170,530,380),)),figures=[Label('3.11',c,'body')]);out=self.repair(i);self.assertFalse(self.alarms(out,15));self.assertEqual(len(out.figures),1)
 def test_one_common_code_identifier_does_not_prove_code_figure_usage(self):
  c=line('图3.11 空指针漏洞',400,bold=True,size=10);a=line('1 void ssl_conn_init() { CHandler = new TLSConnectionHandler(); }',200);r=line('CHandler是句柄，第2行的另一段程序调用函数。',460)
  i=index(page(a,c,r,images=((70,170,530,380),)),figures=[Label('3.11',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_parenthesized_as_number_uniquely_uses_existing_visual(self):
  c=line('图3.1 每个图块处理高斯数量分布箱线图',400,bold=True,size=10);r=line('由于瓦片负载差异巨大（如3.1），不同线程块的执行时间分化。',450)
  i=index(page(c,r,images=((70,170,530,380),)),figures=[Label('3.1',c,'body')]);self.assertFalse(self.alarms(self.repair(i),15))
 def test_parenthesized_scalar_example_does_not_use_same_numbered_visual(self):
  c=line('图3.1 高斯数量分布',400,bold=True,size=10);r=line('可取一个阈值（如3.1），其单位为毫秒。',450)
  i=index(page(c,r,images=((70,170,530,380),)),figures=[Label('3.1',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_parenthesized_as_number_with_real_same_number_section_is_ambiguous(self):
  c=line('图3.1 高斯数量分布',400,bold=True,size=10);h=line('3.1 高斯处理方法',100,bold=True);r=line('处理方法很复杂（如3.1），需要优化。',450)
  i=index(page(h,c,r,images=((70,170,530,380),)),figures=[Label('3.1',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_untyped_numbered_panels_use_exact_caption_panel_names(self):
  c=line('图2.6 (a) 非结构化稀疏 (b) 结构化稀疏',400,bold=True,size=10);r=line('稀疏化分为非结构化稀疏2.6(a)与结构化稀疏2.6(b)。',460)
  i=index(page(c,r,images=((70,170,530,380),)),figures=[Label('2.6',c,'body')]);self.assertFalse(self.alarms(self.repair(i),15))
 def test_untyped_numeric_expression_without_caption_panel_names_is_not_usage(self):
  c=line('图2.6 (a) 非结构化稀疏 (b) 结构化稀疏',400,bold=True,size=10);r=line('计算得到结果2.6(a)，其中a为系数。',460)
  i=index(page(c,r,images=((70,170,530,380),)),figures=[Label('2.6',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)
 def test_wrong_opposite_kind_number_with_real_same_number_table_remains_unresolved(self):
  f=line('图5.4 模型家族欺诈易感率',400,bold=True,size=10);t=line('表5.4 不同模拟规模的欺诈结果',600,bold=True,size=10);r=line('如表5.4所示，Qwen模型的Rpop和Rconv较低。',650)
  i=index(page(f,t,r,images=((70,170,530,380),),tables=((70,620,530,740),)),figures=[Label('5.4',f,'body')],tables=[Label('5.4',t,'body')],trefs=[Label('5.4',r,'body')]);out=self.repair(i);self.assertEqual(len(out.figures),1);self.assertEqual([f['token'] for f in self.alarms(out,15)],['5.4'])


 def paired_matrix(self,swapped=False,duplicate=False):
  c=line('图5.4 各模型风险值',120,bold=True,size=10);h=line('Model Rpop Rconv',170);a=line('Model-A 17.0 64.0',200);b=line('Model-B 41.0 60.2',230)
  r=line('Model-A达到了64.0%的高Rconv，但Rpop=17%；Model-B的Rconv(60.2%)、Rpop(41%)。',100,page=2)
  if swapped:r=line('Model-A的Rconv(17%)、Rpop(64%)；Model-B的Rconv(41%)、Rpop(60.2%)。',100,page=2)
  t=line('表5.4 不同规模结果',600,page=2,bold=True,size=10);tr=line('如表5.4所示，小规模与大规模不同。',650,page=2)
  ls=[c,h,a,b];figs=[Label('5.4',c,'body')];boxes=[(60,155,540,255)]
  if duplicate:
   c2=line('图5.5 同一模型风险值',400,bold=True,size=10);h2=line(h.text,450);a2=line(a.text,480);b2=line(b.text,510);ls.extend([c2,h2,a2,b2]);figs.append(Label('5.5',c2,'body'));boxes.append((60,435,540,535))
  return index(page(*ls,images=boxes,tables=boxes),page(r,t,tr,number=2,tables=((60,520,540,580),)),figures=figs,tables=[Label('5.4',t,'body')],trefs=[Label('5.4',tr,'body')])
 def test_symbolic_field_pairs_and_unique_model_names_prove_figure_table_use_without_changing_opposite_id(self):
  i=self.paired_matrix();out=self.repair(i);self.assertFalse(self.alarms(out,15));self.assertEqual(out.table_refs,i.table_refs);self.assertEqual(len(out.figures),1);self.assertEqual(len(out.tables),1)
 def test_same_values_assigned_to_wrong_fields_do_not_use_matrix_figure(self):
  self.assertEqual(len(self.alarms(self.repair(self.paired_matrix(swapped=True)),15)),1)
 def test_duplicate_model_field_matrices_do_not_take_same_untyped_evidence(self):
  self.assertEqual(len(self.alarms(self.repair(self.paired_matrix(duplicate=True)),15)),2)
 def test_native_cropped_and_nfkc_raw_reference_are_not_duplicated(self):
  raw=line('如图9.9所示，详见附录Z。');cropped=line('如图9.9所示,详见附录Z。',x=84,right=120)
  out=self.repair(index(page(raw),refs=[Label('9.9',cropped,'body')]))
  self.assertEqual(len(self.alarms(out,11)),1);self.assertEqual(out.figure_refs[0].line.bbox,cropped.bbox)
 def test_typed_appendix_qualifier_is_preserved_during_raw_reparse(self):
  r=line('另见附录A图1.1。');c=line('图1.1 附录A对象',400,page=2,bold=True,size=10);h=line('附录A 材料',80,page=2,bold=True)
  i=index(page(r),page(h,c,number=2),figures=[Label('1.1',c,'A')],refs=[Label('1.1',r,'body','A')]);out=self.repair(i);self.assertFalse(self.alarms(out,11));self.assertEqual(len(out.figure_refs),1)


 def test_heatmap_model_sentence_and_following_experiment_paragraph_share_context(self):
  c=line('图3.6 Method性能（1B模型，缓存512词元）',400,bold=True,size=10);model=line('在Llama-1B模型上开展实验，采用512的键值缓存。',450);r=line('实验所用文本形成210场景，一幅热力图对应全部场景，横轴表示文本长度。',485)
  i=index(page(c,model,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]);self.assertFalse(self.alarms(self.repair(i),15))
 def test_intervening_experiment_heading_blocks_heatmap_metadata_transfer(self):
  c=line('图3.6 Method性能（1B模型，缓存512词元）',400,bold=True,size=10);model=line('在Llama-1B模型上开展实验，采用512的键值缓存。',450);head=line('3.2 新的对照实验',473,bold=True);r=line('实验所用文本形成210场景，一幅热力图对应全部场景，横轴表示文本长度。',505)
  i=index(page(c,model,head,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]);self.assertEqual(len(self.alarms(self.repair(i),15)),1)


 def test_full_caption_extension_repeating_matrix_values_is_not_body_usage(self):
  from pdf_rules.mineru_layout import LayoutObject
  c=line('表3.8 模型比较',90,bold=True,size=10)
  d1=line('RVT-Base准确率0.874和0.920，AUC为0.912和0.939；RVT-Large准确率0.889和0.926，AUC为0.928和0.947。',115,size=10)
  d2=line('RVT-Large准确率0.889和0.926，AUC为0.928和0.947。',140,size=10)
  h=line('Model Accuracy AUC Accuracy AUC',210);a=line('RVT-Base 0.874 0.912 0.920 0.939',240);b=line('RVT-Large 0.889 0.928 0.926 0.947',270)
  i=index(page(c,d1,d2,h,a,b,tables=((60,190,540,290),)),tables=[Label('3.8',c,'body')])
  caption=LayoutObject('table_caption',1,(60,85,540,155),c.text+' '+d1.text+' '+d2.text,600,800)
  out=repair_reference_identity(i,[caption]);self.assertEqual([f['token'] for f in self.alarms(out,16)],['3.8']);self.assertEqual(len(out.tables),1)

if __name__=='__main__':unittest.main()

class SemanticReferenceFollowupTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 def test_two_named_paths_and_render_extract_predict_use_twin_architecture(self):
  cap=line('图4.1 DeepIM和CATRE的孪生网络迭代架构',400,bold=True,size=10)
  r=line('DeepIM把CAD渲染为图像，再提取观测和渲染特征并预测姿态增量；CATRE融合物体点云与形状先验来预测增量。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('4.1',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_one_of_two_named_architecture_paths_is_insufficient(self):
  cap=line('图4.1 DeepIM和CATRE的孪生网络迭代架构',400,bold=True,size=10)
  r=line('DeepIM把CAD渲染为图像，再提取观测和渲染特征并预测姿态增量。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('4.1',cap,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,15)],['4.1'])
 def test_deictic_architecture_describes_three_steps_and_unique_same_page_object(self):
  cap=line('图4.1 系统架构图',400,bold=True,size=10)
  r=line('系统先扫描信标并形成向量，再执行滤波与求解，将估计坐标返回客户端。该架构可以独立更新算法参数。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('4.1',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_architecture_topic_without_a_deictic_or_specific_name_is_insufficient(self):
  cap=line('图4.1 系统架构图',400,bold=True,size=10)
  r=line('另一个系统先扫描信标并形成向量，再执行滤波与求解，将估计坐标返回客户端。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('4.1',cap,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_specific_chinese_workflow_name_and_full_operations_use_diagram(self):
  cap=line('图2.2 潜空间扩散模型整体结构示意图',400,bold=True,size=10)
  r=line('潜空间扩散模型首先通过编码器映射图像，再在潜空间采样，最后经解码器重建像素图像。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('2.2',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_workflow_sentence_crossing_page_keeps_named_subject_and_operations(self):
  cap=line('图2.3 GraphLime可解释性流程图',400,page=2,bold=True,size=10)
  a=line('GraphLime在解释给',700);b=line('定节点时先采样邻近节点，拟合代理模型，并生成特征重要性解释。',100,page=2)
  out=self.repair(index(page(a),page(b,cap,number=2,images=((80,170,520,380),)),figures=[Label('2.3',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_complete_previous_sentence_does_not_lend_named_subject_across_page(self):
  cap=line('图2.3 GraphLime可解释性流程图',400,page=2,bold=True,size=10)
  a=line('其他算法包括GraphLime。',700);b=line('本文模型先采样邻近节点，拟合代理模型，并生成特征重要性解释。',100,page=2)
  out=self.repair(index(page(a),page(b,cap,number=2,images=((80,170,520,380),)),figures=[Label('2.3',cap,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_sentence_continuation_in_same_paragraph_keeps_functional_chain(self):
  cap=line('图3.5 FFT分支生成掩膜的模型示意图',400,bold=True,size=10)
  a=line('FFT分支把空间特征映射到频域。',460,x=100,right=520)
  b=line('随后提取频谱，与空间特征拼接后供解码器重建掩膜。',490,x=80,right=520)
  out=self.repair(index(page(cap,a,b,images=((80,170,520,380),)),figures=[Label('3.5',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_new_indented_paragraph_blocks_functional_chain_transfer(self):
  cap=line('图3.5 FFT分支生成掩膜的模型示意图',400,bold=True,size=10)
  a=line('FFT分支把空间特征映射到频域。',460,x=80,right=520)
  b=line('随后另一方法提取频谱，与空间特征拼接后供解码器重建掩膜。',490,x=110,right=520)
  out=self.repair(index(page(cap,a,b,images=((80,170,520,380),)),figures=[Label('3.5',cap,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_named_workflow_requires_described_functional_steps(self):
  cap=line('图2.1 GraphSAGE采样与聚合过程示意图',400,bold=True,size=10)
  r=line('GraphSAGE对邻居均匀采样，将邻居特征聚合后更新节点状态。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('2.1',cap,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_method_name_alone_does_not_use_workflow(self):
  cap=line('图2.1 GraphSAGE采样与聚合过程示意图',400,bold=True,size=10)
  r=line('GraphSAGE是一种常用的图神经网络方法。')
  out=self.repair(index(page(cap,r,images=((80,170,520,380),)),figures=[Label('2.1',cap,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,15)],['2.1'])
 def test_two_physical_workflows_with_same_name_remain_ambiguous(self):
  a=line('图2.1 GraphSAGE采样与聚合过程示意图',250,bold=True,size=10);b=line('图2.2 GraphSAGE采样与聚合过程示意图',600,bold=True,size=10)
  r=line('GraphSAGE对邻居采样，将邻居特征聚合后更新节点状态。',680)
  out=self.repair(index(page(a,b,r,images=((80,100,520,230),(80,430,520,580))),figures=[Label('2.1',a,'body'),Label('2.2',b,'body')]))
  self.assertEqual(len(self.alarms(out,15)),2)
 def test_workflow_explanation_does_not_use_same_named_accuracy_chart(self):
  a=line('图2.1 GraphSAGE采样与聚合过程示意图',250,bold=True,size=10);b=line('图2.2 GraphSAGE准确率结果曲线',600,bold=True,size=10)
  r=line('GraphSAGE对邻居采样，将邻居特征聚合后更新节点状态。',680)
  out=self.repair(index(page(a,b,r,images=((80,100,520,230),(80,430,520,580))),figures=[Label('2.1',a,'body'),Label('2.2',b,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,15)],['2.2'])
 def test_api_table_parent_extent_supplies_two_called_function_rows(self):
  from pdf_rules.mineru_layout import LayoutObject
  cap=line('表5.4 实体抽取模块接口表',120,bold=True,size=10)
  cells=[line('接口名称 输入参数 说明',155,role='table'),line('extract_entities() text: str 抽取实体',185,role='table'),line('normalize_entities() normalize_values: bool 规范化',250,role='table')]
  r=line('通过extract_entities()接口处理输入文本，再调用normalize_entities()接口执行实体规范化。',500)
  i=index(page(cap,*cells,r,tables=((80,145,520,215),)),tables=[Label('5.4',cap,'body')])
  events=[];out=repair_reference_identity(i,[LayoutObject('table',1,(80,145,520,290),'',600,800)],evidence=events)
  self.assertFalse(self.alarms(out,16));self.assertEqual(len(out.tables),1)
  self.assertTrue(any(e['action']=='add_reference' and '接口' in e['criterion'] for e in events))
 def test_api_table_own_cells_do_not_establish_body_usage(self):
  from pdf_rules.mineru_layout import LayoutObject
  cap=line('表5.4 实体抽取模块接口表',120,bold=True,size=10)
  cells=[line('extract_entities() 输入文本',185),line('normalize_entities()规范化',250)]
  out=repair_reference_identity(index(page(cap,*cells,tables=((80,145,520,215),)),tables=[Label('5.4',cap,'body')]),[LayoutObject('table',1,(80,145,520,290),'',600,800)])
  self.assertEqual([x['token'] for x in self.alarms(out,16)],['5.4'])
 def test_one_api_name_shared_by_two_tables_is_not_usage_proof(self):
  cap=line('表5.4 实体抽取模块接口表',120,bold=True,size=10);cell=line('extract_entities() 输入文本',185,role='table')
  r=line('调用extract_entities()接口处理输入文本。',500)
  out=self.repair(index(page(cap,cell,r,tables=((80,145,520,250),)),tables=[Label('5.4',cap,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,16)],['5.4'])
 def test_named_dataset_row_and_two_exact_large_counts_establish_usage(self):
  cap=line('表5.1 数据集统计',120,bold=True,size=10);head=line('数据集 训练集 测试集',155,role='table');cell=line('MedQA 10178 1131',185,role='table')
  r=line('MedQA数据集包含10,178个训练问题和1,131个测试问题。',500)
  out=self.repair(index(page(cap,head,cell,r,tables=((80,145,520,240),)),tables=[Label('5.1',cap,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_same_counts_for_other_named_dataset_are_not_usage(self):
  cap=line('表5.1 数据集统计',120,bold=True,size=10);head=line('数据集 训练集 测试集',155,role='table');cell=line('MedQA 10178 1131',185,role='table')
  r=line('OtherQA包含10,178个训练问题和1,131个测试问题。',500)
  out=self.repair(index(page(cap,head,cell,r,tables=((80,145,520,240),)),tables=[Label('5.1',cap,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,16)],['5.1'])
 def test_common_counts_do_not_prove_use_of_named_dataset_table(self):
  cap=line('表5.1 数据集统计',120,bold=True,size=10);head=line('数据集 训练集 测试集',155,role='table');cell=line('MedQA 10 20',185,role='table')
  r=line('MedQA通常随机划分10个训练问题和20个测试问题。',500)
  out=self.repair(index(page(cap,head,cell,r,tables=((80,145,520,240),)),tables=[Label('5.1',cap,'body')]))
  self.assertEqual([x['token'] for x in self.alarms(out,16)],['5.1'])


 def test_three_error_columns_and_two_named_rows_with_exact_location_are_used(self):
  c=line('表5.2 自习区域定位结果',120,bold=True,size=10);h=line('平均误差 中位数误差 前90%误差',155,role='table');a=line('指纹定位 3.69 3.54 5.48',185,role='table');b=line('传播模型定位 4.01 4.10 5.56',215,role='table')
  r=line('可以看到，自习区域的指纹定位平均误差、中位数误差和90%误差均小于传播模型定位。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('5.2',c,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_location_and_row_names_without_columns_do_not_use_result_table(self):
  c=line('表5.2 自习区域定位结果',120,bold=True,size=10);h=line('平均误差 中位数误差 前90%误差',155,role='table');a=line('指纹定位 3.69 3.54 5.48',185,role='table');b=line('传播模型定位 4.01 4.10 5.56',215,role='table')
  r=line('自习区域实验比较指纹定位与传播模型定位，这两种算法各有优点。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('5.2',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)
 def test_specific_comparison_location_does_not_use_neighbouring_other_region(self):
  c=line('表5.2 自习区域定位结果',120,bold=True,size=10);h=line('平均误差 中位数误差 前90%误差',155,role='table');a=line('指纹定位 3.69 3.54 5.48',185,role='table');b=line('传播模型定位 4.01 4.10 5.56',215,role='table')
  r=line('可以看到，书架区域的指纹定位平均误差、中位数误差和90%误差均小于传播模型定位。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('5.2',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)
 def test_named_interval_rows_are_used_only_with_their_own_bounds(self):
  c=line('表4.2 严重度映射规则',120,bold=True,size=10);h=line('严重度等级 z-score 范围',155,role='table')
  a=line('mild 1 ≤|z| < 1.5',185,role='table');b=line('moderate 1.5 ≤|z| < 2',215,role='table');d=line('significant 2 ≤|z| < 3',245,role='table');e=line('profound |z| ≥3',275,role='table')
  r=line('严重度划分为mild（1≤|z|<1.5）、moderate（1.5≤|z|<2）、significant（2≤|z|<3）与profound（|z|≥3）。',500)
  out=self.repair(index(page(c,h,a,b,d,e,r,tables=((80,145,520,300),)),tables=[Label('4.2',c,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_same_interval_values_assigned_to_other_grade_names_do_not_prove_use(self):
  c=line('表4.2 严重度映射规则',120,bold=True,size=10);h=line('严重度等级 z-score 范围',155,role='table')
  a=line('mild 1 ≤|z| < 1.5',185,role='table');b=line('moderate 1.5 ≤|z| < 2',215,role='table');d=line('significant 2 ≤|z| < 3',245,role='table');e=line('profound |z| ≥3',275,role='table')
  r=line('严重度划分为profound（1≤|z|<1.5）、significant（1.5≤|z|<2）、moderate（2≤|z|<3）与mild（|z|≥3）。',500)
  out=self.repair(index(page(c,h,a,b,d,e,r,tables=((80,145,520,300),)),tables=[Label('4.2',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)

 def test_curve_named_condition_and_two_legend_methods_are_body_usage(self):
  c=line('图4.2 cSBM同质性性能曲线',400,bold=True,size=10);a=line('GCN BGRL GraphACL',230,role='figure')
  r=line('图4.1显示了cSBM上的同质性性能曲线，GCN和BGRL在低同质性区准确率低，随同质性增加迅速提升。')
  i=index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('4.2',c,'body')],refs=[Label('4.1',r,'body')]);out=self.repair(i)
  self.assertFalse(self.alarms(out,15));self.assertEqual([x['token'] for x in self.alarms(out,11)],['4.1'])
 def test_names_and_common_median_do_not_use_prompt_length_histogram(self):
  c=line('图3.4 Prompt长度直方图',400,bold=True,size=10);a=line('DatasetA DatasetB Median 14',230,role='figure')
  r=line('DatasetA与DatasetB是本文使用的数据集，另一组统计的中位数是14。')
  out=self.repair(index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('3.4',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_specific_ui_function_description_uses_unique_visualization_interface(self):
  c=line('图5.3 实体关系抽取模块可视化界面',400,bold=True,size=10)
  r=line('图谱可视化采用力导向布局，展现节点重要性和关系置信度；搜索功能可以从一个实体探索指定跳数的关联网络。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('5.3',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_two_same_visualization_interfaces_cannot_claim_one_function_description(self):
  a=line('图5.3 实体关系抽取模块可视化界面',250,bold=True,size=10);b=line('图5.4 实体关系抽取模块可视化界面',600,bold=True,size=10)
  r=line('图谱可视化采用力导向布局，展现节点重要性和关系置信度；搜索功能可以从一个实体探索指定跳数的关联网络。',680)
  out=self.repair(index(page(a,b,r,images=((80,100,520,230),(80,430,520,580))),figures=[Label('5.3',a,'body'),Label('5.4',b,'body')]))
  self.assertEqual(len(self.alarms(out,15)),2)
 def test_two_physical_encoder_decoder_labels_and_restoration_operations_use_diagram(self):
  c=line('图4.6 恢复学习示意图',400,bold=True,size=10);a=line('图像编码器 图像解码器',220,role='figure');b=line('文本编码器 文本解码器',250,role='figure')
  r=line('恢复学习分别提取影像和文本表征，由影像解码器重构图像，再由文本解码器重构文本，采用两个独立损失。')
  out=self.repair(index(page(c,a,b,r,images=((80,170,520,380),)),figures=[Label('4.6',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_source_specific_api_names_and_reserve_create_map_operations_use_memory_diagram(self):
  c=line('图2.3 GPU虚拟内存管理机制示意图',400,bold=True,size=10);a=line('cuMemCreate cuMemMap cuMemSetAccess',220,role='figure')
  r=line('GPU VMM先预留地址范围，再调用cuMemCreate创建物理内存，随后用cuMemMap映射，并通过cuMemSetAccess设置访问权限。',100,page=4)
  out=self.repair(index(page(c,a,images=((80,170,520,380),)),page(r,number=4),figures=[Label('2.3',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_one_memory_api_identifier_does_not_use_a_diagram(self):
  c=line('图2.3 GPU虚拟内存管理机制示意图',400,bold=True,size=10);a=line('cuMemCreate cuMemMap cuMemSetAccess',220,role='figure')
  r=line('cuMemCreate用于创建物理内存。',100,page=4)
  out=self.repair(index(page(c,a,images=((80,170,520,380),)),page(r,number=4),figures=[Label('2.3',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)

 def test_experiment_number_and_two_bound_columns_select_one_physical_table(self):
  c=line('表3.5 不同卷积核与空洞率组合的性能',120,bold=True,size=10);h=line('实验 卷积核 激活函数 准确率 F1',155,role='table');a=line('10 5x5 GELU 90.1 0.889',185,role='table')
  d=line('表3.6 另一实验性能',350,bold=True,size=10);dh=line(h.text,385,role='table');da=line('3 5x5 GELU 90.1 0.889',415,role='table')
  r=line('实验10采用5x5与GELU，准确率90.1%，F1分数0.889。',600)
  i=index(page(c,h,a,d,dh,da,r,tables=((80,145,520,240),(80,375,520,470))),tables=[Label('3.5',c,'body'),Label('3.6',d,'body')]);out=self.repair(i)
  self.assertEqual([x['token'] for x in self.alarms(out,16)],['3.6'])
 def test_two_metric_values_without_the_experiment_identity_remain_insufficient(self):
  c=line('表3.5 不同卷积核与空洞率组合的性能',120,bold=True,size=10);h=line('实验 卷积核 激活函数 准确率 F1',155,role='table');a=line('10 5x5 GELU 90.1 0.889',185,role='table')
  r=line('某模型的准确率90.1%，F1分数0.889。',600)
  out=self.repair(index(page(c,h,a,r,tables=((80,145,520,240),)),tables=[Label('3.5',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)
 def test_two_named_dataset_scalar_results_bind_their_metric_columns(self):
  c=line('表4.1 IID基准结果',120,bold=True,size=10);h=line('Dataset Model RMSE MAE R2',155,role='table');a=line('Data-A Model-X 3.5631 2.5614 0.8630',185,role='table');b=line('Data-B Model-Y 8.0951 5.4205 0.8513',215,role='table')
  r=line('Data-A的Model-X达到MAE2.5614，Data-B的Model-Y达到MAE5.4205。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('4.1',c,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_values_bound_to_wrong_metric_columns_do_not_prove_use(self):
  c=line('表4.1 IID基准结果',120,bold=True,size=10);h=line('Dataset Model RMSE MAE R2',155,role='table');a=line('Data-A Model-X 3.5631 2.5614 0.8630',185,role='table');b=line('Data-B Model-Y 8.0951 5.4205 0.8513',215,role='table')
  r=line('Data-A的Model-X达到RMSE2.5614，Data-B的Model-Y达到RMSE5.4205。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('4.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)

 def test_structured_schema_definitions_use_three_field_rows_and_enumerations(self):
  c=line('表4.1 临床输出字段及可信约束',120,bold=True,size=10);h=line('输出字段 形式 约束',155,role='table');a=line('Reasoning 自然语言文本',185,role='table');b=line('Diagnosis CN MCI AD',215,role='table');d=line('Confidence High Medium Low',245,role='table')
  r=line('输出R为Reasoning自然语言文本，D为Diagnosis诊断类别，采用CN、MCI、AD；S为Confidence等级，取High、Medium、Low。',500)
  out=self.repair(index(page(c,h,a,b,d,r,tables=((80,145,520,280),)),tables=[Label('4.1',c,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_shared_schema_names_without_definitions_do_not_use_field_table(self):
  c=line('表4.1 临床输出字段及可信约束',120,bold=True,size=10);h=line('输出字段 形式 约束',155,role='table');a=line('Reasoning 自然语言文本',185,role='table');b=line('Diagnosis CN MCI AD',215,role='table');d=line('Confidence High Medium Low',245,role='table')
  r=line('本文讨论Reasoning、Diagnosis与Confidence，也涉及MCI以及High、Medium、Low标签。',500)
  out=self.repair(index(page(c,h,a,b,d,r,tables=((80,145,520,280),)),tables=[Label('4.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)
 def test_three_chosen_models_and_their_hidden_dimension_comparison_use_config_table(self):
  c=line('表5.3 基座模型配置对比',120,bold=True,size=10);h=line('模型 参数量 层数 隐藏维度',155,role='table');a=line('ChatGLM-6B 6.2 28 4096',185,role='table');b=line('LLaMA-8B 8 32 4096',215,role='table');d=line('Qwen-7B 7.6 28 3584',245,role='table')
  r=line('选取ChatGLM-6B、LLaMA-8B和Qwen-7B作为基座模型；Qwen-7B的隐藏层状态小于上述两个模型。',500)
  out=self.repair(index(page(c,h,a,b,d,r,tables=((80,145,520,280),)),tables=[Label('5.3',c,'body')]))
  self.assertFalse(self.alarms(out,16))
 def test_model_list_without_configuration_property_is_insufficient(self):
  c=line('表5.3 基座模型配置对比',120,bold=True,size=10);h=line('模型 参数量 层数 隐藏维度',155,role='table');a=line('ChatGLM-6B 6.2 28 4096',185,role='table');b=line('LLaMA-8B 8 32 4096',215,role='table');d=line('Qwen-7B 7.6 28 3584',245,role='table')
  r=line('选取ChatGLM-6B、LLaMA-8B和Qwen-7B作为基座模型进行实验。',500)
  out=self.repair(index(page(c,h,a,b,d,r,tables=((80,145,520,280),)),tables=[Label('5.3',c,'body')]))
  self.assertEqual(len(self.alarms(out,16)),1)
 def test_chart_specific_model_two_caption_factors_and_detailed_curve_use(self):
  c=line('图3.16 RVT不同嵌入维度和特征层数对准确率的影响',400,bold=True,size=10)
  r=line('RVT的嵌入维度和特征层数与准确率关联曲线表明，维度从512到768提升2.1%，1536继续提升，2048饱和；层数从8到11提升2.1%，13到14仅提升0.2%。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.16',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_one_common_chart_number_and_model_name_cannot_prove_use(self):
  c=line('图3.16 RVT不同嵌入维度和特征层数对准确率的影响',400,bold=True,size=10)
  r=line('RVT的准确率与模型规模相关，另一项实验采用768维，性能较好。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.16',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)

 def test_named_english_workflow_requires_actual_three_step_description(self):
  c=line('Figure 3.6 The LMVQ framework comprises quality-aware feature encoders.',400,bold=True,size=10)
  r=line('LMVQ extracts quality-aware features using four encoders, then processes and aligns the representations before prediction.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_english_workflow_name_without_operations_is_insufficient(self):
  c=line('Figure 3.6 The LMVQ framework comprises quality-aware feature encoders.',400,bold=True,size=10)
  r=line('LMVQ is a quality metric used in this research.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.6',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_dense_layer_concrete_connection_operations_use_physical_illustration(self):
  c=line('Figure 2.4 An illustration showing several dense layers interconnected.',400,bold=True,size=10)
  r=line('Fully connected or dense layers connect every neuron to each neuron in the previous layer. The feature vector is flattened and fed into dense layers for final classification.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.4',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_dense_layer_name_without_actual_connectivity_does_not_use_illustration(self):
  c=line('Figure 2.4 An illustration showing several dense layers interconnected.',400,bold=True,size=10)
  r=line('Dense layers are common neural network components used in many models.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.4',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_bare_english_number_and_specific_image_predicate_use_target(self):
  c=line('Figure 4.1 AI-generated images with exaggerated or surreal contents.',400,bold=True,size=10)
  r=line('As 4.1 showcases, AI-generated images may contain exaggerated or surreal contents.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('4.1',c,'body')]))
  self.assertFalse(self.alarms(out,15))
 def test_same_numbered_section_presenting_a_topic_is_not_a_figure_pointer(self):
  c=line('Figure 4.1 AI-generated images with exaggerated or surreal contents.',400,bold=True,size=10)
  r=line('Section 4.1 presents a study of exaggerated or surreal contents.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('4.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)

 def test_html_superscript_is_not_a_workflow_name(self):
  from pdf_rules.mineru_layout import LayoutObject
  c=line('图2.1 GraphSAGE采样与聚合过程示意图',400,bold=True,size=10);r=line('GraphSAGE先采样邻居，再聚合特征，最后更新节点。')
  obj=LayoutObject('figure_caption',1,(60,395,540,420),'图2.1 GraphSAGE采样与聚合过程示意图<sup>[10]</sup>',600,800)
  out=repair_reference_identity(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]),[obj]);self.assertFalse(self.alarms(out,15))
 def test_native_wrapped_title_with_english_caption_extent_keeps_workflow_identity(self):
  from pdf_rules.mineru_layout import LayoutObject
  c=line('图2.3 DiagESC诊断生成与校验合成流',400,bold=True,size=10);z=line('程。',414,x=60,right=95,size=10);e=line('Figure 2.3 DiagESC synthesis pipeline.',428,bold=True,size=10)
  r=line('DiagESC支持问询，合成诊断对话，再生成建议并校验结果。')
  obj=LayoutObject('figure_caption',1,(55,395,545,445),'Figure 2.3 DiagESC synthesis pipeline.',600,800)
  out=repair_reference_identity(index(page(c,z,e,r,images=((80,170,520,380),)),figures=[Label('2.3',c,'body'),Label('2.3',e,'body')]),[obj]);self.assertFalse(self.alarms(out,15));self.assertEqual(len(out.figures),1)
 def test_math_italic_r2_does_not_shift_mae_and_rmse_column_binding(self):
  c=line('表4.1 IID基准结果',120,bold=True,size=10);h=line('Dataset Model RMSE MAE 𝑅2',155,role='table');a=line('Data-A Model-X 3.5631 2.5614 0.8630',185,role='table');b=line('Data-B Model-Y 8.0951 5.4205 0.8513',215,role='table')
  r=line('Data-A的Model-X达到MAE2.5614，Data-B的Model-Y达到MAE5.4205。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('4.1',c,'body')]));self.assertFalse(self.alarms(out,16))
 def test_math_italic_header_does_not_accept_values_under_wrong_columns(self):
  c=line('表4.1 IID基准结果',120,bold=True,size=10);h=line('Dataset Model RMSE MAE 𝑅2',155,role='table');a=line('Data-A Model-X 3.5631 2.5614 0.8630',185,role='table');b=line('Data-B Model-Y 8.0951 5.4205 0.8513',215,role='table')
  r=line('Data-A的Model-X达到MAE0.8630，Data-B的Model-Y达到MAE0.8513。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('4.1',c,'body')]));self.assertEqual(len(self.alarms(out,16)),1)
 def test_verifier_functional_framework_requires_actual_closed_loop(self):
  c=line('图2.6 可验证医学推理的验证器驱动两阶段训练框架',400,bold=True,size=10);r=line('验证器驱动的框架包括两个环节：首先搜索推理轨迹并利用验证器反馈筛选；随后将验证器作为奖励进行强化训练。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.6',c,'body')]));self.assertFalse(self.alarms(out,15))
 def test_concrete_qualitative_detection_results_use_named_visualization(self):
  c=line('图3.9 像素级分割和边缘游离细胞检测可视化图',400,bold=True,size=10);r=line('边缘游离细胞目标检测先分割实例并提取中心，再聚类筛选孤立细胞。定性实验结果表明，目标框已经检测到游离细胞，减少误判。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.9',c,'body')]));self.assertFalse(self.alarms(out,15))
 def test_generic_qualitative_word_does_not_use_specific_detection_visualization(self):
  c=line('图3.9 像素级分割和边缘游离细胞检测可视化图',400,bold=True,size=10);r=line('另一类目标先分割再聚类筛选。定性实验结果表明，目标框显示良好。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.9',c,'body')]));self.assertEqual(len(self.alarms(out,15)),1)
 def test_native_ema_momentum_encoder_and_update_description_use_diagram(self):
  c=line('图4.5 跨模态对比学习示意图',400,bold=True,size=10);a=line('动量 EMA 编码器 对比损失',220,role='figure');r=line('为稳定对比学习，引入动量编码器并维护特征队列，采用指数滑动平均EMA更新编码器参数。')
  out=self.repair(index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('4.5',c,'body')]));self.assertFalse(self.alarms(out,15))
 def test_ema_name_alone_does_not_use_encoder_diagram(self):
  c=line('图4.5 跨模态对比学习示意图',400,bold=True,size=10);a=line('动量 EMA 编码器 对比损失',220,role='figure');r=line('对比学习中也可使用EMA。')
  out=self.repair(index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('4.5',c,'body')]));self.assertEqual(len(self.alarms(out,15)),1)
 def test_ablation_names_actual_metrics_and_decline_use_quantitative_table(self):
  c=line('表3.2 方法一在不同消融设置下的定量结果',120,bold=True,size=10);h=line('SSIM PSNR',155,role='table');a=line('w/o T1 0.44 14.9',185,role='table');b=line('w/o CINE 0.38 14.3',215,role='table');d=line('w/o pretrain 0.45 15.9',245,role='table');r=line('方法一的消融实验结果表明，去除T1和CINE条件时SSIM与PSNR出现明显下降；w/o pretrain整体指标退化。',500)
  out=self.repair(index(page(c,h,a,b,d,r,tables=((80,145,520,280),)),tables=[Label('3.2',c,'body')]));self.assertFalse(self.alarms(out,16))
 def test_same_ablation_names_do_not_use_other_named_methods_table(self):
  c=line('表3.2 方法二在不同消融设置下的定量结果',120,bold=True,size=10);h=line('SSIM PSNR',155,role='table');a=line('w/o T1 0.44 14.9',185,role='table');b=line('w/o CINE 0.38 14.3',215,role='table');r=line('方法一的消融实验结果表明，去除T1和CINE条件时SSIM与PSNR出现明显下降。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,250),)),tables=[Label('3.2',c,'body')]));self.assertEqual(len(self.alarms(out,16)),1)
 def test_ablation_visuals_require_removed_conditions_and_image_degradation(self):
  c=line('图3.4 方法一在不同消融设置下的主观效果对比图',400,bold=True,size=10);a=line('w/o T1 w/o CINE w/o pretrain',220,role='figure');r=line('方法一消融结果表明，去除T1时边界模糊，去除CINE时局部纹理减弱，w/o pretrain出现伪影和纹理不连贯。')
  out=self.repair(index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('3.4',c,'body')]));self.assertFalse(self.alarms(out,15))
 def test_ablation_numeric_comparison_does_not_use_visual_results(self):
  c=line('图3.4 方法一在不同消融设置下的主观效果对比图',400,bold=True,size=10);a=line('w/o T1 w/o CINE w/o pretrain',220,role='figure');r=line('方法一消融结果表明，去除T1和CINE条件时SSIM与PSNR下降。')
  out=self.repair(index(page(c,a,r,images=((80,170,520,380),)),figures=[Label('3.4',c,'body')]));self.assertEqual(len(self.alarms(out,15)),1)
 def test_dataset_name_and_numbers_without_train_test_columns_do_not_use_examples(self):
  c=line('表A.5 Joomla示例',120,bold=True,size=10);h=line('请求ID 响应ID',155,role='table');a=line('Joomla 10178 1131',185,role='table');r=line('Joomla数据集的训练样本10178条，测试样本1131条。',500)
  out=self.repair(index(page(c,h,a,r,tables=((80,145,520,240),)),tables=[Label('A.5',c,'body')]));self.assertEqual(len(self.alarms(out,16)),1)


class PhysicalIndirectReferenceBindingTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 def duplicate_figures(self, explicit=False):
  old=line('Figure 3.3 Distribution of CATE estimates.',400,page=1,bold=True,size=10)
  new=line('Figure 3.3 CCL model architecture.',400,page=3,bold=True,size=10)
  body=line('CCL extracts features, trains the conformal model and predicts confidence intervals.',100,page=3)
  if explicit:body=line('As Figure 3.3 shows, CCL extracts features, trains the model and predicts intervals.',100,page=3)
  return index(page(old,number=1,images=((80,170,520,380),)),page(new,body,number=3,images=((80,170,520,380),)),figures=[Label('3.3',old,'body'),Label('3.3',new,'body')])
 def test_indirect_architecture_use_does_not_credit_distinct_same_number_histogram(self):
  out=self.repair(self.duplicate_figures())
  self.assertEqual([(f['token'],f['page']) for f in self.alarms(out,15)],[('3.3',1)])
  self.assertEqual(len(out.figures),2)
 def test_physical_binding_survives_a_second_repair(self):
  once=self.repair(self.duplicate_figures());twice=self.repair(once)
  self.assertEqual(self.alarms(once,15),self.alarms(twice,15))
  self.assertTrue(getattr(twice,'indirect_reference_targets',{}))
 def test_explicit_typed_number_keeps_original_number_resolution(self):
  self.assertFalse(self.alarms(self.repair(self.duplicate_figures(True)),15))
 def test_unbound_graphic_reference_cannot_credit_two_distinct_physical_targets(self):
  i=self.duplicate_figures();i.graphic_figure_refs=[Label('3.3',i.document.pages[1].lines[1],'body')]
  self.assertEqual(len(self.alarms(i,15)),2)
 def test_unbound_graphic_reference_can_still_credit_a_unique_physical_target(self):
  c=line('图3.3 独立模型',400,bold=True,size=10);r=line('本模型预测区间。')
  i=index(page(c,r,images=((80,170,520,380),)),figures=[Label('3.3',c,'body')]);i.graphic_figure_refs=[Label('3.3',r,'body')]
  self.assertFalse(self.alarms(i,15))
 def test_table_values_bind_only_the_physical_table_they_describe(self):
  a=line('表4.1 IID实验',120,page=1,bold=True,size=10);h=line('Dataset Model RMSE MAE R2',155,page=1,role='table');x=line('Data-A Model-X 9.8 7.6 0.12',185,page=1,role='table');y=line('Data-B Model-Y 6.5 4.3 0.23',215,page=1,role='table')
  b=line('表4.1 IID实验',120,page=3,bold=True,size=10);h2=line('Dataset Model RMSE MAE R2',155,page=3,role='table');x2=line('Data-A Model-X 3.5631 2.5614 0.8630',185,page=3,role='table');y2=line('Data-B Model-Y 8.0951 5.4205 0.8513',215,page=3,role='table');r=line('Data-A的Model-X达到MAE2.5614，Data-B的Model-Y达到MAE5.4205。',500,page=3)
  out=self.repair(index(page(a,h,x,y,number=1,tables=((80,145,520,240),)),page(b,h2,x2,y2,r,number=3,tables=((80,145,520,240),)),tables=[Label('4.1',a,'body'),Label('4.1',b,'body')]))
  self.assertEqual([(f['token'],f['page']) for f in self.alarms(out,16)],[('4.1',1)])
 def assert_weak_description_stays_unreferenced(self,title,body,inside=''):
  c=line('图2.1 '+title,400,bold=True,size=10);r=line(body);parts=[c,r]
  if inside:parts.append(line(inside,220,role='figure'))
  out=self.repair(index(page(*parts,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
  self.assertEqual(len(out.figures),1)
 def test_generic_encoder_only_deictic_does_not_use_six_layer_translation_diagram(self):
  self.assert_weak_description_stays_unreferenced('Transformer模型架构','该架构的模型变体ALBERT通过参数分解处理文本并提取信息，DistilBERT分类和预测语义。','Encoder Decoder 6 layers 我有一只猫 I have a cat')
 def test_hsi_method_operations_do_not_use_specific_stain_example_panels(self):
  self.assert_weak_description_stays_unreferenced('基于HSI色彩空间的染色增强与域偏移示意图','HSI染色增强方法提取组织特征并分割血管，预测Ki67标记物；转换色彩空间再处理图像。','H1 S1 I1 H2 S2 I2')
 def test_entropy_prior_theory_does_not_use_specific_gland_examples(self):
  self.assert_weak_description_stays_unreferenced('组织腺体区域的结构信息熵先验','结构信息熵先验通过组织腺体区域提取特征，计算分布，再处理并分割细胞。','原始图像 图像块 高熵 低熵')
 def test_generic_module_operations_do_not_use_full_sampling_framework(self):
  self.assert_weak_description_stays_unreferenced('序列重排序模块和滑动窗口扫描线组织病理学采样框架','组织病理学采样采用LSH过滤和DINOv2提取特征，SRU模块通过滑动窗口重建空间，再处理序列。','TokenFilter SequenceAdaptor SurvivalAnalysis')
 def test_attention_theory_does_not_use_sparse_heads_and_window_example(self):
  self.assert_weak_description_stays_unreferenced('滑动窗口采样和稀疏注意力示意图','滑动窗口采样和稀疏注意力通过QKV投影计算权重并提取特征，分类和预测结果。','SlidingWindow SparseHeads Concat Scaling ChannelAttention')
 def test_sparse_format_definitions_do_not_use_specific_encoding_matrix(self):
  self.assert_weak_description_stays_unreferenced('常见稀疏编码数据格式示意图','常见稀疏编码数据格式中CSR聚合行数据，CSC处理列数据，COO计算乘积并映射索引，BSR优化分块。','ELL DIA COO CSR ptr offset 1 2 3 4 5 6 7 8')


class ConcreteWorkflowRecoveryTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 def expect_used(self,title,body,inside=''):
  c=line('图2.1 '+title,400,bold=True,size=10);r=line(body);parts=[c,r]
  if inside:parts.append(line(inside,220,role='figure'))
  out=self.repair(index(page(*parts,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]))
  self.assertFalse(self.alarms(out,15));self.assertEqual(len(out.figures),1)
 def test_generic_architecture_deictic_and_complete_client_server_chain(self):
  self.expect_used('系统架构图','系统采用客户端-服务器架构：客户端扫描信标形成RSSI向量；服务器滤波并计算位置，将估计坐标返回客户端。该架构可以更新算法。')
 def test_annotation_protocol_defines_complete_ordered_pair_options(self):
  self.expect_used('RLHF标注示意图','RLHF采用pair标注，每个prompt生成两个response，标注A4,A3,A2,A1,B1,B2,B3,B4八档偏好，A表示回答A优于B，数字越大偏好越强，训练前过滤低强度数据。','A4 A3 A2 A1 B1 B2 B3 B4')
 def test_two_level_retrieval_explains_summary_then_body_matching(self):
  self.expect_used('层级检索结构','层级检索先生成问题向量并匹配摘要，筛选论文子集；第二阶段将正文段落嵌入后再精细匹配，返回最终结果。','L1 摘要 L0 正文')
 def test_full_multihead_attention_name_and_operations(self):
  self.expect_used('多头注意力','多头注意力先投影查询键和值，拆分多个并行头，计算注意力后拼接各头并执行线性映射。','Q K V Linear Scaled Dot-Product Attention Concat Linear')
 def test_diffusion_explains_both_directional_state_chains(self):
  self.expect_used('扩散模型前向与反向过程示意图','扩散模型前向过程从原始输入逐步加入高斯噪声直至纯噪声，反向过程学习去噪，通过预测噪声逐步重建原始图像。','x0 x1 xt xT q p')
 def test_named_two_branch_dit_structure(self):
  self.expect_used('SD3系列模型中的MM-DiT结构示意','MM-DiT分别投影文本和图像，独立参数处理两路特征，在共享注意力中拼接交互并更新。')
 def test_named_static_masked_autoencoder_structure(self):
  self.expect_used('ViTMAE结构与时空遮挡示意图','ViT-MAE先映射二维patch并随机遮挡，编码器处理少量可见patch，解码器重建完整静态图像。')
 def test_named_video_masked_autoencoder_structure(self):
  self.expect_used('VideoMAE结构与时空遮挡示意图','VideoMAE将连续视频划分为tubelet patch，随机遮挡90%，编码可见片段后由解码器重建完整视频。')
 def test_recovery_learning_names_both_modality_decoder_branches(self):
  self.expect_used('恢复学习示意图','恢复学习分别编码影像和文本；影像解码器重建像素并用MSE计算损失，文本解码器恢复证据文本并用token交叉熵训练。','影像解码器 文本解码器 重构损失')
 def test_named_module_uses_concrete_graph_operations(self):
  self.expect_used('Diagram of our proposed GFTE module','GFTE constructs a temporal graph, computes its Laplacian, normalizes the matrix and extracts Fourier features before reconstruction.')
 def test_preprocessing_workflow_uses_three_distinct_qc_operations(self):
  self.expect_used('Data Pre-processing Workflow','Data preprocessing removes duplicates and handles missing observations through interpolation, then detects outliers and standardizes the clean data for model training.')
 def test_postfix_number_with_exact_distinctive_image_content(self):
  self.expect_used('The AI-generated images with exaggerated or surreal features','The generated images may contain exaggerated or surreal features 2.1.')
 def test_captionless_numbered_section_is_not_postfix_image_use(self):
  c=line('Figure 2.1 The AI-generated images with exaggerated or surreal features',400,bold=True,size=10);r=line('The section discusses exaggerated or surreal features in Chapter 2.1.')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)
 def test_vertical_caption_binds_only_unique_prepared_large_workflow(self):
  from pdf_rules.mineru_layout import LayoutObject
  c=PdfLine(1,'Figure 3.6 The LMVQ framework comprises four essential modules.',(480,100,494,700),600,800,bold=True,font_size=10,direction=(0.,1.))
  r=line('LMVQ extracts features through four encoders, transforms their tokens, aligns dimensional features and predicts video quality.',100,page=2)
  visual=LayoutObject('figure',1,(160,180,370,720),'',600,800);cap=LayoutObject('figure_caption',1,c.bbox,c.text,600,800)
  out=repair_reference_identity(index(page(c,number=1,graphics=(visual.bbox,)),page(r,number=2),figures=[Label('3.6',c,'body')]),[visual,cap])
  self.assertFalse(self.alarms(out,15))
 def test_ordinary_prose_between_vertical_caption_and_visual_blocks_ownership(self):
  from pdf_rules.mineru_layout import LayoutObject
  c=PdfLine(1,'Figure 3.6 The LMVQ framework comprises four essential modules.',(480,100,494,700),600,800,bold=True,font_size=10,direction=(0.,1.))
  middle=line('An unrelated paragraph discusses another model and its results.',400,x=380,right=470)
  r=line('LMVQ extracts features through four encoders, transforms their tokens, aligns dimensional features and predicts video quality.',100,page=2)
  visual=LayoutObject('figure',1,(160,180,370,720),'',600,800);cap=LayoutObject('figure_caption',1,c.bbox,c.text,600,800)
  out=repair_reference_identity(index(page(c,middle,number=1,graphics=(visual.bbox,)),page(r,number=2),figures=[Label('3.6',c,'body')]),[visual,cap])
  self.assertEqual(len(self.alarms(out,15)),1)


class ConcreteTableContextTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 def merged_group(self,correct=True):
  c=line('表4.1 IID跨数据集预测结果',120,bold=True,size=10);h=line('Dataset Model RMSE MAE R2',155,role='table')
  data=[line('Group-A',175,role='table'),line('Model-X 3.5932 2.5960 0.8642',195,role='table'),line('Model-X(MM) 3.5512 2.5614 0.8690',215,role='table'),line('Group-B',235,role='table'),line('Model-X 9.1823 5.3934 0.8331',255,role='table'),line('Model-X(MM) 9.1584 5.3252 0.8365',275,role='table'),line('RGD1 Model-X 8.0951 5.4221 0.8513',295,role='table'),line('Model-X(MM) 8.0924 5.4205 0.8518',315,role='table')]
  r=line('Group-A的Model-X(MM)达到MAE2.5614，RGD1的多模态模型达到MAE'+('5.4205' if correct else '0.8518')+'，与Model-X基本持平。',500)
  return self.repair(index(page(c,h,*data,r,tables=((80,145,520,345),)),tables=[Label('4.1',c,'body')]))
 def test_inline_dataset_cell_starts_a_new_group_for_following_model_rows(self):self.assertFalse(self.alarms(self.merged_group(),16))
 def test_inline_dataset_change_cannot_swap_mae_and_r2_columns(self):self.assertEqual(len(self.alarms(self.merged_group(False),16)),1)
 def numbered(self,value='0.9682',section=False):
  c=line('表5.2 B-H随机划分(IID)产率预测结果',120,bold=True,size=10);h=line('Model Type MAE RMSE R2',155,role='table');a=line('ReaMVP DL 3.7213 5.6183 0.9574',185,role='table');b=line('3D Uni-Reaction(MM) DL 3.3142 4.9863 0.9682',215,role='table')
  label='Section 5.2' if section else 'IID5.2随机划分'
  r=line('B-H产率预测任务中'+label+'下，3D-UniReaction(MM)与SOTA模型ReaMVP相当的精度，R2达到'+value+'。',500)
  return self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('5.2',c,'body')]))
 def test_named_experiment_and_primary_model_metric_do_not_follow_comparison_baseline(self):self.assertFalse(self.alarms(self.numbered(),16))
 def test_comparison_baseline_value_is_not_the_primary_models_metric(self):self.assertEqual(len(self.alarms(self.numbered('0.9574'),16)),1)
 def test_section_number_is_not_numbered_experiment_use(self):self.assertEqual(len(self.alarms(self.numbered(section=True),16)),1)
 def test_own_model_alias_needs_both_validation_conditions_and_actual_columns(self):
  c=line('表3.2 模型重构率与合法率对比',120,bold=True,size=10);h=line('非标准分子序列的验证集 标准分子序列的验证集 重构率 合法率',155,role='table');a=line('MegaMolBART 90.87 94.31 90.16 95.21',185,role='table');b=line('Ours 99.17 99.51 99.53 99.75',215,role='table');r=line('标准化SMILES与非标准化SMILES两组验证集分别统计重构率与合法率。对比结果表明，我们的模型相较于MegaMolBART原始权重具有更高重构率。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('3.2',c,'body')]));self.assertFalse(self.alarms(out,16))
 def test_own_model_generic_comparison_without_table_conditions_is_insufficient(self):
  c=line('表3.2 模型重构率与合法率对比',120,bold=True,size=10);h=line('非标准分子序列的验证集 标准分子序列的验证集 重构率 合法率',155,role='table');a=line('MegaMolBART 90.87 94.31 90.16 95.21',185,role='table');b=line('Ours 99.17 99.51 99.53 99.75',215,role='table');r=line('对比结果表明，我们的模型相较于MegaMolBART具有较高重构率与合法率。',500)
  out=self.repair(index(page(c,h,a,b,r,tables=((80,145,520,240),)),tables=[Label('3.2',c,'body')]));self.assertEqual(len(self.alarms(out,16)),1)
 def test_sample_count_and_three_deictic_statistical_properties_use_error_table(self):
  c=line('表5.1 AutoDock-Vina预测值误差统计(N=2000)',120,bold=True,size=10);h=line('指标 误差均值 误差标准差 皮尔逊系数',155,role='table');v=line('数值 0.645 0.428 0.461',185,role='table');pre=line('筛选2000个有明确实验记录的分子，比较AutoDock Vina预测亲和力与实验真值。',60);post=line('从上述一致性统计结果可以看出，AutoDock Vina仍存在系统偏差与随机误差，线性相关性仅为中等。',500)
  out=self.repair(index(page(pre,c,h,v,post,tables=((80,145,520,220),)),tables=[Label('5.1',c,'body')]));self.assertFalse(self.alarms(out,16))
 def test_common_error_words_without_specific_experiment_metadata_are_insufficient(self):
  c=line('表5.1 AutoDock-Vina预测值误差统计(N=2000)',120,bold=True,size=10);h=line('指标 误差均值 误差标准差 皮尔逊系数',155,role='table');v=line('数值 0.645 0.428 0.461',185,role='table');r=line('从上述一致性统计结果可见，系统偏差、随机误差和线性相关性均影响模型。',500)
  out=self.repair(index(page(c,h,v,r,tables=((80,145,520,220),)),tables=[Label('5.1',c,'body')]));self.assertEqual(len(self.alarms(out,16)),1)
 def edit_cases(self,increasing=True,body=True):
  c=line('表5.2 靶点导向的分子编辑样例分析',120,bold=True,size=10);h=line('Case1 Input Output Case2 Input Output',155,role='table');v=line('pIC50=4.25 pIC50='+('6.32' if increasing else '2.32')+' pIC50=4.79 pIC50='+('6.46' if increasing else '2.46'),185,role='table')
  r=line('发现较好的靶点导向分子编辑案例（如图5.2所示）。具体而言，修饰侧链基团使靶点亲和力显著提升。' if body else '数据中存在分子案例（如图5.2所示）。',500)
  f=line('图5.2 分子编辑总体架构',400,page=2,bold=True,size=10)
  return self.repair(index(page(c,h,v,r,tables=((80,145,520,220),)),page(f,number=2,images=((80,170,520,380),)),tables=[Label('5.2',c,'body')],figures=[Label('5.2',f,'body')]))
 def test_explicit_wrong_type_is_not_rewritten_when_case_table_has_independent_proof(self):
  out=self.edit_cases();self.assertFalse(self.alarms(out,16));self.assertFalse(self.alarms(out,11));self.assertTrue(out.figure_refs);self.assertFalse(out.table_refs)
 def test_declining_original_case_values_cannot_prove_described_affinity_increase(self):self.assertEqual(len(self.alarms(self.edit_cases(False),16)),1)
 def test_wrong_typed_number_and_case_topic_alone_cannot_use_table(self):self.assertEqual(len(self.alarms(self.edit_cases(body=False),16)),1)


class ExclusiveOperationAndExperimentTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 def split_flow(self,complete=True,native=True):
  c=line('图2.1 联邦学习与拆分学习的数据流通对比图',400,bold=True,size=10)
  inside=line('中心服务器 全局模型 顶层模型 客户端 底层模型 梯度 联邦学习 拆分学习' if native else '客户端 中心服务器 全局模型',220,role='figure')
  r=line('拆分学习与联邦学习不同，客户端持有底部网络而服务器持有顶部网络。客户端前向计算激活值并发送给服务器，服务器计算损失后反向将梯度发送给客户端，两侧分别更新参数。' if complete else '拆分学习和联邦学习均可保护隐私，客户端与服务器各持有模型的一部分，处理数据并训练和更新模型。')
  return self.repair(index(page(c,inside,r,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]))
 def test_split_training_uses_actual_bidirectional_activation_gradient_protocol(self):self.assertFalse(self.alarms(self.split_flow(),15))
 def test_distributed_learning_topic_and_ownership_are_not_dataflow_use(self):self.assertEqual(len(self.alarms(self.split_flow(False),15)),1)
 def test_bidirectional_prose_cannot_use_unmatched_physical_model(self):self.assertEqual(len(self.alarms(self.split_flow(native=False),15)),1)
 def generation(self,alignment=True,caption=True):
  c=line('Figure 3.5 '+('Sample generation strategy.' if caption else 'Typical distortion types.'),400,page=2,bold=True,size=10)
  inside=line('Spatial Quality Degradation Temporal Quality Degradation Alignment Quality Degradation GPT-4 Manual Post-processing Degradation High Quality Model Low Quality Model',220,page=2,role='figure')
  first=line('Spatial degradation uses GPT-4 to modify prompt adjectives, while lower-performing models generate temporal degradation samples.',100,page=1)
  second=line('Manual Post-processing Degradation applies Gaussian blur and additive noise for spatial degradation. Temporal degradation uses random frame dropping, repetitive frame insertion and shuffling. '+('Alignment degradation randomizes the pairing between prompts and videos.' if alignment else 'Alignment degradation may be challenging.'),100,page=3)
  return self.repair(index(page(first,number=1),page(c,inside,number=2,images=((80,170,520,380),)),page(second,number=3),figures=[Label('3.5',c,'body')]))
 def test_sample_generation_binds_all_three_native_dimensions_and_both_paths(self):self.assertFalse(self.alarms(self.generation(),15))
 def test_generation_without_alignment_operation_keeps_unused_target(self):self.assertEqual(len(self.alarms(self.generation(False),15)),1)
 def test_distortion_example_panels_do_not_inherit_generation_workflow_use(self):self.assertEqual(len(self.alarms(self.generation(caption=False),15)),1)
 def augmentation(self,kernel='RBF',dataset='Mini-ImageNet',metadata=True,compare=True):
  c=line('表5.4 '+dataset+'数据集上的方法性能比较',120,bold=True,size=10);h=line('METHODS 5-way 1-shot ACC 5-way 5-shot ACC',155,role='table');a=line('Vanilla GL-ViT 88.04 96.45',185,role='table');b=line('HP-GP + GL-ViT ('+kernel+') 89.25 97.01',215,role='table')
  pre=line(('Mini-ImageNet数据集包含100类图像，每类600张图像。' if metadata else '')+'本实验将HP-GP应用于视觉Transformer的MLP第一层，采用RBF核函数。',60)
  post=line('实验结果表明，将HP-GP应用于MLP或卷积层时，性能显著提升。' if compare else 'HP-GP是一种模型，使用MLP或卷积层。',500)
  return self.repair(index(page(pre,c,h,a,b,post,tables=((80,145,520,240),)),tables=[Label('5.4',c,'body')]))
 def test_unique_dataset_compound_model_kernel_and_experiment_result_bind_table(self):self.assertFalse(self.alarms(self.augmentation(),16))
 def test_other_native_kernel_is_not_the_described_experiment(self):self.assertEqual(len(self.alarms(self.augmentation(kernel='Matern'),16)),1)
 def test_other_caption_dataset_does_not_borrow_nearby_experiment(self):self.assertEqual(len(self.alarms(self.augmentation(dataset='MNIST'),16)),1)
 def test_model_and_kernel_without_dataset_metadata_are_insufficient(self):self.assertEqual(len(self.alarms(self.augmentation(metadata=False),16)),1)
 def test_experiment_configuration_without_result_discussion_is_insufficient(self):self.assertEqual(len(self.alarms(self.augmentation(compare=False),16)),1)
 def variants(self,star=True,task='分子描述生成',defined=True):
  c=line('表4.2 '+task+'任务表现',120,bold=True,size=10);h=line('Model BLEU-2 BLEU-4 ROUGE-1 METEOR',155,role='table');a=line('BioT5 63.5 55.6 69.2 65.6',185,role='table');b=line('Ours(CheBI-20) 57.3 51.2 70.7 67.7',215,role='table');v=line(('Ours*' if star else 'Ours')+' 48.5 37.3 55.4 46.8',235,role='table')
  pre=line('将实验分为两个部分，ChEBI-20训练测试标记为“CheBI-20”；自组织数据训练测试包含未见过的零样本分子，标记为“*”。' if defined else 'ChEBI-20是分子数据集，本文模型训练和测试。',60)
  post=line('在分子描述生成任务中，我们的模型与其他模型表现相近，BLEU指标没有明显区别；复杂样本平均指标稍逊。',500)
  return self.repair(index(page(pre,c,h,a,b,v,post,tables=((80,145,520,260),)),tables=[Label('4.2',c,'body')]))
 def test_two_defined_test_tags_and_actual_task_metrics_use_own_variant_rows(self):self.assertFalse(self.alarms(self.variants(),16))
 def test_absent_star_variant_cannot_borrow_second_experiment_definition(self):self.assertEqual(len(self.alarms(self.variants(False),16)),1)
 def test_other_translation_direction_cannot_borrow_description_metrics(self):self.assertEqual(len(self.alarms(self.variants(task='基于文本的分子序列生成'),16)),1)
 def test_common_dataset_and_ours_alias_without_tag_definitions_are_insufficient(self):self.assertEqual(len(self.alarms(self.variants(defined=False),16)),1)


class ContextProofAnchorTests(unittest.TestCase):
 def test_cross_paragraph_generation_use_stays_on_actual_pairing_operation(self):
  c=line('Figure 3.5 Sample generation strategy.',400,page=2,bold=True,size=10);inside=line('Spatial Quality Degradation Temporal Quality Degradation Alignment Quality Degradation GPT-4 Manual Post-processing Degradation High Quality Model Low Quality Model',220,page=2,role='figure')
  first=line('Spatial degradation uses GPT-4 to modify prompt adjectives; lower-performing models generate temporal negative samples.',100,page=1)
  actual=line('Manual Post-processing Degradation applies Gaussian blur and noise. Temporal degradation uses frame dropping, frame insertion and shuffling. Alignment degradation randomizes pairing between prompts and videos.',100,page=3)
  unrelated=line('A different model uses four encoders and predicts quality.',500,page=3)
  out=repair_reference_identity(index(page(first,number=1),page(c,inside,number=2,images=((80,170,520,380),)),page(actual,unrelated,number=3),figures=[Label('3.5',c,'body')]))
  refs=[r for r in out.graphic_figure_refs if r.number=='3.5'];self.assertTrue(refs);self.assertTrue(all('pairing' in r.line.text for r in refs))


class OrderedHierarchicalRetrievalTests(unittest.TestCase):
 repair=ReferenceIdentityRepairTests.repair
 alarms=ReferenceIdentityRepairTests.alarms
 expect_used=ConcreteWorkflowRecoveryTests.expect_used
 def test_ordered_topk_summary_then_original_paragraph_embedding_without_layer_label(self):
  self.expect_used('层级检索结构','对于用户问题，生成嵌入向量，首先在所有摘要或总结的向量库中匹配最相似的topk，获取对应的原文段落集合，再次使用扩增文本嵌入向量进行向量匹配，获取最终匹配段落。','L1 摘要 L0 正文')
 def test_repeated_summary_matching_without_original_paragraph_stage_is_insufficient(self):
  c=line('图2.1 层级检索结构',400,bold=True,size=10);r=line('生成用户问题向量，在摘要库中匹配topk，获取摘要集合后再次嵌入摘要并匹配，返回最终摘要。正文也可生成摘要。')
  out=self.repair(index(page(c,r,images=((80,170,520,380),)),figures=[Label('2.1',c,'body')]))
  self.assertEqual(len(self.alarms(out,15)),1)


class CompetingTableEvidencePriorityTests(unittest.TestCase):
 def test_exact_two_variant_definition_is_not_discarded_by_other_table_comparison(self):
  c=line('表4.2 分子描述生成任务表现',120,bold=True,size=10);h=line('Model BLEU ROUGE METEOR',155,role='table');a=line('Ours(CheBI-20) 57.3 70.7 67.7',185,role='table');b=line('Ours* 48.5 55.4 46.8',215,role='table')
  pre=line('实验分两个部分，训练测试标记为“CheBI-20”，第二个训练测试标记为“*”。',60)
  post=line('在分子描述生成任务中，我们的模型表现相近，BLEU无明显区别。同时分子描述生成可以看到MolT5和BioT5在BLEU和EXACT指标均高于其他模型。',500)
  d=line('表4.3 分子描述生成任务表现',120,page=2,bold=True,size=10);h2=line('Model BLEU EXACT',155,page=2,role='table');x=line('MolT5 64.4 90.2',185,page=2,role='table');y=line('BioT5 63.5 89.3',215,page=2,role='table')
  out=repair_reference_identity(index(page(pre,c,h,a,b,post,tables=((80,145,520,240),)),page(d,h2,x,y,number=2,tables=((80,145,520,240),)),tables=[Label('4.2',c,'body'),Label('4.3',d,'body')]))
  self.assertNotIn('4.2',[f['token'] for f in detect_rules(out,{16})['16']['findings']])
