"""No transport, real archived target projections plus direct structural proof tests."""
import importlib.util,json,copy
from pathlib import Path
import pytest
from paper_compiler.programs import execute_pure
HERE=Path(__file__).parent
from paper_compiler import fixed_r31 as module
CODE=module.build_r31_package()['code']
ACTUAL=json.loads((HERE/'fixtures/r31_source_proof_archive_cases.json').read_text())

def run(payload):return execute_pure(CODE,payload)[0]

@pytest.mark.parametrize('f',ACTUAL,ids=lambda f:f['node_id'])
def test_actual_role_uncertainty_never_becomes_missing_field_alarm(f):
    before=copy.deepcopy(f);row=run(f['payload'])
    assert row['status']=='UNKNOWN'
    assert f==before


def title_payload(text):
    return {'ir':{'nodes':[{'id':'e','kind':'BibliographyEntry','text':text}]},'analysis':{'coverage':{'e':{'status':'complete'}},'results':{'bibliography_fields':{'e':{'title':{'state':'confirmed_absent'},'type_code':{'state':'observed','value':'J'}}}}}}


def test_literal_empty_title_slot_retains_missing_title_alarm():
    row=run(title_payload('[1] [J]. Journal, 2020.'))
    assert row['status']=='VIOLATION' and '缺少必备题名' in row['message']

@pytest.mark.parametrize('text',['[1] AUTHOR A. A complete title[J]. Journal, 2020.','[1] AUTHOR A.[J]. Journal, 2020.','[1] 1984[M]. Publisher, 2020.','[1] α[J]. Journal, 2020.','[1] ∑[J]. Journal, 2020.'])
def test_nonempty_literal_prefix_with_model_absence_is_unresolved_not_missing(text):
    assert run(title_payload(text))['status']=='UNKNOWN'


def standard(identifier='ISO 8601-1:2019', *, visible='',metadata_year=2019,metadata_doi='10.9999/standard',identity=True):
    title='Time representation';text='[1] '+title+'[S]. '+visible+' 2019. DOI:10.9999/standard.'
    start=text.index('2019',text.index('[S]'))
    fields={'title':{'state':'observed','value':title},'type_code':{'state':'observed','value':'S'},'year':{'state':'observed','value':'2019','source_range':[start,start+4]},'standard_number':{'state':'confirmed_absent'}}
    work={'title':title,'year':metadata_year,'doi':metadata_doi,'type':'standard','standard_number':identifier}
    return {'ir':{'nodes':[{'id':'e','kind':'BibliographyEntry','text':text}]},'analysis':{'coverage':{'e':{'status':'complete'}},'evidence':[{'id':'verified-standard','status':'ok','provider':'public-catalog-fixture','work':work}],'results':{'bibliography_fields':{'e':fields},'external_work':{'e':{'exists':{'state':'observed','value':identity,'evidence_ids':['verified-standard']}}}}}}


def test_exact_manifestation_metadata_identifier_and_true_omission_retains_alarm():
    row=run(standard())
    assert row['status']=='VIOLATION' and '标准编号' in row['message'] and 'verified-standard' in row['evidence_ids']

@pytest.mark.parametrize('kwargs',[{'identity':False},{'metadata_year':2020},{'metadata_doi':'10.9999/other'},{'identifier':'Version 1.21 Part 1'},{'identifier':''}])
def test_unknown_work_version_or_identifier_role_does_not_alarm(kwargs):
    assert run(standard(**kwargs))['status']=='UNKNOWN'

@pytest.mark.parametrize('visible',['GB/T 7714-2019','ISO 8601-1:2019','RFC 3339'])
def test_visible_standard_identifier_overrides_model_absent(visible):
    row=run(standard(visible=visible))
    assert row['status']=='PASS' and 'standard_number' not in row['message']


@pytest.mark.parametrize('qualifier',['Version 1.21.','Part 1.'])
def test_unresolved_version_or_part_is_not_proved_by_a_coarse_identifier(qualifier):
    payload=standard();payload['ir']['nodes'][0]['text']=payload['ir']['nodes'][0]['text'].replace(' 2019.', ' '+qualifier+' 2019.')
    text=payload['ir']['nodes'][0]['text'];start=text.index('2019')
    payload['analysis']['results']['bibliography_fields']['e']['year']['source_range']=[start,start+4]
    assert run(payload)['status']=='UNKNOWN'
