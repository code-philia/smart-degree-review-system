from pathlib import Path
import pytest
from pdf_rules.model import PdfDocument, PdfPage, PdfLine
from pdf_rules.index import build_index
from pdf_rules.local_rules import detect_rules


def line(text, box, font=12, bold=False):
    return PdfLine(1,text,box,600,800,font_size=font,bold=bold)


def index_for(lines):
    return build_index(PdfDocument(Path('unseen.pdf'),(PdfPage(1,600,800,tuple(lines),images=((80,220,520,420),)),)))


@pytest.mark.parametrize('word,rule',[('图','15'),('表','16')])
@pytest.mark.parametrize('tail',['中。','内！'])
def test_short_locative_sentence_tail_is_a_reference(word,rule,tail):
    idx=index_for([line('我们将所有实验的变换和拼接操作可视化在',(60,170,540,190)),
                   line(f'{word}7.2{tail}',(60,188,120,204)),
                   line(f'{word}7.2 实验的变换与拼接',(180,440,420,451),10.5,True)])
    assert detect_rules(idx,[11,15,16])[rule]['findings']==[]


@pytest.mark.parametrize('tail',['中。','内！'])
def test_short_locative_reference_still_reports_missing_figure(tail):
    idx=index_for([line(f'图7.2{tail}',(60,188,120,204))])
    r=detect_rules(idx,[11,15])
    assert [f['token'] for f in r['11']['findings']]==['7.2']
    assert r['15']['findings']==[]


@pytest.mark.parametrize('tail',['中。','内！'])
def test_missing_table_reference_does_not_invent_a_table(tail):
    idx=index_for([line(f'表7.2{tail}',(60,188,120,204))])
    assert [x.number for x in idx.table_refs]==['7.2']
    assert idx.tables==[]


@pytest.mark.parametrize('word,rule',[('图','15'),('表','16')])
@pytest.mark.parametrize('title',['中间特征的变化过程。','内部结构与参数设置。'])
def test_substantive_title_starting_with_locative_character_stays_a_caption(word,rule,title):
    idx=index_for([line(f'{word}7.2 {title}',(180,440,420,451),10.5,True)])
    r=detect_rules(idx,[11,15,16])
    assert [f['token'] for f in r[rule]['findings']]==['7.2']
    assert r['11']['findings']==[]


@pytest.mark.parametrize('word,rule',[('图','15'),('表','16')])
@pytest.mark.parametrize('predicate',['中展示了','内给出了','里显示了'])
def test_locative_predicate_is_a_wrapped_prose_citation(word,rule,predicate):
    idx=index_for([line('系统实现了从算法设计到任务调度的统一流程。在',(85,150,525,164)),
                   line(f'{word}7.2{predicate}任务提交后的运行状态。',(85,171,525,185)),
                   line(f'{word}7.2 运行状态',(180,440,420,451),10.5,True)])
    assert len(idx.figures if rule=='15' else idx.tables)==1
    assert detect_rules(idx,[15,16])[rule]['findings']==[]
