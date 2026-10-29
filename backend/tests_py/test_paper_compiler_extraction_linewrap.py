"""Source-preserving layout normalization; all extraction clients are local fakes."""
import copy
import pytest
from paper_compiler import analysis
from paper_compiler.registry import REGISTRY
from test_paper_compiler_compiler import fixture


def extract(text, value, quote=None):
    state = {'evidence': []}
    node = {'id': 'entry', 'text': text}
    result = analysis._extract_field(node, 'title',
        {'state': 'observed', 'value': value, 'quote': text if quote is None else quote}, True, state)
    return result, state['evidence']


@pytest.mark.parametrize('wrap', ['-\n', '-\r\n', '-\n  ', '- \n\t'])
def test_exact_quote_linewrap_keeps_hyphen_and_source_offsets(wrap):
    quote = 'security best practices vio' + wrap + 'lation'
    text = '[9] SHAMIM S I. ' + quote + '[C].'
    value = 'security best practices vio-lation'
    fact, evidence = extract(text, value, quote)
    start = text.index(quote)
    assert fact['state'] == 'observed'
    assert fact['value'] == value
    assert fact['source_range'] == [start, start + len(quote)]
    assert evidence[0]['quote'] == quote
    assert text[evidence[0]['start']:evidence[0]['end']] == quote
    assert evidence[0]['transcription_policy'] == analysis.BIBLIOGRAPHY_EXTRACTION_POLICY
    assert all(text[a:b].isspace() for a,b in evidence[0]['linewrap_join_ranges'])


@pytest.mark.parametrize('text,value,quote', [
    ('security vio-\nlation', 'security vio-lution', None),
    ('security best practices vio-\nlation', 'security vio-lation', None),
    ('security vio-\n\nlation', 'security vio-lation', None),
    ('security vio-\n \nlation', 'security vio-lation', None),
    ('security vio- lation', 'security vio-lation', None),
    ('security vio-\nlation', 'security vio-lation', 'security vio-lation'),
    ('security vio-\nlation', 'security vio-lation', 'security vio- lation'),
    ('security vio-\n_lation', 'security vio-_lation', None),
])
def test_linewrap_never_invents_changes_omits_or_crosses_paragraphs(text,value,quote):
    fact,evidence=extract(text,value,quote)
    assert fact['state']=='unknown'
    assert evidence==[]


def test_existing_plain_whitespace_transcription_stays_supported():
    fact,evidence=extract('A study of\nneural networks', 'study of neural networks', 'study of neural networks')
    assert fact['state']=='observed'
    assert evidence[0]['quote']=='study of\nneural networks'

def test_field_transcription_rejoins_a_nonhyphenated_word_split():
    quote='Anamorphic Encryption: Private Communication Again\nst a Dictator'
    fact,evidence=extract('[1] PERSIANO G. '+quote+'[C/OL].',
                          'Anamorphic Encryption: Private Communication Against a Dictator', quote)
    assert fact['state']=='observed'
    assert fact['value'].endswith('Against a Dictator')
    assert evidence[0]['quote']==quote
    assert evidence[0]['linewrap_join_ranges']==[[quote.index('\n')+len('[1] PERSIANO G. '), quote.index('\n')+len('[1] PERSIANO G. ')+1]]


def test_field_transcription_rejoins_or_retains_end_of_line_hyphen():
    quote='Post-quantum cryptogra-\nphy'
    for value in ('Post-quantum cryptography', 'Post-quantum cryptogra-phy'):
        fact,evidence=extract('[2] '+quote, value, quote)
        assert fact['state']=='observed'
        assert evidence[0]['linewrap_join_ranges']


def test_field_transcription_never_joins_a_non_soft_or_paragraph_break():
    for quote,value in [('Authors.\nTitle', 'Authors.Title'), ('first\n\nsecond', 'firstsecond')]:
        fact,evidence=extract('[3] '+quote, value, quote)
        assert fact['state']=='unknown'
        assert evidence==[]


@pytest.mark.parametrize('size',['1','8'])
def test_extraction_policy_invalidates_derived_cache_without_changing_model_request(tmp_path,monkeypatch,size):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE',size)
    ir,_=fixture(tmp_path)
    packages=[{'rule_ir':{'requires':['bibliography_fields']},'registry':REGISTRY}]
    class LocalModel:
        config={'MAAS_MODEL':'local-fake','MAAS_MODEL_VERSION':'test'}
        def __init__(self):self.requests=[]
        def complete_json(self,*args):
            self.requests.append(copy.deepcopy(args))
            return {'entries':[{'id':'entry','complete':True,'fields':{'title':{'state':'observed','value':'Hello','quote':'Hello'}}}]}
    client=LocalModel()
    def run():return analysis.enrich(ir,packages,client=client,gateway=None,cache_dir=tmp_path/'cache',snapshot_id='test-only')
    monkeypatch.setattr(analysis,'BIBLIOGRAPHY_EXTRACTION_POLICY','test-policy-old',raising=False)
    run();run()
    assert len(client.requests)==1
    monkeypatch.setattr(analysis,'BIBLIOGRAPHY_EXTRACTION_POLICY','test-policy-new')
    run()
    assert len(client.requests)==2
    assert client.requests[0]==client.requests[1], 'existing raw response key must stay unchanged'
    assert analysis.bibliography_execution_policy()['extraction_policy']=='test-policy-new'


def test_compact_model_fields_remain_source_grounded(tmp_path):
    from paper_compiler.analysis import base_analysis, parse_entries
    from test_paper_compiler_bibliography_batch import paper
    class CompactModel:
        def complete_json(self, *_):
            return {'entries':[{'id':'e0','complete':True,'fields':{
                'title':'Anamorphic Encryption: Private Communication Against a Dictator',
                'authors':['PERSIANO G', 'YUNG M']}}]}
    ir=paper(tmp_path, 1, ['[1] PERSIANO G, YUNG M. Anamorphic Encryption: Private Communication Again\nst a Dictator[C]. 2022.'])
    analysis_state=base_analysis(ir); parse_entries(ir, analysis_state, CompactModel(), batch_size=1)
    fields=analysis_state['results']['bibliography_fields']['e0']
    assert fields['title']['state']=='observed'
    assert fields['title']['value'].endswith('Against a Dictator')
    assert fields['authors']['state']=='observed'
    evidence={e['id']:e for e in analysis_state['evidence']}
    assert evidence[fields['title']['evidence_ids'][0]]['linewrap_join_ranges']
