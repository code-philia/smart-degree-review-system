"""Direct regressions for source-backed identity, bounded semantic batches and review shape."""
from copy import deepcopy
import pytest
from paper_compiler import identity, program_analysis as runtime, conflict_review as review
from test_paper_compiler_program_analysis_batch import paper, BatchModel, Gateway, package
from test_paper_compiler_r33_reason_grounding import ground
from test_paper_compiler_conflict_witness import FIXTURES

def identities(url='https://arxiv.org/abs/1807.04320'):
    entry={'title':'An Example Research Work','authors':['Jane Smith'],'year':2018,'url':url}
    common={'title':entry['title'],'authors':['Jane Smith'],'year':2018}
    records=[{'id':'conference','status':'ok','work':dict(common,doi='10.1000/conference',url='https://doi.org/10.1000/conference')},
             {'id':'preprint','status':'ok','work':dict(common,doi='10.48550/arxiv.1807.04320',url='https://arxiv.org/abs/1807.04320')}]
    return entry,records

def test_explicit_arxiv_url_selects_only_matching_existing_preprint():
    entry,records=identities();before=deepcopy((entry,records));result=identity.resolve_identity(entry,records)
    assert result['state']=='observed' and result['value'] is True
    assert result['work']['doi']=='10.48550/arxiv.1807.04320' and result['evidence_ids']==['preprint']
    assert (entry,records)==before

@pytest.mark.parametrize('url',['https://arxiv.org.evil.test/abs/1807.04320','https://user@arxiv.org/abs/1807.04320','https://arxiv.org/abs/1807.99999','https://arxiv.org/abs/1807.04320v2'])
def test_url_pin_rejects_foreign_identity_host_and_version(url):
    entry,records=identities(url);assert identity.resolve_identity(entry,records)['state']=='unknown'

def test_conflicting_explicit_doi_and_url_do_not_collapse_editions():
    entry,records=identities();entry['doi']='10.1000/conference'
    assert identity.resolve_identity(entry,records)['state']=='unknown'

def test_no_url_preserves_ambiguity_and_existing_doi_exact_pin():
    entry,records=identities();entry.pop('url');assert identity.resolve_identity(entry,records)['state']=='unknown'
    entry['doi']='10.48550/arxiv.1807.04320';assert identity.resolve_identity(entry,records)['work']['doi']==entry['doi']

def test_thinking_reference_batches_cap_two_without_changing_other_batches(tmp_path,monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    model=BatchModel();model.semantic_thinking=True;ir=paper(tmp_path,5);before=deepcopy(ir)
    result=runtime.analyze_programs(ir,[package('ReferenceUse',{'related':'boolean'})],client=model,gateway=Gateway(),cache_dir=tmp_path/'cache')
    assert [len(x[0]['nodes']) for x in model.batches]==[2,2,1]
    assert [x[1] for x in model.batches]==[16384,16384,12000]
    assert result['policy']['thinking_reference_batch_limit']==2 and ir==before
    other=tmp_path/'other';other.mkdir();m=BatchModel();m.semantic_thinking=True
    result=runtime.analyze_programs(paper(other,5),[package()],client=m,gateway=None,cache_dir=other/'cache')
    assert [len(x[0]['nodes']) for x in m.batches]==[5]
    assert 'thinking_reference_batch_limit' not in result['policy']

def shared_answer(packet):
    wire=review.model_input(packet);node=wire['nodes'][0]
    p=next(a for a in node['assertions'] if a['origin']=='paper');e=next(a for a in node['assertions'] if a['origin']=='external')
    return {'results':{node['node']['id']:{'decision':'confirmed_conflict','same_entity':True,'same_property':True,'same_scope':True,
        'citation_purpose':'assertion','relation':'mutually_exclusive_values','reason':'The independent source assertions concern the same method property and scope.',
        'alignment':{'entity':'identified method','property':'method capability','scope':'method operation'},
        'witness':{'citing':{'quote_span_id':p['assertion_span_ids'][0],'value':'denied'},'cited':{'quote_span_id':e['assertion_span_ids'][0],'value':'affirmed'}}}}}

def test_shared_alignment_is_minted_only_from_independent_explicit_review():
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=shared_answer(packet);before=deepcopy(answer)
    proofs=review.accept_review(packet,answer);assert proofs and answer==before
    proof=review.trusted_verification(f['raw']['fields']['conflict'],f['data'],proofs)
    assert proof['witness']['citing']['scope']==proof['witness']['cited']['scope']=='method operation'

@pytest.mark.parametrize('bad',['missing_alignment','side_entity','side_scope','different_entity_bool','different_scope_bool'])
def test_shared_alignment_missing_mixed_or_unresolved_comparison_is_rejected(bad):
    f=deepcopy(FIXTURES[0]);packet=review.prepare_review(f['request'],f['raw'],f['data']);answer=shared_answer(packet);row=next(iter(answer['results'].values()))
    if bad=='missing_alignment':row.pop('alignment')
    elif bad=='side_entity':row['witness']['cited']['entity']='foreign work'
    elif bad=='side_scope':row['witness']['cited']['scope']='different scope'
    elif bad=='different_entity_bool':row['same_entity']=False
    else:row['same_scope']=False
    assert not review.accept_review(packet,answer)

def test_negative_reason_does_not_cross_sentence_boundary():
    reason='The properties are attributed to SFO, not Adam. The cited work states that SFO failed on stochastic regularization.'
    assert ground(reason)[0]['state']=='observed'

@pytest.mark.parametrize('reason',['The source does not mention this method.','The paper never states this result.','全文未提及该方法。'])
def test_real_absence_reason_still_unknown(reason):
    assert ground(reason,negative=True)[0]['state']=='unknown'


def test_negation_of_missing_detail_does_not_reject_supported_evidence():
    assert ground('This is positive semantic incompatibility, not merely a missing detail.')[0]['state']=='observed'

def test_missing_detail_without_verified_negative_proof_stays_unknown():
    assert ground('The paper omits that detail.',negative=True)[0]['state']=='unknown'

def test_review_prioritizes_positive_conflict_without_relabeling_proof():
    assert 'Evaluate positive conflict FIRST' in review.INSTRUCTIONS
    assert 'confirmed_unsupported_attribution ONLY when no such positive conflict' in review.INSTRUCTIONS
    assert 'decisions are not interchangeable' in review.INSTRUCTIONS
