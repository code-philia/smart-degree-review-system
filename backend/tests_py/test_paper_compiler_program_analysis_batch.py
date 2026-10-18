"""Opt-in generated-analysis batches keep per-target grounding and cache ownership."""
import copy
import hashlib
import json

import pytest

from paper_compiler import program_analysis as runtime
from paper_compiler.budget import BudgetExceeded
from paper_compiler.contracts import ir_hash, validate_analysis, validate_ir
from paper_compiler.runtime import _evidence_check
from test_paper_compiler_program_analysis import Model, Gateway, package, grounded_reference

BATCH_TASK = 'generated-analysis-batch/1.0'


def paper(tmp_path, count=5, texts=None):
    texts = texts or ['We apply tree models topic-' + str(i) + ' [1].' for i in range(count)]
    entry = '[1] Smith J. Tree Models for Lakes. 2020. doi:10.1000/wrong'
    full = '\n'.join([*texts, entry, 'Unrelated note.'])
    source = tmp_path / 'paper.txt'
    source.write_text(full)
    def node(nid, kind, text=None, children=(), attrs=None):
        start = full.find(text) if text else 0
        return {'id':nid, 'kind':kind, 'text':text, 'children':list(children), 'attrs':attrs or {},
                'provenance':[{'kind':'source','source_id':'src','char_start':start,'char_end':start+len(text)}] if text else []}
    nodes = [node('root','Paper',children=[*['p'+str(i) for i in range(count)],'entry','note'])]
    for i, text in enumerate(texts):
        nodes += [node('p'+str(i),'Paragraph',text,['use'+str(i)]),
                  node('use'+str(i),'ReferenceUse','[1]',attrs={'namespace':'bibliography','expected_kind':'BibliographyEntry',
                       'selector':{'kind':'numeric','value':'1'}})]
    nodes += [node('entry','BibliographyEntry',entry,attrs={'key':'1'}), node('note','Note','Unrelated note.')]
    ir = {'schema_version':'paper-ir/1.0','model_version':'paper-model/1.0','document_id':'batch-doc','revision':'original',
          'root_id':'root','source_artifacts':[{'id':'src','kind':'text','path':str(source),
          'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}], 'nodes':nodes,
          'coverage':{},'profile':{},'layout':{'pages':[]},'extensions':{}}
    validate_ir(ir)
    return ir


class BatchModel(Model):
    def __init__(self, transform=None, fail_on=None, error=None):
        super().__init__()
        self.batches = []
        self.transform = transform
        self.fail_on = fail_on
        self.error = error or RuntimeError('fake HTTP transport failure')

    def complete_json(self, task, instructions, data, max_tokens):
        if task == 'bibliography-fields/1.1':
            return super().complete_json(task, instructions, data, max_tokens)
        assert task == BATCH_TASK, 'opt-in nodes must use the versioned batch protocol'
        self.batches.append((copy.deepcopy(data), max_tokens, instructions))
        if len(self.batches) == self.fail_on:
            raise self.error
        sources = {s['source_id']:s for s in data['sources']}
        answers = {}
        for packed in data['nodes']:
            local = {**packed, 'sources':[sources[sid] for sid in packed['source_ids']]}
            if packed['node']['kind'] == 'ReferenceUse':
                answers[packed['node']['id']] = grounded_reference(local)
            else:
                src = next(s for s in local['sources'] if s['node_id'] == packed['node']['id'])
                answers[packed['node']['id']] = {'fields':{'method':{
                    'state':'observed','value':'tree models','quotes':[{'source_id':src['source_id'],'quote':'tree models'}]}}}
        response = {'results':answers}
        return self.transform(response, data) if self.transform else response


def run(tmp_path, ir, model, *, packages=None, gateway=None):
    result = runtime.analyze_programs(ir, packages or [package()], client=model, gateway=gateway,
                                      cache_dir=tmp_path/'cache')
    validate_analysis(ir, result)
    _evidence_check(ir, result)
    return result


@pytest.fixture(autouse=True)
def opt_in(monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE', '8')


def test_batch_reduces_calls_and_preserves_all_targets_and_source_facts(tmp_path):
    ir = paper(tmp_path, 5)
    before = copy.deepcopy(ir)
    model = BatchModel()
    result = run(tmp_path, ir, model)
    assert len(model.batches) == 1
    assert set(result['results']['method_facts']) == {'p0','p1','p2','p3','p4'}
    assert all(f['method']['state'] == 'observed' for f in result['results']['method_facts'].values())
    assert ir == before and result['paper_ir_sha256'] == ir_hash(ir)
    data, tokens, _ = model.batches[0]
    assert data['schema_version'] == BATCH_TASK and len(data['nodes']) == 5
    assert 15000 <= tokens <= 16384
    assert result['policy']['generated_batch'] == runtime.analysis_execution_policy()


def test_reference_batch_deduplicates_sources_but_grounds_both_sides_and_graph(tmp_path):
    ir = paper(tmp_path, 3)
    model = BatchModel()
    result = run(tmp_path, ir, model, packages=[package('ReferenceUse', {'related':'boolean'})], gateway=Gateway())
    assert len(model.batches) == 1
    data = model.batches[0][0]
    assert len([s for s in data['sources'] if s['origin'] == 'external']) == 1
    for nid in ['use0','use1','use2']:
        fact = result['results']['method_facts'][nid]['related']
        assert fact['state'] == 'observed' and fact['value'] is True
    assert len([e for e in result['entities'] if e['kind'] == 'CitationIntent']) == 3
    assert len([e for e in result['entities'] if e['kind'] == 'SemanticObservation']) == 3


def test_cross_node_quotes_cannot_become_evidence_for_another_target(tmp_path):
    def crossed(response, data):
        response['results']['p1'] = copy.deepcopy(response['results']['p0'])
        return response
    result = run(tmp_path, paper(tmp_path, 2), BatchModel(crossed))
    assert result['results']['method_facts']['p0']['method']['state'] == 'observed'
    assert result['results']['method_facts']['p1']['method']['state'] == 'unknown'
    assert all(e.get('node_id') != 'p1' for e in result['evidence'] if e.get('kind') == 'source_span')


@pytest.mark.parametrize('bad', ['missing','wrong_type','bad_field','wrong_node','non_mapping'])
def test_partial_or_malformed_response_only_makes_affected_nodes_unknown(tmp_path, bad):
    def malformed(response, data):
        if bad == 'missing': response['results'].pop('p1')
        elif bad == 'wrong_type': response['results']['p1'] = []
        elif bad == 'bad_field': response['results']['p1']['fields']['method']['value'] = 42
        elif bad == 'wrong_node': response['results']['not-requested'] = response['results'].pop('p1')
        else: response['results'] = []
        return response
    result = run(tmp_path, paper(tmp_path, 2), BatchModel(malformed))
    assert set(result['results']['method_facts']) == {'p0','p1'}
    assert result['results']['method_facts']['p1']['method']['state'] == 'unknown'
    assert result['results']['method_facts']['p0']['method']['state'] == ('unknown' if bad == 'non_mapping' else 'observed')


def test_node_limit_and_utf8_soft_limit_split_without_truncation(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','3')
    model = BatchModel()
    run(tmp_path, paper(tmp_path, 8), model)
    assert [len(c[0]['nodes']) for c in model.batches] == [3,3,2]
    other = tmp_path/'large';other.mkdir()
    texts = ['We apply tree models '+str(i)+' '+('x'*25000) for i in range(3)]
    large = BatchModel()
    run(other, paper(other, 3, texts), large)
    assert [len(c[0]['nodes']) for c in large.batches] == [2,1]
    assert all(len(json.dumps(c[0],ensure_ascii=False,separators=(',',':')).encode()) <= 128*1024 for c in large.batches)
    huge = tmp_path/'huge';huge.mkdir()
    text = 'We apply tree models '+('z'*80000)
    singleton = BatchModel()
    run(huge, paper(huge, 2, [text, 'We apply tree models short.']), singleton)
    assert [len(c[0]['nodes']) for c in singleton.batches] == [1,1]
    assert singleton.batches[0][0]['nodes'][0]['node']['text'] == text
    assert next(s['text'] for s in singleton.batches[0][0]['sources'] if s['source_id']=='paper:p0') == text
    assert len(json.dumps(singleton.batches[0][0],ensure_ascii=False).encode()) > 128*1024


@pytest.mark.parametrize('same_text', [False, True])
def test_conflicting_source_ids_split_instead_of_merging_text(tmp_path, monkeypatch, same_text):
    real = runtime._paper_sources
    def collisions(ir, analysis, node):
        sources = real(ir, analysis, node)
        for source in sources:
            if source['node_id'] == node['id']: source['source_id'] = 'paper:collision'
        return sources
    monkeypatch.setattr(runtime, '_paper_sources', collisions)
    model = BatchModel()
    texts = ['We apply tree models shared.'] * 2 if same_text else None
    result = run(tmp_path, paper(tmp_path, 2, texts), model)
    assert [len(c[0]['nodes']) for c in model.batches] == [1,1]
    assert all(f['method']['state']=='observed' for f in result['results']['method_facts'].values())


def test_same_node_cache_reused_across_mutants_but_changed_source_is_recomputed(tmp_path):
    ir = paper(tmp_path, 3)
    model = BatchModel()
    first = run(tmp_path, ir, model)
    changed = copy.deepcopy(ir);changed['revision'] = 'next';changed['nodes'][-1]['text'] = 'Changed note.'
    second = run(tmp_path, changed, model)
    assert len(model.batches) == 1
    assert first['paper_ir_sha256'] != second['paper_ir_sha256']
    changed = copy.deepcopy(changed);changed['revision'] = 'next2';changed['nodes'][1]['text'] += ' Revised tree models.'
    run(tmp_path, changed, model)
    assert len(model.batches) == 2
    assert [n['node']['id'] for n in model.batches[-1][0]['nodes']] == ['p0']


@pytest.mark.parametrize('error', [BudgetExceeded('fake budget stop'), RuntimeError('fake HTTP failure')])
def test_batch_exception_does_not_retry_and_previous_batches_remain_cached(tmp_path, monkeypatch, error):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','2')
    ir = paper(tmp_path, 5);model = BatchModel(fail_on=2,error=error)
    with pytest.raises(type(error),match='fake'):
        run(tmp_path, ir, model)
    assert len(model.batches) == 2
    assert len(list((tmp_path/'cache/generated-nodes').glob('*.json'))) == 2
    assert not list((tmp_path/'cache/program-analysis').glob('*.json'))
    resumed = BatchModel()
    result = run(tmp_path, ir, resumed)
    assert [len(c[0]['nodes']) for c in resumed.batches] == [2,1]
    assert all(f['method']['state']=='observed' for f in result['results']['method_facts'].values())


def test_not_ready_targets_and_no_client_do_not_send_semantic_requests(tmp_path):
    ir = paper(tmp_path, 3);model = BatchModel()
    result = run(tmp_path, ir, model, packages=[package('ReferenceUse',{'related':'boolean'})],gateway=Gateway(empty=True))
    assert model.batches == []
    assert all(f['related']['state']=='unknown' for f in result['results']['method_facts'].values())
    other = tmp_path/'offline';other.mkdir()
    result = run(other, paper(other, 3), None)
    assert all(f['method']['state']=='unknown' for f in result['results']['method_facts'].values())


def test_modes_have_separate_caches_and_default_single_mode_keeps_legacy_policy(tmp_path,monkeypatch):
    ir = paper(tmp_path, 2)
    monkeypatch.delenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE')
    single = Model()
    first = run(tmp_path, ir, single)
    assert single.semantic_calls == 2 and 'generated_batch' not in first['policy']
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
    assert run(tmp_path, ir, single) == first and single.semantic_calls == 2
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','8')
    batch = BatchModel();second = run(tmp_path, ir, batch)
    assert len(batch.batches)==1 and second['policy']['generated_batch']['batch_size']==8
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
    assert run(tmp_path, ir, single) == first and single.semantic_calls == 2


@pytest.mark.parametrize('value',['0','9','-1','1.5','bad',''])
def test_invalid_batch_configuration_fails_before_any_model_call(tmp_path,monkeypatch,value):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE',value)
    model = BatchModel()
    with pytest.raises(ValueError,match='PAPER_COMPILER_ANALYSIS_BATCH_SIZE'):
        run(tmp_path, paper(tmp_path), model)
    assert not model.batches and not model.requests


def test_public_policy_and_batch_limits_are_bounded_and_caller_cannot_mutate_them(monkeypatch):
    policy = runtime.analysis_execution_policy()
    assert policy['batch_size']==8 and policy['task']==BATCH_TASK
    assert policy['input_soft_limit_bytes']==128*1024 and policy['max_tokens_per_batch']==16384
    assert len(policy['batch_protocol_sha256'])==64
    policy['batch_size']=99
    assert runtime.analysis_execution_policy()['batch_size']==8


def reference_packages(count):
    result = []
    for index in range(count):
        p = package('ReferenceUse', {'related':'boolean'}, instructions='Ground request '+str(index))
        request = p['program_spec']['analysis_requests'][0]
        old = request['name'];name = 'reference_fact_'+str(index)
        request['name'] = name
        p['program_spec']['requires'] = [name]
        p['registry']['capabilities'][name] = p['registry']['capabilities'].pop(old)
        p['manifest']['version_id'] = 'generation-'+str(index)
        result.append(p)
    return result


def test_single_call_projection_and_ir_hash_do_not_scale_with_targets_or_requests(tmp_path, monkeypatch):
    monkeypatch.setenv('PAPER_COMPILER_ANALYSIS_BATCH_SIZE','1')
    ir = paper(tmp_path, 8)
    ir['layout']['pages'] = [{'page_index':0,'width':600,'height':800,'rotation':0,
        'lines':[{'id':'line0','text':'Original layout details','chars':[{'c':'O','bbox':[0,0,10,10]}]}],
        'images':[{'bbox':[10,10,20,20]}]}]
    before = copy.deepcopy(ir)
    model = Model(grounded_reference);packages = reference_packages(3)
    work = {'projection':0,'ir_hash':0};projected=[]
    real_project, real_hash = runtime._builtin_ir, runtime.ir_hash
    def project(value):
        work['projection'] += 1
        result = real_project(value)
        projected.append((result,copy.deepcopy(result)))
        return result
    def digest(value):
        work['ir_hash'] += 1
        return real_hash(value)
    monkeypatch.setattr(runtime,'_builtin_ir',project)
    monkeypatch.setattr(runtime,'ir_hash',digest)
    result = run(tmp_path, ir, model, packages=packages, gateway=Gateway())
    assert model.semantic_calls == 24
    assert work == {'projection':1,'ir_hash':1}
    assert ir == before and all(value == snapshot for value,snapshot in projected)
    assert 'generated_batch' not in result['policy']
    assert len([e for e in result['entities'] if e['kind']=='CitationIntent']) == 8
    assert len([e for e in result['entities'] if e['kind']=='SemanticObservation']) == 24
    # IDs retain the existing full-IR hash contract, including one per field.
    from paper_compiler.storage import json_bytes
    for entity in result['entities']:
        if entity['kind'] != 'SemanticObservation': continue
        fact = result['results'][entity['capability']][entity['target_node_id']][entity['field']]
        expected = 'semantic-'+hashlib.sha256(json_bytes([real_hash(ir),entity['capability'],
            entity['target_node_id'],entity['field'],fact])).hexdigest()[:24]
        assert entity['id'] == expected
    variant = copy.deepcopy(ir);variant['revision']='unrelated-variant';variant['nodes'][-1]['text']='Another note.'
    run(tmp_path, variant, model, packages=packages, gateway=Gateway())
    assert model.semantic_calls == 24
    assert work == {'projection':2,'ir_hash':2}
    assert ir == before and all(value == snapshot for value,snapshot in projected)


def test_optional_precomputed_projection_and_hash_keep_helper_results_identical(tmp_path):
    ir = paper(tmp_path, 1)
    analysis = run(tmp_path, ir, BatchModel(), packages=[package('ReferenceUse',{'related':'boolean'})],gateway=Gateway())
    node = next(n for n in ir['nodes'] if n['id']=='use0')
    projected = runtime._builtin_ir(ir);before = copy.deepcopy(projected)
    slow = runtime._target_data(ir,analysis,node,Gateway(),None,{})
    fast = runtime._target_data(ir,analysis,node,Gateway(),None,{},builtin_ir=projected)
    assert slow == fast and projected == before
    left=copy.deepcopy(analysis);right=copy.deepcopy(analysis)
    facts=analysis['results']['method_facts']['use0']
    runtime._citation_graph(ir,left,node,slow[0],'method_facts',facts)
    runtime._citation_graph(ir,right,node,fast[0],'method_facts',facts,paper_ir_sha256=ir_hash(ir))
    assert left == right


def test_batches_do_not_cross_generated_request_or_paper_boundaries(tmp_path):
    model = BatchModel();packages = reference_packages(2)
    ir = paper(tmp_path, 3)
    result = run(tmp_path, ir, model, packages=packages,gateway=Gateway())
    assert len(model.batches) == 2
    assert all(len(c[0]['nodes']) == 3 for c in model.batches)
    assert 'Ground request 0' in model.batches[0][2]
    assert 'Ground request 1' in model.batches[1][2]
    assert set(result['results']) >= {'reference_fact_0','reference_fact_1'}
    other = tmp_path/'other-paper';other.mkdir()
    second = paper(other,3,['We apply tree models other-paper '+str(i)+' [1].' for i in range(3)])
    second['document_id'] = 'other-paper'
    run(tmp_path,second,model,packages=packages,gateway=Gateway())
    assert len(model.batches) == 4
    assert all('other-paper' not in n['citation_context']['text'] for c in model.batches[:2] for n in c[0]['nodes'])
    assert all('other-paper' in n['citation_context']['text'] for c in model.batches[2:] for n in c[0]['nodes'])


def test_changed_external_source_body_invalidates_batched_node_cache(tmp_path):
    ir = paper(tmp_path,2);gateway = Gateway();model = BatchModel()
    packages = [package('ReferenceUse',{'related':'boolean'})]
    run(tmp_path,ir,model,packages=packages,gateway=gateway)
    variant = copy.deepcopy(ir);variant['revision']='external-evidence-changed'
    gateway.text = 'Tree models estimate lake measurements with a revised procedure.'
    result = run(tmp_path,variant,model,packages=packages,gateway=gateway)
    assert len(model.batches) == 2
    assert any('revised procedure' in e.get('quote','') for e in result['evidence'])
    assert all(f['related']['state']=='observed' for f in result['results']['method_facts'].values())


def test_batched_false_semantics_still_need_positive_scope_contradiction(tmp_path):
    def false_without_contradiction(response,data):
        response['results']['use0']['fields']['related']['value'] = False
        return response
    result = run(tmp_path,paper(tmp_path,2),BatchModel(false_without_contradiction),
                 packages=[package('ReferenceUse',{'related':'boolean'})],gateway=Gateway())
    assert result['results']['method_facts']['use0']['related']['state']=='unknown'
    assert result['results']['method_facts']['use1']['related']['state']=='observed'
    assert [e['use_id'] for e in result['entities'] if e['kind']=='CitationIntent']==['use1']


def test_ambiguous_source_id_within_one_node_stays_unknown_without_api(tmp_path,monkeypatch):
    real = runtime._paper_sources
    def ambiguous(ir,analysis,node):
        sources = real(ir,analysis,node)
        source = next(s for s in sources if s['node_id']==node['id'])
        return [*sources,{**source,'text':'Conflicting text with same source identity.'}]
    monkeypatch.setattr(runtime,'_paper_sources',ambiguous)
    model = BatchModel()
    result = run(tmp_path,paper(tmp_path,1),model)
    assert model.batches == []
    assert result['results']['method_facts']['p0']['method']['state']=='unknown'
