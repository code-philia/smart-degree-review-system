from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_bilingual_semantic_lint as lint

def facts():
    return {'chinese_keywords':{'values':['图数据库','不定跳路径'],'text':'图数据库，不定跳路径'},
            'english_keywords':{'values':['Graph Database','Recursive Path'],'text':'Graph Database, Recursive Path'},
            'chinese_abstract':'本文研究不定跳路径。','english_abstract':'We study variable-length paths.',
            'terminology_context':[{'quote':'递归路径查询（Recursive Path Query）的路径长度不定。','page_number':27}],
            'locations':{}}

def pair(zh,en,match=True):
    return {'chinese':zh,'english':en,'match':match,'reason':'本篇定义对应同一研究对象' if match else '两个概念指不同研究对象'}

def run_with(review):
    initial={'outcome':'inconsistent','summary':'初审认为译法不同','pairs':[]}
    with patch.object(lint,'request_json',side_effect=[(initial,{'input_tokens':1,'output_tokens':1}),
                                                   (review,{'input_tokens':2,'output_tokens':2})]) as request:
        result=lint._run_semantic_rule({},facts(),'bilingual_keywords_correspondence_check')
    return result,request

def test_keyword_mismatch_gets_context_and_independent_evidence_review():
    review={'outcome':'consistent','summary':'两侧概念对应','pairs':[pair('图数据库','Graph Database'),pair('不定跳路径','Recursive Path')],
            'missing_chinese':[],'missing_english':[]}
    result,request=run_with(review)
    assert request.call_count==2
    assert '递归路径查询（Recursive Path Query）' in request.call_args_list[1].args[0][0]['content']
    assert result['outcome']=='passed' and result['findings']==[]
    assert result['model_usage']=={'input_tokens':3,'output_tokens':3}

def test_review_cannot_claim_pass_without_covering_both_keyword_lists():
    review={'outcome':'consistent','summary':'对应关系尚不能全部确认','pairs':[pair('图数据库','Graph Database')],
            'missing_chinese':[],'missing_english':[]}
    result,_=run_with(review)
    assert result['outcome']=='inconclusive'
    assert result['findings']==[]

def test_genuine_keyword_concept_conflict_still_alarms():
    review={'outcome':'inconsistent','summary':'两侧第二个关键词指不同的研究对象',
            'pairs':[pair('图数据库','Graph Database'),pair('不定跳路径','Recursive Path',False)],
            'missing_chinese':[],'missing_english':[]}
    result,_=run_with(review)
    assert result['outcome']=='issues_found' and len(result['findings'])==1

def test_missing_keyword_still_alarms():
    review={'outcome':'inconsistent','summary':'英文缺少不定跳路径对应项','pairs':[pair('图数据库','Graph Database')],
            'missing_chinese':['Recursive Path'],'missing_english':['不定跳路径']}
    result,_=run_with(review)
    assert result['outcome']=='issues_found'

def test_explicit_missing_term_can_have_a_null_counterpart_pair():
    f=facts();f['english_keywords']['values']=['Graph Database']
    review={'outcome':'inconsistent','summary':'英文缺少不定跳路径对应项',
            'pairs':[pair('图数据库','Graph Database'),pair('不定跳路径',None,False)],
            'missing_chinese':[],'missing_english':['不定跳路径']}
    with patch.object(lint,'request_json',side_effect=[({'outcome':'inconsistent','summary':'初审'},{}),(review,{})]):
        result=lint._run_semantic_rule({},f,'bilingual_keywords_correspondence_check')
    assert result['outcome']=='issues_found'

def test_untraceable_reviewed_terms_cannot_make_a_pass():
    review={'outcome':'consistent','summary':'对应关系尚不能全部确认','pairs':[pair('图数据库','Graph Database'),pair('不定跳路径','Variable-Length Path')],
            'missing_chinese':[],'missing_english':[]}
    result,_=run_with(review)
    assert result['outcome']=='inconclusive'

def test_review_cannot_change_hyphens_or_word_boundaries_in_source_terms():
    f=facts();f['english_keywords']['values']=['Graph Database','Re-sign']
    review={'outcome':'consistent','summary':'对应关系尚不能全部确认',
            'pairs':[pair('图数据库','Graph Database'),pair('不定跳路径','Resign')],
            'missing_chinese':[],'missing_english':[]}
    with patch.object(lint,'request_json',side_effect=[({'outcome':'inconsistent','summary':'初审'},{}),(review,{})]):
        result=lint._run_semantic_rule({},f,'bilingual_keywords_correspondence_check')
    assert result['outcome']=='inconclusive'

@pytest.mark.parametrize('outcome',[None,'INCONCLUSIVE',' inconclusive ','unexpected'])
def test_unknown_or_inconclusive_review_outcomes_never_turn_into_a_pass(outcome):
    review={'outcome':outcome,'summary':'对应关系尚不能全部确认',
            'pairs':[pair('图数据库','Graph Database'),pair('不定跳路径','Recursive Path')],
            'missing_chinese':[],'missing_english':[]}
    result,_=run_with(review)
    assert result['outcome']=='inconclusive'

@pytest.mark.parametrize('reason',[{},[],True])
def test_nontext_review_reason_is_not_verified_evidence(reason):
    row=pair('不定跳路径','Recursive Path');row['reason']=reason
    review={'outcome':'consistent','summary':'对应关系尚不能全部确认',
            'pairs':[pair('图数据库','Graph Database'),row],'missing_chinese':[],'missing_english':[]}
    result,_=run_with(review)
    assert result['outcome']=='inconclusive'

def test_bulleted_english_contribution_starts_its_own_sentence():
    sentences=lint._abstract_sentences('This improves spatial signal transmission.\n• Fine-grained Sensing: RF signals are weak.')
    assert sentences==['This improves spatial signal transmission.','• Fine-grained Sensing: RF signals are weak.']

def test_context_cannot_replace_missing_abstract_information():
    f=facts()
    prompt=lint.prompt_for('bilingual_keywords_correspondence_check',f)
    assert '递归路径查询（Recursive Path Query）' in prompt
    assert '正文' in prompt and '术语' in prompt
