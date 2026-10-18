import copy
import pytest
from paper_compiler.analysis import locate_quote, parse_entries, bind_references, judge_relevance, base_analysis
from paper_compiler.contracts import validate_analysis
from test_paper_compiler_compiler import fixture

class FieldModel:
    def __init__(self,fields,complete=True):self.fields=fields;self.complete=complete
    def complete_json(self,task,instructions,data,max_tokens):
        return {'entries':[{'id':n['id'],'fields':copy.deepcopy(self.fields),'complete':self.complete} for n in data['entries']]}


def test_quote_offsets_preserve_source_linebreaks():
    text='A study of\nneural networks.'
    start,end=locate_quote(text,'study of neural networks')
    assert text[start:end]=='study of\nneural networks'
    with pytest.raises(ValueError):locate_quote(text,'invented words')


def test_fields_require_source_quotes_and_typed_values(tmp_path):
    ir,_=fixture(tmp_path);node=next(n for n in ir['nodes'] if n['kind']=='BibliographyEntry');node['text']='[1] Vaswani A. Attention Is All You Need[J]. 2017.'
    a=base_analysis(ir)
    parse_entries(ir,a,FieldModel({'title':{'state':'observed','value':'Attention Is All You Need','quote':'Attention Is All You Need'},
        'year':{'state':'observed','value':'2017','quote':'2017'}, 'doi':{'state':'confirmed_absent'}}))
    facts=a['results']['bibliography_fields'][node['id']]
    assert facts['title']['value']=='Attention Is All You Need'
    assert facts['doi']['state']=='confirmed_absent' and facts['doi']['search_scope']==node['id']
    assert facts['authors']['state']=='unknown'
    validate_analysis(ir,a)


def test_invented_quote_and_incomplete_absence_remain_unknown(tmp_path):
    ir,_=fixture(tmp_path);a=base_analysis(ir)
    parse_entries(ir,a,FieldModel({'title':{'state':'observed','value':'Fake title','quote':'Fake title'},
        'doi':{'state':'confirmed_absent'}},complete=False))
    facts=next(iter(a['results']['bibliography_fields'].values()))
    assert facts['title']['state']=='unknown' and facts['doi']['state']=='unknown'


def test_changed_field_cannot_be_justified_by_another_quote(tmp_path):
    ir,_=fixture(tmp_path);a=base_analysis(ir)
    parse_entries(ir,a,FieldModel({'title':{'state':'observed','value':'Fabricated title','quote':'Hello'}}))
    assert next(iter(a['results']['bibliography_fields'].values()))['title']['state']=='unknown'

class RelevanceModel:
    def __init__(self,value):self.value=value
    def complete_json(self,*args):return self.value

def decision(relation='related',basis='explicit_support',quote='We use convolutional networks'):
    return {'relation':relation,'purpose':'method','intent_quote':'We apply convolutional networks','evidence_id':'content1',
        'evidence_quote':quote,'basis':basis,'reason':'A method can transfer across disciplines.'}


def test_cross_discipline_method_and_criticism_are_valid_relations():
    context={'paragraph':'We apply convolutional networks [1] to lake images.'}
    content=[{'id':'content1','status':'ok','level':'abstract','coverage':'abstract_only','text':'We use convolutional networks for image recognition.'}]
    result=judge_relevance(context,content,RelevanceModel(decision()))
    assert result['state']=='observed' and result['value'] is True
    result=judge_relevance(context,content,RelevanceModel({**decision(),'purpose':'criticism'}))
    assert result['value'] is True


def test_missing_detail_in_abstract_is_not_negative_proof():
    context={'paragraph':'We apply convolutional networks [1].'}
    content=[{'id':'content1','status':'ok','level':'abstract','coverage':'abstract_only','text':'We study fish.'}]
    result=judge_relevance(context,content,RelevanceModel(decision('unrelated','missing_detail','We study fish.')))
    assert result['state']=='unknown'


def test_negative_relevance_requires_explicit_scope_contradiction():
    context={'paragraph':'We apply convolutional networks [1].'}
    content=[{'id':'content1','status':'ok','level':'abstract','coverage':'abstract_only','text':'This work exclusively inventories medieval coins and makes no computational or methodological contribution.'}]
    d=decision('unrelated','explicit_scope_contradiction',content[0]['text'])
    result=judge_relevance(context,content,RelevanceModel(d))
    assert result['state']=='observed' and result['value'] is False


def test_untraceable_semantic_judgment_is_unknown():
    result=judge_relevance({'paragraph':'Unrelated source'},[{'id':'content1','status':'ok','text':'We use convolutional networks'}],RelevanceModel(decision()))
    assert result['state']=='unknown'


def test_analysis_rejects_unknown_evidence_reference(tmp_path):
    ir,a=fixture(tmp_path)
    a['results']['bibliography_fields']['entry']['title']['evidence_ids']=['no-such-evidence']
    with pytest.raises(ValueError,match='evidence'):validate_analysis(ir,a)


def test_incomplete_usage_coverage_does_not_create_numbering_violation(tmp_path):
    from paper_compiler.analysis import ordering_facts
    ir,_=fixture(tmp_path);a=base_analysis(ir);ordering_facts(ir,a)
    assert a['results']['citation_order']['u']['first_appearance_rank']['state']=='unknown'
    assert a['results']['bibliography_order']['entry']['position']['value']==1


def test_complete_usage_order_has_independent_ranks(tmp_path):
    from paper_compiler.analysis import ordering_facts
    ir,_=fixture(tmp_path);ir['coverage']['reference_uses']={'status':'complete'}
    a=base_analysis(ir);ordering_facts(ir,a)
    assert a['results']['citation_order']['u']['first_appearance_rank']['value']==1


def test_compact_explicit_absence_is_scoped_and_omissions_stay_unknown(tmp_path):
    ir,_=fixture(tmp_path);a=base_analysis(ir)
    class CompactModel:
        def complete_json(self,task,instructions,data,max_tokens):
            return {'entries':[{'id':n['id'],'complete':True,'fields':{},'absent':['doi']} for n in data['entries']]}
    parse_entries(ir,a,CompactModel())
    fields=next(iter(a['results']['bibliography_fields'].values()))
    assert fields['doi']['state']=='confirmed_absent'
    assert fields['title']['state']=='unknown'
