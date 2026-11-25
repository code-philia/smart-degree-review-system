"""Recover native sibling experiments without trusting matching numbers alone."""
import copy
import pytest
import numeric_consistency as n


def model_and_target(metric='cell voltage',number='1.79',unit='V',method='Electrode-X'):
    sections={sid:{'section_id':sid,'parent_id':parent,'title':title,'block_ids':[]}for sid,parent,title in [
        ('ch',None,'Chapter 4 Electrode-X'),('wrong','ch','4.3.4 Mechanistic insights'),
        ('right','ch','4.3.6 Overall Water Splitting Performance'),
        ('intro','ch','4.1 Introduction'),('conclusion','ch','4.4 Conclusion'),
        ('other',None,'Chapter 5 Other material'),('other-exp','other','5.3 Experimental Results')]}
    def block(bid,sid,text,page):return {'block_id':bid,'source_node_id':bid,'section_id':sid,'block_type':'Paragraph','text':text,'page':page,'provenance':[{'bbox':[10,10,100,30]}]}
    model={'sections':sections,'blocks':[
        block('mechanism','wrong','Electrode-X has a fitted resistance of 1.79 ohm.',126),
        block('native-result','right','Electrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.',135)],'tables':[]}
    declaration={'id':'d1','metric':metric,'method':method,'number':number,'unit':unit,'condition':'1.0 A cm-2','text':'本文电池电压为1.79 V。'}
    mapping={'declaration_id':'d1','chapter_id':'ch','experiment_section_ids':['wrong']}
    return model,declaration,mapping,block


@pytest.mark.parametrize('metric,number,unit,text,page',[
    ('cell voltage','1.79','V','Electrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.',135),
    ('voltage reduction','0.195','V','Electrode-X enables MOR-assisted water splitting with a cell voltage 0.195 V lower at 1.0 A cm-2.',188),
    ('voltage reduction','184','mV','Electrode-X enables MOR-assisted water splitting, providing a cell voltage saving of 0.184 V at 1.0 A cm-2.',237),
])
def test_recalls_source_backed_sibling_result_including_equivalent_units(metric,number,unit,text,page):
    model,d,mapping,_=model_and_target(metric,number,unit)
    model['blocks'][1].update(text=text,page=page)
    before=copy.deepcopy((model,d,mapping))
    candidates,diagnostics=n.retrieve_candidates([d],[mapping],model)
    hit=next(c for c in candidates if c['source_node_id']=='native-result')
    assert hit['text']==text and hit['page']==page and hit['is_primary']
    assert hit['provenance']==[{'bbox':[10,10,100,30]}]
    assert diagnostics[0]['chapter_recall']['chapter_id']=='ch'
    assert (model,d,mapping)==before


def test_recall_can_find_a_conflicting_number_without_certifying_equality():
    model,d,mapping,_=model_and_target()
    model['blocks'][1]['text']='Electrode-X requires a cell voltage of 1.95 V at 1.0 A cm-2.'
    candidates,_=n.retrieve_candidates([d],[mapping],model)
    assert any('1.95 V' in c['text']for c in candidates)
    assert all('status'not in c for c in candidates)


@pytest.mark.parametrize('sid,text',[
    ('other-exp','Electrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('intro','Electrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('conclusion','Electrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('right','Unrelated-Y requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('right','Electrode-X2 requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('right','Electrode-X-extra requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('right','PrefixElectrode-X requires a cell voltage of 1.79 V at 1.0 A cm-2.'),
    ('right','Electrode-X has a fitted resistance of 1.79 ohm.'),
])
def test_same_number_wrong_chapter_background_method_or_metric_cannot_trigger_recall(sid,text):
    model,d,mapping,_=model_and_target()
    model['blocks'][1].update(section_id=sid,text=text)
    candidates,_=n.retrieve_candidates([d],[mapping],model)
    assert not any(c['source_node_id']=='native-result'for c in candidates)


def test_recall_retains_complete_native_blocks_and_bounds_context_size():
    model,d,mapping,block=model_and_target()
    model['blocks'].extend(block('long-'+str(i),'right','Electrode-X cell voltage '+str(i)+' V. '+'x'*2000,136+i)for i in range(30))
    candidates,diagnostics=n.retrieve_candidates([d],[mapping],model)
    recall=[c for c in candidates if c.get('retrieval_scope')=='chapter_recall']
    assert recall and sum(len(c['text'])for c in recall)<=8000
    source={b['block_id']:b['text']for b in model['blocks']}
    assert all(c['text']==source[c['block_id']]for c in recall)
    assert len([c for c in recall if c['is_primary']])<=4


def test_recalled_evidence_still_requires_real_candidate_identity_and_page():
    model,d,mapping,_=model_and_target()
    candidates,_=n.retrieve_candidates([d],[mapping],model)
    hit=next(c for c in candidates if c['source_node_id']=='native-result')
    payload={'results':[{'declaration_id':'d1','status':'consistent','reason':'Direct native statement supports the target.','suggestion':'','evidence':[{'candidate_id':hit['candidate_id']}]}]}
    checked,errors=n.validated_results(n.resolve_citations(payload,candidates),[d],candidates)
    assert not errors and checked[0]['evidence'][0]['page']==135
    invalid=copy.deepcopy(payload);invalid['results'][0]['evidence'][0].update(quote=hit['text'],page=999)
    _,errors=n.validated_results(invalid,[d],candidates)
    assert errors


@pytest.mark.parametrize('method',['本方法','本文方法','本文模型','proposed method','our model','the proposed approach'])
def test_generic_self_reference_cannot_bind_a_different_method_branch(method):
    model,d,mapping,_=model_and_target(method=method)
    model['sections']['right']['title']='4.3.6 OtherModel Performance'
    model['blocks'][1]['text']=method+' requires a cell voltage of 1.79 V at 1.0 A cm-2.'
    candidates,_=n.retrieve_candidates([d],[mapping],model)
    assert not any(c['source_node_id']=='native-result'for c in candidates)


def test_native_condition_headings_reach_verifier_without_becoming_a_verdict():
    model,d,mapping,_=model_and_target()
    d['condition']='alkaline electrolyte'
    prompts=[]
    for condition in ['alkaline electrolyte','acidic electrolyte']:
        model['sections']['right']['title']='4.3.6 Performance in '+condition
        candidates,_=n.retrieve_candidates([d],[mapping],model)
        prompt=n.verifier_prompt({'declarations':[d],'mappings':[mapping]},candidates)
        assert 'Performance in '+condition in prompt
        prompts.append(prompt)
    assert prompts[0]!=prompts[1]
