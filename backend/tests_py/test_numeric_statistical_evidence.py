"""Statistics guards need source definitions/coverage, not magic words."""
import copy

import pytest

import numeric_consistency as n
from test_numeric_metric_evidence import block, model, section, MAPPING


def average_row(metric='平均绝对误差'):
    d={'id':'d1','number':'5.3934','metric':metric,'unit':'kcal/mol','comparison':'absolute',
       'condition':'数据集A','dataset':'','method':'','baseline':'','text':'本模型平均绝对误差5.3934 kcal/mol。'}
    return {'declaration_id':'d1','declaration':d,'status':'consistent','reason':'同一条件数值吻合',
            'suggestion':'','evidence':[{'quote':'本模型 MAE 5.3934 kcal/mol。','block_id':'result','page':21}]}


def test_average_definition_outside_selected_excerpt_prevents_false_veto():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为所有样本绝对误差的均值。'))
    row=average_row();before=copy.deepcopy(source)
    limits=n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent' and limits==[]
    assert source==before


def test_unrelated_method_definition_does_not_excuse_missing_average_scope():
    source=model(block('definition','other-chapter','平均绝对误差（MAE）定义为所有样本绝对误差的均值。'))
    row=average_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_definition_cannot_turn_a_numerical_conflict_into_consistency():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为全部样本绝对误差均值。'))
    row=average_row();row.update(status='inconsistent',reason='同一条件实际值6.0，与5.3934冲突')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconsistent'


def test_definition_alone_cannot_excuse_a_different_number():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为所有样本绝对误差的均值。'))
    row=average_row();row['evidence'][0]['quote']='本模型 MAE 6.3934 kcal/mol。'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_different_metric_definition_does_not_establish_average_semantics():
    source=model(block('definition','metrics','MSE 定义为所有样本平方误差的均值。'))
    row=average_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_average_definition_does_not_substitute_for_measured_metric():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为所有样本绝对误差的均值。'))
    row=average_row();row['evidence'][0]['quote']='本模型 MSE 5.3934 kcal/mol。'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_result_evidence_in_another_chapter_cannot_borrow_average_definition():
    source=model(block('definition','metrics','平均绝对误差（MAE）定义为所有样本绝对误差的均值。'))
    row=average_row();row['evidence'][0]['section_id']='other-chapter'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('text',[
    'Mean runtime | SSE: evaluation metric',
    '平均簇内余弦（Average Cosine）定义如下。与平均SSE不同，该指标衡量向量方向。',
])
def test_average_word_for_another_measure_does_not_define_sse_mean(text):
    source=model(block('definition','metrics',text,kind='Table'))
    row=average_row(metric='平均SSE')
    row['declaration'].update(text='平均SSE为5.3934。',unit='')
    row['evidence'][0]['quote']='SSE 5.3934'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_absent_context_keeps_legacy_row_and_limitations_byte_for_byte():
    row=average_row();before=copy.deepcopy(row)
    limits=n.conservative_evidence_guard([row])
    gap='已定位相关数值，但引用原文未明确该指标的平均统计口径，需要核实统计范围。'
    assert row=={**before,'model_status':'consistent','model_reason':before['reason'],
                'status':'inconclusive','reason':gap,
                'suggestion':'请作者结合相应实验表格核实指标、基线和统计范围。'}
    assert limits==[{'declaration_id':'d1','model_status':'consistent','reason':gap}]


def test_anaphoric_scheme_condition_adds_no_experimental_restriction():
    source=model();source['tables']=[table('t1',[('A','3.9321%'),('B','2.0%')])]
    row=maximum_row();row['declaration']['condition']='该方案'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'
    row=maximum_row();row['declaration']['condition']='该方案，batch=64'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def table(tid,values,*,sid='experiment',metric='RelaImpr (AUC)',grounded=True):
    matrix=[['Dataset',metric]]+[[dataset,value] for dataset,value in values]
    return {'table_id':tid,'section_id':sid,'page':21,'caption':'表5.2 各数据集评估结果','matrix':matrix,
            'rows':[],'column_headers':['Dataset',metric],'native_header_paths':[['Dataset'],[metric]],
            'native_cells_grounded':grounded,'reliability':'reliable','limitations':[],
            'row_count':len(matrix),'column_count':2}


def maximum_row(number='3.93',dataset=''):
    d={'id':'d1','number':number,'metric':'AUC相对提升','unit':'%','comparison':'relative',
       'condition':'公开数据集','dataset':dataset,'method':'','baseline':'','text':f'AUC最高相对提升{number}%。'}
    return {'declaration_id':'d1','declaration':d,'status':'consistent','reason':'对应表格结果吻合',
            'suggestion':'','evidence':[{'quote':f'AUC {number}%','block_id':'t1','page':21}]}


def test_complete_comparison_column_proves_max_without_the_word_maximum():
    source=model();source['tables']=[table('t1',[('A','1.4875%'),('B','3.9321%'),('C','-0.0727%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


def test_larger_result_in_another_scope_table_is_not_silently_ignored():
    source=model();source['tables']=[table('t1',[('A','3.9321%')]),table('t2',[('B','4.51%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_other_metric_cannot_prove_maximum_even_if_its_value_matches():
    source=model();source['tables']=[table('t1',[('A','3.9321%')],metric='RelaImpr (gAUC)')]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_larger_value_from_other_declared_dataset_does_not_refute_scoped_maximum():
    source=model();source['tables']=[table('t1',[('DataA','3.9321%'),('DataB','9.2%')])]
    row=maximum_row(dataset='DataA')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('change',['unreadable_cell','untrusted_geometry','unbound_source','partial_rows'])
def test_incomplete_or_untraceable_tables_do_not_prove_a_maximum(change):
    source=model();item=table('t1',[('A','3.9321%'),('B','2.0%')]);source['tables']=[item]
    if change=='unreadable_cell':item['matrix'][2][1]=None
    if change=='untrusted_geometry':item['native_cells_grounded']=False;item['reliability']='limited'
    if change=='unbound_source':item['section_id']='unknown'
    if change=='partial_rows':item['row_count']=9
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_unselected_matching_table_in_other_method_cannot_prove_maximum():
    source=model();source['tables']=[table('t1',[('A','1.0%')],sid='other-method'),
                                    table('t2',[('A','3.9321%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_percentage_point_column_does_not_prove_relative_improvement():
    source=model();source['tables']=[table('t1',[('A','3.9321%')],metric='AUC提升（百分点）')]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_missing_unit_cannot_establish_percentage_maximum():
    source=model();source['tables']=[table('t1',[('A','3.9321')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_metric_columns_with_same_value_remain_separate():
    item=table('t1',[('A','3.9321%'),('B','2.0%')])
    item.update(matrix=[['Dataset','RelaImpr (AUC)','RelaImpr (gAUC)'],
                        ['A','3.9321%','3.9321%'],['B','2.0%','9.5%']],
                column_count=3,column_headers=['Dataset','RelaImpr (AUC)','RelaImpr (gAUC)'],
                native_header_paths=[['Dataset'],['RelaImpr (AUC)'],['RelaImpr (gAUC)']])
    source=model();source['tables']=[item];row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


def test_grounded_dataset_spanning_label_filters_rows_without_forward_fill():
    item=table('t1',[('DataA','3.9321%'),(None,'2.0%'),('DataB','9.5%')])
    item['matrix'][1][0]=None
    item['native_spanning_cells']=[{'role':'body','text':'DataA','row_indices':[1,2],
                                  'column_indices':[0],'grounding':'native_ruling_boundaries'}]
    source=model();source['tables']=[item];row=maximum_row(dataset='DataA')
    before=copy.deepcopy(item)
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent' and item==before


def test_unproven_missing_dataset_label_prevents_scoped_maximum():
    item=table('t1',[(None,'3.9321%'),('DataB','9.5%')])
    source=model();source['tables']=[item];row=maximum_row(dataset='DataA')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_unknown_dataset_row_also_prevents_global_dataset_maximum():
    source=model();source['tables']=[table('t1',[('A','3.9321%'),(None,'2.0%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_unknown_measurement_suffix_is_not_a_complete_scalar():
    source=model();source['tables']=[table('t1',[('A','3.9321% uncertain'),('B','2.0%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_model_and_baseline_scope_must_match_named_row_fields():
    item=table('t1',[('A','3.9321%')])
    item.update(matrix=[['Dataset','Model','Baseline','RelaImpr (AUC)'],
                        ['A','OtherModel','OtherBaseline','3.9321%']],column_count=4,
                column_headers=['Dataset','Model','Baseline','RelaImpr (AUC)'],
                native_header_paths=[['Dataset'],['Model'],['Baseline'],['RelaImpr (AUC)']])
    source=model();source['tables']=[item];row=maximum_row()
    row['declaration'].update(method='ProposedModel',baseline='Baseline')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_negative_maximum_uses_signed_decimal_values():
    source=model();source['tables']=[table('t1',[('A','-1.004%'),('B','-2.0%')])]
    row=maximum_row(number='-1.00')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


def test_incomplete_comparison_set_does_not_become_pass_when_source_says_maximum():
    source=model();item=table('t1',[('A','3.9321%'),('B',None)]);source['tables']=[item]
    row=maximum_row();row['evidence'][0]['quote']='AUC最高3.93%'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_display_subset_cannot_replace_complete_native_matrix():
    item=table('t1',[('A','3.9321%'),('B','9.5%')])
    item['raw_matrix']=copy.deepcopy(item['matrix'])
    item['matrix']=item['matrix'][:2];item['row_count']=2
    source=model();source['tables']=[item];row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('status',['inconsistent','inconclusive','execution_error'])
def test_complete_native_maximum_cannot_promote_or_rewrite_other_statuses(status):
    source=model();source['tables']=[table('t1',[('A','3.9321%'),('B','2.0%')])]
    row=maximum_row();row.update(status=status,reason='existing result')
    before=copy.deepcopy(row)
    assert n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])==[]
    assert row==before


def speedup_case():
    paragraph=block('comparison','experiment','表5.3 对比编译器默认配置与Tuner优化配置下的执行时间。')
    source=model(paragraph)
    headers=['Operator','Performance of Compiler Config. (us)','Performance of Tuner Config. (us) with Speedup']
    item=table('t1',[])
    item.update(caption='表5.3 各算子结果',matrix=[headers,['GEMM','141.67','97.07 (1.46×)'],
                                               ['FFN','350.63','280.51 (1.25×)']],
                column_headers=headers,native_header_paths=[[h] for h in headers],row_count=3,column_count=3)
    source['tables']=[item]
    row=maximum_row('1.46')
    row['declaration'].update(metric='性能提升',unit='倍',method='Tuner',baseline='编译器默认配置',
                              condition='相较于编译器默认配置',text='Tuner最高可实现1.46倍的性能提升。')
    row['evidence'][0].update(quote='97.07 (1.46×)')
    mapping={**MAPPING,'table_reference_scope':[{'table_id':'t1','block_id':'comparison',
             'source_node_id':'comparison-node','section_id':'experiment','page':20,'quote':'表5.3'}]}
    return source,row,mapping


def test_nested_native_speedup_uses_explicit_ratio_and_named_source_comparison():
    source,row,mapping=speedup_case()
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='consistent'
    assert row['statistical_evidence'][0]['maximum']=='1.46'


def test_later_native_table_reference_can_supply_exact_named_scope():
    source,row,mapping=speedup_case()
    source['blocks'][0]['text']='表5.3 系统性地总结所有算子结果。'
    source['blocks'].append(block('later','experiment','表5.3 对比编译器 默认配置与Tuner优化配置下的执行时间。'))
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='consistent'


def test_native_ascii_name_keeps_word_boundary_before_configuration_description():
    source,row,mapping=speedup_case()
    source['blocks'][0]['text']='表5.3 对比Compiler Default 配置与Tuner DSE优化配置。'
    row['declaration'].update(baseline='Compiler Default 配置',condition='相较于Compiler Default 配置')
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='consistent'


def test_context_scope_never_overrides_an_explicit_different_model_axis():
    source,row,mapping=speedup_case()
    item=source['tables'][0]
    item['matrix'][0][0]='Model';item['column_headers'][0]='Model';item['native_header_paths'][0]=['Model']
    item['matrix'][1][0]='OtherModel';item['matrix'][2][0]='OtherModel'
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='inconclusive'


def test_softwrapped_maximum_still_requires_complete_comparison():
    source=model();source['tables']=[table('t1',[('A','3.9321%'),('B',None)])]
    row=maximum_row();row['declaration']['text']='AUC最高相对提升\n3.93%。'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_atomic_other_metric_does_not_inherit_neighbor_maximum_word():
    source=model();row=maximum_row('4.5')
    row['declaration'].update(metric='gAUC',text='AUC最高提升3.93%，gAUC提升4.5%。')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('change',['no_speedup_header','wrong_reference','different_baseline','larger_row','unreadable_ratio'])
def test_nested_speedup_does_not_relax_metric_scope_or_coverage(change):
    source,row,mapping=speedup_case()
    if change=='no_speedup_header':
        source['tables'][0]['native_header_paths'][2]=['Tuner latency (us)']
    if change=='wrong_reference':mapping['table_reference_scope'][0]['quote']='表9.9'
    if change=='different_baseline':row['declaration']['baseline']='另一个编译器配置'
    if change=='larger_row':source['tables'][0]['matrix'][2][2]='200.0 (1.60×)'
    if change=='unreadable_ratio':source['tables'][0]['matrix'][2][2]='280.51 (unknown)'
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='inconclusive'


def improvement_row_case():
    headers=['Models','DatasetA / R@20','DatasetA / N@20','DatasetB / R@20','DatasetB / N@20']
    item=table('t1',[])
    item.update(matrix=[headers,['BaselineA','0.05','0.04','0.03','0.02'],
                        ['BaselineB','0.06','0.05','0.04','0.03'],
                        ['Proposed','0.07*','0.06*','0.05*','0.04*'],
                        ['提升比例','17.61%','15.98%','7.20%','8.12%']],
                column_headers=headers,native_header_paths=[['Models'],['DatasetA','R@20'],['DatasetA','N@20'],
                                                          ['DatasetB','R@20'],['DatasetB','N@20']],
                row_count=5,column_count=5)
    source=model();source['tables']=[item]
    row=maximum_row('17.61')
    row['declaration'].update(metric='Recall/NDCG',comparison='relative improvement',
                              baseline='代表性基线方法',condition='公开数据集',
                              text='Recall/NDCG指标取得最高17.61%的提升。')
    return source,row


def test_row_oriented_relative_improvement_checks_both_requested_metrics():
    source,row=improvement_row_case()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'
    assert row['statistical_evidence'][0]['comparison_count']==4


@pytest.mark.parametrize('change',['wrong_unit','missing_improvement','missing_metric','larger_value','specific_wrong_baseline'])
def test_row_oriented_improvement_retains_ambiguity_and_counterexamples(change):
    source,row=improvement_row_case();item=source['tables'][0]
    if change=='wrong_unit':item['matrix'][-1][1]='17.61百分点'
    if change=='missing_improvement':item['matrix'][-1][2]=None
    if change=='missing_metric':
        item['native_header_paths'][2]=['DatasetA','Precision'];item['native_header_paths'][4]=['DatasetB','Precision']
        item['matrix'][0][2]='DatasetA / Precision';item['matrix'][0][4]='DatasetB / Precision'
    if change=='larger_value':item['matrix'][-1][4]='20.0%'
    if change=='specific_wrong_baseline':row['declaration']['baseline']='AbsentBaseline'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_representative_baseline_comparison_excludes_explicit_ablation_scope():
    source,row=improvement_row_case()
    other=copy.deepcopy(source['tables'][0]);other.update(table_id='ablation',section_id='ablation')
    other['matrix'][-1][1]='25.0%';other['native_cells_grounded']=False
    source['tables'].append(other)
    source['sections']['ablation']=section('ablation','experiment','5.4.3 消融实验')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


def test_explicit_ablation_target_does_not_get_the_baseline_class_exclusion():
    source,row=improvement_row_case();row['declaration']['condition']='消融实验'
    other=copy.deepcopy(source['tables'][0]);other.update(table_id='ablation',section_id='ablation')
    other['matrix'][-1][1]='25.0%';source['tables'].append(other)
    source['sections']['ablation']=section('ablation','experiment','5.4.3 消融实验')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def prose_max_case(text='Engine在在线服务场景的有效吞吐量最高提升2.5倍。'):
    native=block('result','experiment',text,page=21)
    source=model(native)
    row=maximum_row('2.5')
    row['declaration'].update(metric='有效吞吐量提升',unit='倍',method='Engine',condition='在线服务场景',
                              text='Engine有效吞吐量最高提升2.5倍。')
    row['evidence'][0].update(block_id='result',quote=text,page=21,section_id='experiment')
    return source,row


def test_explicit_native_prose_maximum_binds_target_metric_and_value():
    source,row=prose_max_case()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('scope',[
    '非在线服务场景', '不是在线服务场景', 'non-online service', 'not online service',
])
def test_prose_maximum_does_not_treat_negated_online_scope_as_online(scope):
    source,row=prose_max_case(f'Engine在{scope}中有效吞吐量最高提升2.5倍。')
    if scope.isascii():row['declaration']['condition']='online service'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('bound',[
    '最高不超过', '最高不高于', '最高不到', '最高≤', 'maximum at most ',
])
def test_prose_maximum_bound_does_not_prove_attained_measurement(bound):
    source,row=prose_max_case(f'Engine在线有效吞吐量 {bound}2.5倍，实测最高为2.0倍。')
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_bound_cannot_supply_measurement_for_an_explicit_chapter_summary_maximum():
    source,row=prose_max_case('Engine在线有效吞吐量不超过2.5倍。')
    source['sections']['summary']=section('summary','chapter','5.4 本章小结')
    source['blocks'].append(block('summary','summary','Engine在线有效吞吐量最高提升2.5倍。',page=22))
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('incomplete',[False,True])
def test_prose_maximum_cannot_bypass_known_comparative_table(incomplete):
    native=block('result','experiment','AUC相对提升最高3.93%。',page=21)
    source=model(native);source['tables']=[table('t1',[('A','3.9321%'),('B','9.5%')])]
    if incomplete:source['tables'][0]['row_count']+=1
    row=maximum_row();row['evidence'][0].update(block_id='result',quote=native['text'])
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('field,text,expected',[
    ('method','OtherEngine在线有效吞吐量最高提升2.5倍。Engine在线有效吞吐量提升2.0倍。','Engine'),
    ('method','Engine在线服务场景，OtherEngine有效吞吐量最高提升2.5倍。','Engine'),
    ('dataset','Engine在DataB在线有效吞吐量最高提升2.5倍。Engine在DataA在线有效吞吐量提升2.0倍。','DataA'),
    ('baseline','Engine相较于OtherBase在线有效吞吐量最高提升2.5倍。Engine相较于Base在线有效吞吐量提升2.0倍。','Base'),
])
def test_prose_maximum_named_axes_cannot_be_borrowed_from_another_sentence(field,text,expected):
    source,row=prose_max_case(text);row['declaration'][field]=expected
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('batch,status',[(1,'inconclusive'),(64,'consistent')])
def test_prose_maximum_preserves_compound_online_condition(batch,status):
    source,row=prose_max_case(f'Engine在线服务场景，batch={batch}时有效吞吐量最高提升2.5倍。')
    row['declaration']['condition']='在线服务场景，batch=64'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']==status


def test_inherited_prose_scope_preserves_exact_native_quote():
    source,row=prose_max_case('Engine在线服务场景,batch=64时有效吞吐量最高提升2.5倍。')
    row['declaration']['condition']='在线服务场景，batch=64'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'
    assert row['statistical_evidence'][0]['source']['quote'] in source['blocks'][0]['text']


def test_summary_measurement_cannot_borrow_a_different_subject_in_same_sentence():
    source,row=prose_max_case('OtherEngine在线有效吞吐量提升2.5倍，Engine在线有效吞吐量提升2.0倍。')
    source['sections']['summary']=section('summary','chapter','5.4 本章小结')
    source['blocks'].append(block('summary','summary','Engine在线有效吞吐量高达2.5倍。',page=22))
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


@pytest.mark.parametrize('text',[
    'Engine在在线服务场景TTFT最高提升295倍，有效吞吐量提升2.5倍。',
    'Engine的TTFT最高提升295倍。在线Goodput提升2.5倍。',
    'Engine在离线服务场景有效吞吐量最高提升2.5倍。',
    'Engine在线性能比较。离线场景，有效吞吐量最高提升2.5倍。',
    'OtherEngine在在线服务场景有效吞吐量最高提升2.5倍。',
])
def test_prose_maximum_does_not_borrow_neighbor_metric_or_wrong_scope(text):
    source,row=prose_max_case(text)
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_same_chapter_summary_can_supply_maximum_semantics_with_separate_measurement():
    source,row=prose_max_case('Engine在在线服务场景有效吞吐量提升2.5倍。')
    source['sections']['summary']=section('summary','chapter','5.4 本章小结')
    source['blocks'].append(block('summary','summary','Engine在线服务有效吞吐量高达2.5倍。',page=22))
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('change',['wrong_chapter','no_measurement','wrong_condition','not_summary'])
def test_summary_never_replaces_experiment_or_crosses_chapter(change):
    source,row=prose_max_case('Engine在在线服务场景有效吞吐量提升2.5倍。')
    source['sections']['summary']=section('summary','chapter','5.4 本章小结')
    source['blocks'].append(block('summary','summary','Engine在线服务有效吞吐量高达2.5倍。',page=22))
    if change=='wrong_chapter':source['sections']['summary']['parent_id']='other-chapter'
    if change=='no_measurement':source['blocks'][0]['text']='Engine在线有效吞吐量提升2.0倍。';row['evidence'][0]['quote']=source['blocks'][0]['text']
    if change=='wrong_condition':source['blocks'][-1]['text']='Engine离线服务有效吞吐量高达2.5倍。'
    if change=='not_summary':source['sections']['summary']['title']='第六章 全文总结'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def caption_metric_case():
    caption=block('caption','experiment','Table 4.4',page=21,kind='Caption')
    meaning=block('caption-meaning','experiment','TLB Miss Rates under Different Non-Secure Domain Sizes',page=21)
    caption['provenance'][0]['bbox']=[80,100,180,112]
    meaning['provenance'][0]['bbox']=[80,115,510,128]
    source=model(caption,meaning)
    source['sections']['chapter']['title']='第四章 TEE TLB安全可扩展隔离机制'
    headers=['基准程序','100%非安全域','1/2非安全域','1/4非安全域']
    item=table('t1',[])
    item.update(caption='Table 4.4',source_node_ids=['caption-node'],bbox=[80,140,510,300],
                matrix=[headers,['A','1.50%','3.2%','8.82%'],['B','0.8%','1.2%','4.7%']],
                column_headers=headers,native_header_paths=[[h] for h in headers],row_count=3,column_count=4)
    source['tables']=[item]
    row=maximum_row('8.82')
    row['declaration'].update(metric='缺失率',comparison='absolute',method='可扩展TLB隔离机制',
                              condition='最高缺失率',text='最高8.82%的缺失率。')
    return source,row


def test_native_caption_continuation_binds_one_common_metric_to_condition_columns():
    source,row=caption_metric_case()
    before=copy.deepcopy(source)
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent' and source==before
    assert row['statistical_evidence'][0]['comparison_count']==6


def test_selected_native_table_reference_can_bind_full_measurement_table():
    source,row=caption_metric_case()
    reference=block('reference','experiment','表4.4列出了不同非安全域大小下TLB缺失率。',page=21)
    source['blocks'].append(reference)
    row['evidence'][0].update(block_id='reference',page=21,quote=reference['text'])
    mapping={**MAPPING,'table_reference_scope':[{'table_id':'t1','block_id':'reference',
             'section_id':'experiment','page':21,'quote':'表4.4'}]}
    n.conservative_evidence_guard([row],model=source,mappings=[mapping])
    assert row['status']=='consistent'


def test_explicit_native_upper_bound_cannot_exceed_exact_attained_maximum():
    source,row=caption_metric_case();source['tables'][0]['matrix'][2][1]='<0.01%'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('value',['>0.01%','≤9.5%'])
def test_lower_or_larger_upper_bounds_do_not_prove_the_declared_maximum(value):
    source,row=caption_metric_case();source['tables'][0]['matrix'][2][1]=value
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_upper_bound_alone_never_proves_attainment():
    source=model();source['tables']=[table('t1',[('A','<3.93%'),('B','<2.0%')])]
    row=maximum_row()
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def test_caption_metric_keeps_qualified_native_lines_when_node_also_contains_table_header():
    source,row=caption_metric_case();meaning=source['blocks'][1]
    first=meaning['text'];meaning['text'] += '\n基准程序'
    meaning['provenance']=[{'bbox':[80,115,510,128],'node_text_start':0,'node_text_end':len(first),'line_id':'caption-line'},
                           {'bbox':[80,141,200,153],'node_text_start':len(first)+1,'node_text_end':len(first)+5,'line_id':'header-line'}]
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'
    quotes=row['statistical_evidence'][0]['tables'][0]['metric_caption_sources']
    assert any(item['quote']==first for item in quotes)


@pytest.mark.parametrize('change',['far_caption','wrong_page','wrong_method','other_metric_column','missing_cell'])
def test_caption_metric_inheritance_requires_native_geometry_scope_and_full_cells(change):
    source,row=caption_metric_case()
    if change=='far_caption':source['blocks'][1]['provenance'][0]['bbox']=[80,600,510,615]
    if change=='wrong_page':source['blocks'][1]['page']=22
    if change=='wrong_method':row['declaration']['method']='另一个TLB隔离机制'
    if change=='other_metric_column':source['tables'][0]['native_header_paths'][3]=['Latency'];source['tables'][0]['matrix'][2][3]='9ms'
    if change=='missing_cell':source['tables'][0]['matrix'][2][3]=None
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'


def prose_grid_case():
    source=model();complete=table('t1',[('A','3.9321%'),('B','2.0%')])
    measured={'block_index':0,'line_index':0,'span_index':0,'char_start':0,'char_end':7,
              'text':'3.9321%','bbox':[80,160,140,175]}
    complete.update(strategy='native_rules',bbox=[80,100,510,220],source_node_ids=['caption-node'],
                    native_rulings=[[80,100,510],[80,140,510],[80,220,510]],
                    rows=[{'cells':[{'native_spans':[measured]}]}])
    text='The following paragraph analyzes the experiment.'
    extra={'block_index':1,'line_index':0,'span_index':0,'char_start':0,'char_end':len(text),
           'text':text,'bbox':[80,240,510,260]}
    prose=block('analysis','experiment',text,page=21)
    prose['provenance'][0].update(line_id='p20-b1-l0',bbox=extra['bbox'])
    source['blocks']=[prose]
    oversized=copy.deepcopy(complete)
    oversized.update(table_id='t2',strategy='text',bbox=[80,100,510,300],native_cells_grounded=False,
                     limitations=['unconfirmed_text_table_relationships','native_cell_text_not_grounded'],
                     rows=[{'cells':[{'native_spans':[measured,extra]}]}])
    source['tables']=[complete,oversized]
    return source,maximum_row(),extra


def test_pagewide_text_grid_preserves_extra_prose_as_nontable_context():
    source,row,_=prose_grid_case();before=copy.deepcopy(source)
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent' and source==before
    assert row['statistical_evidence'][0]['non_table_alternatives'][0]['extra_native_block_ids']==['analysis']


@pytest.mark.parametrize('identity,status',[('5.2','consistent'),('9.9','inconclusive')])
def test_paragraph_typed_table_identity_must_match_known_closed_table(identity,status):
    source,row,extra=prose_grid_case()
    text=f'Table {identity} Additional results show AUC improvement of 9.5 percent.'
    source['blocks'][0]['text']=text
    source['blocks'][0]['provenance'][0]['node_text_end']=len(text)
    extra.update(text=text,char_end=len(text))
    source['tables'][1]['rows'][0]['cells'][0]['native_spans'][-1]=extra
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']==status


@pytest.mark.parametrize('identity,status',[('9.9','inconclusive'),('5.2','consistent')])
def test_paragraph_typed_table_identity_is_not_discarded_as_extra_prose(identity,status):
    source,row,extra=prose_grid_case()
    text=f'Table {identity} Additional results show AUC improvement of 9.5 percent.'
    source['blocks'][0]['text']=text
    source['blocks'][0]['provenance'][0]['node_text_end']=len(text)
    extra.update(text=text,char_end=len(text))
    source['tables'][1]['rows'][0]['cells'][0]['native_spans'][-1].update(extra)
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']==status


def test_native_verified_section_number_can_remain_paragraph_typed():
    source,row,_=prose_grid_case()
    number=block('number','experiment','5.4',page=21)
    number['provenance'][0].update(line_id='p20-b2-l0',bbox=[80,275,100,290])
    source['blocks'].append(number)
    source['sections']['experiment'].update(title='5.4 Analysis',heading_node_ids=['number-node'])
    source['tables'][1]['rows'][0]['cells'][0]['native_spans'].append(
        {'block_index':2,'line_index':0,'span_index':0,'char_start':0,'char_end':3,
         'text':'5.4','bbox':[80,275,100,290]})
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


def test_exact_native_line_ownership_does_not_require_redecoded_glyph_identity():
    source,row,_=prose_grid_case()
    source['tables'][1]['rows'][0]['cells'][0]['native_spans'][-1]['text']='\ufb01'
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='consistent'


@pytest.mark.parametrize('change',['extra_table','extra_caption','unresolved_source','inside_closed_table'])
def test_overbroad_grid_classification_requires_resolved_prose_outside_closed_table(change):
    source,row,extra=prose_grid_case()
    if change=='extra_table':source['blocks'][0]['block_type']='Table'
    if change=='extra_caption':source['blocks'][0]['block_type']='Caption'
    if change=='unresolved_source':source['blocks']=[]
    if change=='inside_closed_table':extra['bbox']=[80,180,510,195];source['tables'][1]['rows'][0]['cells'][0]['native_spans'][-1]['bbox']=extra['bbox'];source['blocks'][0]['provenance'][0]['bbox']=extra['bbox']
    n.conservative_evidence_guard([row],model=source,mappings=[MAPPING])
    assert row['status']=='inconclusive'
