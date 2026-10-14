import pathlib
import pytest
from pdf_rules.model import PdfLine,PdfPage,PdfDocument
from pdf_rules.mineru_layout import LayoutObject
from pdf_rules.numbering import normalize_text
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules
def line(text,box,font=12,bold=False,page=1,scale=1):
 b=tuple(v*scale for v in box)
 # Each region identifies exact synthetic ink so number highlighting remains testable.
 w=(b[2]-b[0])/max(1,len(normalize_text(text)))
 regions=tuple((i,i+1,(b[0]+i*w,b[1],b[0]+(i+1)*w,b[3])) for i in range(len(normalize_text(text))))
 return PdfLine(page,text,b,600*scale,840*scale,font_size=font*scale,bold=bold,source='native',text_regions=regions,block_id=None)

def continuation(scale,font,gap,ending,tail,number):
 y=220;h=font;second=y+h*.65+h
 texts=[line('这里统计了多个观测切片中的群体状态，实验使用相同时间窗。',(70,150,530,150+h),font,scale=scale),
 line('各观测切片采用一致的数据处理方式，便于比较不同等级的变化。',(70,180,530,180+h),font,scale=scale),
 line('这一实验统计了多个观测切片的群体变化，'+ending,(70,y,530,y+h),font,scale=scale),
 line('图'+number+tail,(70,second,530,second+h),font,scale=scale)]
 vy=second+h+gap;box=tuple(v*scale for v in (70,vy,530,vy+160))
 capy=vy+180;texts.append(line('图'+number+' 测试结果总体比较',(190,capy,440,capy+h*.875),font*.875,True,scale=scale))
 page=PdfPage(1,600*scale,840*scale,tuple(texts),images=(box,))
 doc=PdfDocument(pathlib.Path('synthetic-continuation.pdf'),(page,))
 obj=LayoutObject('figure',1,box,'统计结果柱图',page.width,page.height)
 return doc,(obj,)

def bare_scene(number,text,title,scale=1,font=12,float_page=False,collision=None,nodes=None):
 target_page=2 if float_page else 1
 rows=[line('这是对照实验的正文背景，使用相同配置完成各项测量。',(70,110,530,110+font),font,scale=scale),
 line(text,(94,150,530,150+font),font,scale=scale)]
 box=tuple(v*scale for v in (70,240,530,400))
 rows.append(line('图'+number+' '+title,(190,425,440,425+font*.875),font*.875,True,page=target_page,scale=scale))
 if nodes:rows.append(line(' '.join(nodes),(110,280,480,280+font),font,page=target_page,scale=scale))
 objects=[LayoutObject('figure',target_page,box,' '.join(nodes or [title]),600*scale,840*scale)]
 pages=[]
 if collision:
  tb=tuple(v*scale for v in (70,500,530,650))
  rows.append(line('表'+number+' '+collision,(190,475,440,475+font*.875),font*.875,True,page=target_page,scale=scale))
  objects.append(LayoutObject('table',target_page,tb,collision,600*scale,840*scale))
 for p in range(1,target_page+1):
  pages.append(PdfPage(p,600*scale,840*scale,tuple(l for l in rows if l.page_number==p),images=(box,) if p==target_page else (),tables=(objects[-1].bbox,) if collision and p==target_page else ()))
 return PdfDocument(pathlib.Path('synthetic-bare-number.pdf'),tuple(pages)),tuple(objects)

@pytest.mark.parametrize('scale,font',[(.6,10),(1,12),(1.4,14)])
@pytest.mark.parametrize('gap',[20,80])
@pytest.mark.parametrize('ending',['该结果已汇总于','对应结果可见'])
def test_body_reference_wrap_stays_prose_beside_an_independent_visual(scale,font,gap,ending):
    doc,objects=continuation(scale,font,gap,ending,'中。这种离散统计便于分析变化趋势。','7.12')
    result=detect_rules(build_index(doc,objects),[15])
    assert not result['15']['findings']


@pytest.mark.parametrize('number,scale',[('2.1',.7),('7.12',1.3)])
@pytest.mark.parametrize('float_page',[False,True])
@pytest.mark.parametrize('grammar',['see','combine','naked'])
def test_explicit_omitted_type_usage_is_bound_to_actual_title_or_components(number,scale,float_page,grammar):
    if grammar=='see':
        text='上述传统GC算法的概况可见'+number+'，这些方法用于比较暂停时间。'
        title='传统GC算法概况';nodes=None
    elif grammar=='combine':
        text='进一步结合'+number+'可以发现，流量生成带宽对比在高负载阶段呈现差异。'
        title='流量生成带宽对比';nodes=None
    else:
        text='将服务拆分为下文四个独立部署的函数单元'+number+'，分别处理校验、摘要、写入与复制。'
        title='函数设计';nodes=['校验','摘要','写入','复制']
    doc,objects=bare_scene(number,text,title,scale,12,float_page,nodes=nodes)
    assert not detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('text',[
    '传统GC算法的统计结果可见2.1%。','传统GC算法的平均暂停时间可见2.1ms。',
    '传统GC算法的速度可见2.1倍提升。','传统GC算法的概况可见2.1节。',
    '传统GC算法的概况详见第2.1节。','传统GC算法的平均暂停时间由式2.1给出。',
    '传统GC算法的概况可见2.2。','本文研究了传统GC算法的暂停时间与回收机制。'])
def test_numeric_quantities_sections_and_wrong_numbers_do_not_reference_a_visual(text):
    doc,objects=bare_scene('2.1',text,'传统GC算法概况')
    assert detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('collision',['运行参数配置','传统GC算法概况'])
def test_bare_number_identity_requires_disambiguation_between_real_object_kinds(collision):
    doc,objects=bare_scene('7.12','上述传统GC算法概况可见7.12。','传统GC算法概况',collision=collision)
    result=detect_rules(build_index(doc,objects),[15,16])
    assert bool(result['15']['findings'])==(collision=='传统GC算法概况')
    assert result['16']['findings']


def test_component_topic_without_numbered_pointer_is_not_a_reference():
    doc,objects=bare_scene('2.1','本系统使用校验、摘要、写入、复制四个独立函数处理数据。','函数设计',nodes=['校验','摘要','写入','复制'])
    assert detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('number',['2.1','7.12'])
@pytest.mark.parametrize('unit_clause',['单位为毫秒','这个数值的单位为毫秒','该值的单位是毫秒'])
def test_measurement_unit_in_next_clause_does_not_turn_a_scalar_into_a_reference(number,unit_clause):
    doc,objects=bare_scene(number,'传统GC算法的暂停时间均值可见'+number+'，'+unit_clause+'。','传统GC算法暂停时间均值')
    assert detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('float_page',[False,True])
def test_component_pointer_preserves_same_number_cross_kind_semantic_ambiguity(float_page):
    doc,objects=bare_scene('7.12','下文四个独立部署的函数单元7.12，分别处理校验、摘要、写入与复制。','函数设计',
                           float_page=float_page,collision='函数设计',nodes=['校验','摘要','写入','复制'])
    result=detect_rules(build_index(doc,objects),[15,16])
    assert result['15']['findings'] and result['16']['findings']


@pytest.mark.parametrize('text',[
 '传统GC算法的暂停时间均值可见2.1。该测量值以毫秒为单位。',
 '传统GC算法的暂停时间均值可见2.1，换算为0.0021秒。',
 '传统GC算法的暂停时间均值为2.1毫秒，结合2.1可以计算单位时间开销。',
 '传统GC算法的概况参见2.1，该编号是下方脚注编号。'])
def test_number_identity_is_not_overridden_by_an_unrelated_same_number_visual(text):
    doc,objects=bare_scene('2.1',text,'传统GC算法暂停时间均值概况')
    assert detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('suffix',['，横坐标的单位为毫秒。','，可以看出方案A更低，纵坐标单位为毫秒。'])
def test_axis_unit_explanation_does_not_remove_a_real_visual_pointer(suffix):
    doc,objects=bare_scene('2.1','传统GC算法的暂停时间均值对比可见2.1'+suffix,'传统GC算法暂停时间均值对比')
    assert not detect_rules(build_index(doc,objects),[15])['15']['findings']


@pytest.mark.parametrize('separator',['。','，而'])
def test_same_scalar_spelling_does_not_override_a_distinct_actual_visual_pointer(separator):
    text='方案A的平均暂停时间为2.1毫秒'+separator+'两方案暂停时间均值对比可见2.1，可以看出方案B更高。'
    doc,objects=bare_scene('2.1',text,'两方案暂停时间均值对比',nodes=['A=2.1ms','B=4.3ms'])
    assert not detect_rules(build_index(doc,objects),[15])['15']['findings']
