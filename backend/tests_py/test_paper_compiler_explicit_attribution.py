"""Conservative fixed citation eligibility, without model or transport calls."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from paper_compiler import conflict_review as review
from paper_compiler.program_analysis import analyze_programs,_ground_fields
from paper_compiler.fixed_r33 import build_r33_package
from test_paper_compiler_complete_work_support import sample,answer as scope_answer
from test_paper_compiler_conflict_witness import answered
from test_paper_compiler_program_analysis import Model,Gateway,paper,package
ACTUAL=json.loads((Path(__file__).parent/'fixtures/r33_author_implementation_attribution_counterexample.json').read_text())

def explicit(text='文献[1]提出该方法可以证明所有程序终止。',selector='1',marker='[1]'):
    request,raw,data=sample()
    data['node'].update(kind='ReferenceUse',text=marker,attrs={'selector':{'kind':'numeric','value':selector}})
    data['citation_context'].update(text=text,selector={'kind':'numeric','value':selector})
    data['sources'][0]['text']=text;raw['fields']['relation']['quotes'][0]['quote']=text
    return request,raw,data


def test_actual_decoder_implementation_cannot_be_upgraded_to_cited_contribution():
    f=deepcopy(ACTUAL);before=deepcopy(f)
    packet=review.prepare_review(f['request'],f['raw'],f['data'])
    assert review.model_input(packet)==f['old_wire']
    proofs=review.accept_review(packet,f['receipt']['answer'])
    assert proofs=={}
    assert _ground_fields(f['request'],f['raw'],f['data'],True,conflict_verifications=proofs)[0]['relation']['state']=='unknown'
    assert f==before

@pytest.mark.parametrize('text,selector,marker,eligible',[
    ('文献[1]提出该方法支持回归。','1','[1]',True),
    ('被引论文[1]中报告该模型不使用卷积。','1','[1]',True),
    ('[1]中的方法支持回归。','1','[1]',True),
    ('The cited work [1] reports that the model supports regression.','1','[1]',True),
    ('The authors of the cited work state: “The model supports regression.” [1].','1','[1]',False),
    ('本解码器基于扩散Transformer模型[1]，共12层。','1','[1]',False),
    ('The cited work states that attention models work. Our decoder is a flow-matching diffusion Transformer [1].','1','[1]',False),
    ('文献[2]提出一种方法。本解码器采用Transformer[1]。','1','[1]',False),
    ('文献[1,2]报告该模型支持回归。','1','[1,2]',False),
    ('文献[1]提出方法。我们采用模型[1]。','1','[1]',False),
    ('文献[2]提出该方法支持回归。','1','[1]',False),
])
def test_anchor_is_explicit_single_current_selector(text,selector,marker,eligible):
    _,_,data=explicit(text,selector,marker)
    helper=getattr(review,'explicit_source_attribution',None)
    assert callable(helper),'shared deterministic attribution helper missing'
    assert bool(helper(data)) is eligible

@pytest.mark.parametrize('kind',['positive','complete_work'])
def test_explicit_attribution_retains_both_negative_proof_kinds(kind):
    request,raw,data=explicit();packet=review.prepare_review(request,raw,data)
    answer=answered(packet) if kind=='positive' else scope_answer(packet)
    assert review.accept_review(packet,answer)

@pytest.mark.parametrize('kind',['positive','complete_work'])
def test_author_implementation_without_anchor_never_seals_either_kind(kind):
    request,raw,data=explicit('本方法采用已有框架[1]，我们新增终止证明。')
    packet=review.prepare_review(request,raw,data)
    answer=answered(packet) if kind=='positive' else scope_answer(packet)
    assert review.accept_review(packet,answer)=={}


@pytest.mark.parametrize('batch_size',[1,8])
def test_no_anchor_fixed_request_does_not_call_producer_or_review(tmp_path,monkeypatch,batch_size):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE',str(batch_size))
    model=Model();ir=paper(tmp_path)
    result=analyze_programs(ir,[build_r33_package()],client=model,gateway=Gateway(),cache_dir=tmp_path/'cache')
    assert model.semantic_calls==0
    fact=result['results']['fixed_citation_support_v1']['use']['relation']
    assert fact['state']=='unknown' and 'explicit source attribution' in fact['reason']
    assert all(task!='positive-conflict-review/1.0' for task,_,_ in model.requests)


def test_other_generated_request_keeps_its_original_semantic_path(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
    model=Model();analyze_programs(paper(tmp_path),[package()],client=model,gateway=None,cache_dir=tmp_path/'cache')
    assert model.semantic_calls==1


def test_explicit_fixed_request_keeps_producer_execution_available(tmp_path,monkeypatch):
    from paper_compiler_r33_test_fixtures import attributed_paper
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
    model=Model()
    analyze_programs(attributed_paper(tmp_path),[build_r33_package()],client=model,gateway=Gateway(),cache_dir=tmp_path/'cache')
    assert model.semantic_calls==1
